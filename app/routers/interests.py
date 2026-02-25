from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session, joinedload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.interest import Interest, FocusStint, PauseInterval
from app.schemas.interest import (
    InterestCreate,
    InterestOut,
    InterestRename,
    FocusStintOut,
    PauseIntervalOut,
)

router = APIRouter(prefix="/interests", tags=["interests"])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_owner(db: Session, user_id: str, interest_id: str) -> Interest:
    interest = (
        db.query(Interest)
        .filter(and_(Interest.id == interest_id, Interest.user_id == user_id))
        .first()
    )
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found")
    return interest


def _open_stint(db: Session, user_id: str, interest_id: str) -> FocusStint | None:
    return (
        db.query(FocusStint)
        .filter(
            and_(
                FocusStint.user_id == user_id,
                FocusStint.interest_id == interest_id,
                FocusStint.ended_at.is_(None),
            )
        )
        .first()
    )


def _open_pause(db: Session, stint_id: str) -> PauseInterval | None:
    return (
        db.query(PauseInterval)
        .filter(
            and_(PauseInterval.stint_id == stint_id, PauseInterval.resumed_at.is_(None))
        )
        .first()
    )


@router.post("", response_model=InterestOut, status_code=201)
def create_interest(
    payload: InterestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")

    focus_count = (
        db.query(func.count(Interest.id))
        .filter(Interest.user_id == user.id, Interest.status == "FOCUS")
        .scalar()
        or 0
    )

    is_focus = focus_count < 4
    status = "FOCUS" if is_focus else "BACKLOG"

    interest = Interest(user_id=user.id, name=name, status=status, focus_state="ACTIVE")
    db.add(interest)
    db.flush()  # Use flush to get the ID without committing yet

    if is_focus:
        stint = FocusStint(
            user_id=user.id, interest_id=interest.id, started_at=_utcnow()
        )
        db.add(stint)

    db.commit()
    db.refresh(interest)

    interest.id = str(interest.id)
    return interest


@router.get("", response_model=list[InterestOut])
def list_interests(
    status_filter: str | None = None,  # "FOCUS" or "BACKLOG"
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Interest).filter(Interest.user_id == user.id)
    if status_filter:
        status_filter = status_filter.upper()
        if status_filter not in {"FOCUS", "BACKLOG"}:
            raise HTTPException(
                status_code=400, detail="status_filter must be FOCUS or BACKLOG"
            )
        q = q.filter(Interest.status == status_filter)

    interests = q.order_by(
        Interest.status.desc(), Interest.sort_order.asc(), Interest.updated_at.desc()
    ).all()
    return [
        InterestOut(
            id=str(i.id),
            name=i.name,
            status=i.status,
            focus_state=i.focus_state,
            sort_order=i.sort_order,
        )
        for i in interests
    ]


@router.patch("/{interest_id}", response_model=InterestOut)
def rename_interest(
    interest_id: str,
    payload: InterestRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = _require_owner(db, str(user.id), interest_id)
    interest.name = payload.name.strip()
    db.add(interest)
    db.commit()
    db.refresh(interest)

    return InterestOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        sort_order=interest.sort_order,
    )


@router.post("/{interest_id}/move-to-focus", response_model=InterestOut)
def move_to_focus(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = _require_owner(db, str(user.id), interest_id)

    if interest.status == "FOCUS":
        # if already in focus but paused, keep it in focus; don't create a new stint
        return InterestOut(
            id=str(interest.id),
            name=interest.name,
            status=interest.status,
            focus_state=interest.focus_state,
            sort_order=interest.sort_order,
        )

    # enforce max 4 focus
    focus_count = (
        db.query(func.count(Interest.id))
        .filter(and_(Interest.user_id == user.id, Interest.status == "FOCUS"))
        .scalar()
        or 0
    )
    if focus_count >= 4:
        raise HTTPException(
            status_code=409,
            detail="Focus limit reached (max 4). Pause/move one to backlog first.",
        )

    interest.status = "FOCUS"
    interest.focus_state = "ACTIVE"

    # create a new stint (because it just entered focus)
    stint = FocusStint(
        user_id=user.id, interest_id=interest.id, started_at=_utcnow(), ended_at=None
    )
    db.add(stint)
    db.add(interest)
    db.commit()
    db.refresh(interest)

    return InterestOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        sort_order=interest.sort_order,
    )


@router.post("/{interest_id}/pause", response_model=InterestOut)
def pause_interest(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = _require_owner(db, str(user.id), interest_id)

    if interest.status != "FOCUS":
        raise HTTPException(
            status_code=409, detail="Only focus interests can be paused"
        )

    if interest.focus_state == "PAUSED":
        return InterestOut(
            id=str(interest.id),
            name=interest.name,
            status=interest.status,
            focus_state=interest.focus_state,
            sort_order=interest.sort_order,
        )

    stint = _open_stint(db, str(user.id), str(interest.id))
    if not stint:
        # should not happen if state machine is used correctly
        raise HTTPException(
            status_code=409, detail="No open focus stint for this interest"
        )

    # create pause interval if none open
    if not _open_pause(db, str(stint.id)):
        db.add(PauseInterval(stint_id=stint.id, paused_at=_utcnow(), resumed_at=None))

    interest.focus_state = "PAUSED"
    db.add(interest)
    db.commit()
    db.refresh(interest)

    return InterestOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        sort_order=interest.sort_order,
    )


@router.post("/{interest_id}/resume", response_model=InterestOut)
def resume_interest(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = _require_owner(db, str(user.id), interest_id)

    if interest.status != "FOCUS":
        raise HTTPException(
            status_code=409, detail="Only focus interests can be resumed"
        )

    if interest.focus_state == "ACTIVE":
        return InterestOut(
            id=str(interest.id),
            name=interest.name,
            status=interest.status,
            focus_state=interest.focus_state,
            sort_order=interest.sort_order,
        )

    stint = _open_stint(db, str(user.id), str(interest.id))
    if not stint:
        raise HTTPException(
            status_code=409, detail="No open focus stint for this interest"
        )

    pause = _open_pause(db, str(stint.id))
    if pause:
        pause.resumed_at = _utcnow()
        db.add(pause)

    interest.focus_state = "ACTIVE"
    db.add(interest)
    db.commit()
    db.refresh(interest)

    return InterestOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        sort_order=interest.sort_order,
    )


@router.post("/{interest_id}/move-to-backlog", response_model=InterestOut)
def move_to_backlog(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = _require_owner(db, str(user.id), interest_id)

    if interest.status != "FOCUS":
        # already backlog
        return InterestOut(
            id=str(interest.id),
            name=interest.name,
            status=interest.status,
            focus_state=interest.focus_state,
            sort_order=interest.sort_order,
        )

    stint = _open_stint(db, str(user.id), str(interest.id))
    if stint:
        # close any open pause interval
        pause = _open_pause(db, str(stint.id))
        now = _utcnow()
        if pause and pause.resumed_at is None:
            pause.resumed_at = now
            db.add(pause)

        stint.ended_at = now
        db.add(stint)

    interest.status = "BACKLOG"
    # keep focus_state as ACTIVE for default when brought back later
    interest.focus_state = "ACTIVE"
    db.add(interest)
    db.commit()
    db.refresh(interest)

    return InterestOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        sort_order=interest.sort_order,
    )


@router.get("/timeline", response_model=list[FocusStintOut])
def timeline(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stints = (
        db.query(FocusStint)
        .options(joinedload(FocusStint.interest), joinedload(FocusStint.pauses))
        .filter(FocusStint.user_id == user.id)
        .order_by(FocusStint.started_at.desc())
        .all()
    )

    out: list[FocusStintOut] = []
    for s in stints:
        out.append(
            FocusStintOut(
                id=str(s.id),
                interest_id=str(s.interest_id),
                interest_name=s.interest.name if s.interest else "",
                started_at=s.started_at,
                ended_at=s.ended_at,
                pauses=[
                    PauseIntervalOut(
                        id=str(p.id), paused_at=p.paused_at, resumed_at=p.resumed_at
                    )
                    for p in (s.pauses or [])
                ],
            )
        )
    return out
