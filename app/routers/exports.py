import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.feature_flags import exports_are_free, utcnow
from app.db.session import get_db
from app.models.user import User
from app.models.interest import Interest
from app.models.export import ExportDownload
from app.models.target import Target, TargetBullet, Todo
from app.schemas.tree import (
    InterestExportOut,
    TargetExportOut,
    GroupedTodosOut,
    TodoOut,
    TodoCounts,
    BulletOut,
)
from app.schemas.export import ExportCreateOut, ExportStatusOut, ExportTokenOut

router = APIRouter(prefix="/exports", tags=["exports"])

PRICE_CENTS = 100
CURRENCY = "USD"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_focus_interest(db: Session, user_id: str, interest_id: str) -> Interest:
    interest = (
        db.query(Interest)
        .filter(Interest.id == interest_id, Interest.user_id == user_id)
        .first()
    )
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found")
    if interest.status != "FOCUS":
        raise HTTPException(
            status_code=403, detail="Only focus interests can be exported"
        )
    return interest


@router.post("/interest/{interest_id}", response_model=ExportCreateOut, status_code=201)
def create_export_purchase(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Creates a PENDING export purchase record (represents '$1 per download').
    Later: your payment provider webhook will mark it PAID.
    """
    _require_focus_interest(db, str(user.id), interest_id)

    if exports_are_free(db):
        rec = ExportDownload(
            user_id=user.id,
            interest_id=interest_id,
            status="PAID",
            amount_cents=0,
            currency="USD",
            provider="FREE_MODE",
            provider_ref=None,
            paid_at=utcnow(),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return ExportCreateOut(
            export_id=str(rec.id),
            status=rec.status,
            amount_cents=rec.amount_cents,
            currency=rec.currency,
        )

    rec = ExportDownload(
        user_id=user.id,
        interest_id=interest_id,
        status="PENDING",
        amount_cents=PRICE_CENTS,
        currency=CURRENCY,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return ExportCreateOut(
        export_id=str(rec.id),
        status=rec.status,
        amount_cents=rec.amount_cents,
        currency=rec.currency,
    )


@router.get("/{export_id}", response_model=ExportStatusOut)
def get_export_status(
    export_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rec = (
        db.query(ExportDownload)
        .filter(ExportDownload.id == export_id, ExportDownload.user_id == user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Export not found")

    return ExportStatusOut(
        export_id=str(rec.id),
        status=rec.status,
        amount_cents=rec.amount_cents,
        currency=rec.currency,
        paid_at=rec.paid_at,
        consumed_at=rec.consumed_at,
    )


@router.post("/{export_id}/token", response_model=ExportTokenOut)
def mint_download_token(
    export_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    After payment is confirmed, mint a single-use token.
    Token can be minted once (or re-minted if you choose; here we don't allow re-mint).
    """
    rec = (
        db.query(ExportDownload)
        .filter(ExportDownload.id == export_id, ExportDownload.user_id == user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Export not found")

    if rec.status == "PENDING":
        raise HTTPException(status_code=402, detail="Payment required")
    if rec.status == "CANCELED":
        raise HTTPException(status_code=409, detail="Export canceled")
    if rec.status == "CONSUMED":
        raise HTTPException(status_code=409, detail="Already consumed")

    if rec.token:
        # prevent multiple tokens for the same paid download (keeps 'per download' strict)
        return ExportTokenOut(export_id=str(rec.id), token=rec.token)

    rec.token = secrets.token_urlsafe(32)
    rec.token_issued_at = _utcnow()
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return ExportTokenOut(export_id=str(rec.id), token=rec.token)


def _build_export_payload(db: Session, interest: Interest) -> InterestExportOut:
    # This mirrors your earlier /interests/{id}/export endpoint, but invoked internally.
    targets = (
        db.query(Target)
        .filter(Target.interest_id == interest.id)
        .order_by(Target.sort_order.asc(), Target.updated_at.desc())
        .all()
    )
    target_ids = [t.id for t in targets]

    bullets_map: dict[str, list[BulletOut]] = {str(tid): [] for tid in target_ids}
    if target_ids:
        bullets = (
            db.query(TargetBullet)
            .filter(TargetBullet.target_id.in_(target_ids))
            .order_by(
                TargetBullet.target_id.asc(),
                TargetBullet.sort_order.asc(),
                TargetBullet.updated_at.desc(),
            )
            .all()
        )
        for b in bullets:
            bullets_map[str(b.target_id)].append(
                BulletOut(
                    id=str(b.id),
                    content=b.content,
                    category=b.category,
                    sort_order=b.sort_order,
                )
            )

    todos_map: dict[str, GroupedTodosOut] = {
        str(tid): GroupedTodosOut(active=[], backlog=[], done=[]) for tid in target_ids
    }
    totals = TodoCounts(active=0, backlog=0, done=0)

    if target_ids:
        todos = (
            db.query(Todo)
            .filter(Todo.target_id.in_(target_ids))
            .order_by(Todo.target_id.asc(), Todo.created_at.desc())
            .all()
        )
        for td in todos:
            item = TodoOut(
                id=str(td.id),
                status=td.status,
                content=td.content,
                created_at=td.created_at,
                done_at=td.done_at,
            )
            bucket = todos_map[str(td.target_id)]
            if td.status == "ACTIVE":
                bucket.active.append(item)
                totals.active += 1
            elif td.status == "BACKLOG":
                bucket.backlog.append(item)
                totals.backlog += 1
            else:
                bucket.done.append(item)
                totals.done += 1

    out_targets: list[TargetExportOut] = []
    for t in targets:
        out_targets.append(
            TargetExportOut(
                id=str(t.id),
                name=t.name,
                sort_order=t.sort_order,
                bullets=bullets_map.get(str(t.id), []),
                todos=todos_map.get(
                    str(t.id), GroupedTodosOut(active=[], backlog=[], done=[])
                ),
            )
        )

    return InterestExportOut(
        id=str(interest.id),
        name=interest.name,
        status=interest.status,
        focus_state=interest.focus_state,
        exported_at=_utcnow(),
        targets=out_targets,
        totals=totals,
    )


@router.get("/download/{token}", response_model=InterestExportOut)
def redeem_download_token(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Redeems a token exactly once and returns the export payload.
    Frontend uses this payload to generate a PDF.
    """
    rec = db.query(ExportDownload).filter(ExportDownload.token == token).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Invalid token")

    # token must belong to the authenticated user
    if str(rec.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    if rec.status != "PAID":
        raise HTTPException(status_code=409, detail="Token not redeemable")

    interest = _require_focus_interest(db, str(user.id), str(rec.interest_id))

    # consume
    rec.status = "CONSUMED"
    rec.consumed_at = _utcnow()
    db.add(rec)
    db.commit()

    return _build_export_payload(db, interest)


# ---- DEV ONLY: mark export as paid (replace with payment webhook later) ----
@router.post("/{export_id}/dev/mark-paid", response_model=ExportStatusOut)
def dev_mark_paid(
    export_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Dev convenience. In production, remove this and use a real payment webhook.
    """
    if settings.is_prod:
        raise HTTPException(status_code=404, detail="Not found")

    rec = (
        db.query(ExportDownload)
        .filter(ExportDownload.id == export_id, ExportDownload.user_id == user.id)
        .first()
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Export not found")

    if rec.status in {"CANCELED", "CONSUMED"}:
        raise HTTPException(status_code=409, detail="Cannot mark paid")

    rec.status = "PAID"
    rec.paid_at = _utcnow()
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return ExportStatusOut(
        export_id=str(rec.id),
        status=rec.status,
        amount_cents=rec.amount_cents,
        currency=rec.currency,
        paid_at=rec.paid_at,
        consumed_at=rec.consumed_at,
    )
