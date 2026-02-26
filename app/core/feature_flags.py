from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.admin_settings import AdminSettings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_admin_settings(db: Session) -> AdminSettings:
    row = db.query(AdminSettings).filter(AdminSettings.key == "default").first()
    if not row:
        row = AdminSettings(key="default")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def exports_are_free(db: Session) -> bool:
    s = get_admin_settings(db)
    if s.free_exports_enabled:
        return True
    if s.free_exports_until and utcnow() < s.free_exports_until:
        return True
    return False
