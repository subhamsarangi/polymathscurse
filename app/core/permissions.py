from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.interest import Interest
from app.models.target import Target


def require_interest_owned(db: Session, user_id: str, interest_id: str) -> Interest:
    interest = (
        db.query(Interest)
        .filter(Interest.id == interest_id, Interest.user_id == user_id)
        .first()
    )
    if not interest:
        raise HTTPException(status_code=404, detail="Interest not found")
    return interest


def require_interest_interactive(interest: Interest):
    if interest.status != "FOCUS" or interest.focus_state != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Interest is not interactive (must be in focus and active)",
        )


def require_target_owned(db: Session, user_id: str, target_id: str) -> Target:
    # join targets->interests to ensure ownership
    target = (
        db.query(Target)
        .join(Interest, Interest.id == Target.interest_id)
        .filter(Target.id == target_id, Interest.user_id == user_id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target
