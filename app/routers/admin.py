from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, distinct
from sqlalchemy.orm import Session

from app.core.admin import require_admin
from app.core.feature_flags import get_admin_settings, exports_are_free, utcnow
from app.db.session import get_db
from app.models.user import User
from app.models.export import ExportDownload
from app.schemas.admin import (
    ExportModeOut,
    ExportModeUpdateIn,
    MetricsSummaryOut,
    MetricsWindowOut,
    GrowthBlock,
    RevenueBlock,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _pct(delta: int, prev: int) -> float | None:
    if prev <= 0:
        return None
    return (delta / prev) * 100.0


def _period_bounds_today_utc() -> tuple[datetime, datetime]:
    now = utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _make_window(label: str, start: datetime | None, end: datetime | None):
    return {"label": label, "start": start, "end": end}


def _growth_counts(current: int, previous: int) -> GrowthBlock:
    d = current - previous
    return GrowthBlock(
        current=current, previous=previous, delta=d, pct=_pct(d, previous)
    )


def _revenue_block(current_cents: int, previous_cents: int) -> RevenueBlock:
    d = current_cents - previous_cents
    return RevenueBlock(
        current_cents=current_cents,
        previous_cents=previous_cents,
        delta_cents=d,
        pct=_pct(d, previous_cents),
    )


def _range_prev(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    span = end - start
    return start - span, start


def _new_users_in(db: Session, start: datetime, end: datetime) -> int:
    return int(
        db.query(func.count(User.id))
        .filter(and_(User.created_at >= start, User.created_at < end))
        .scalar()
        or 0
    )


def _paying_users_in(db: Session, start: datetime, end: datetime) -> int:
    # Paying user = user with PAID/CONSUMED export with amount_cents > 0 in that time range
    q = db.query(func.count(distinct(ExportDownload.user_id))).filter(
        ExportDownload.paid_at.isnot(None),
        ExportDownload.paid_at >= start,
        ExportDownload.paid_at < end,
        ExportDownload.status.in_(["PAID", "CONSUMED"]),
        ExportDownload.amount_cents > 0,
    )
    return int(q.scalar() or 0)


def _revenue_in(db: Session, start: datetime, end: datetime) -> int:
    q = db.query(func.coalesce(func.sum(ExportDownload.amount_cents), 0)).filter(
        ExportDownload.paid_at.isnot(None),
        ExportDownload.paid_at >= start,
        ExportDownload.paid_at < end,
        ExportDownload.status.in_(["PAID", "CONSUMED"]),
        ExportDownload.amount_cents > 0,
    )
    return int(q.scalar() or 0)


@router.get("/export-mode", response_model=ExportModeOut)
def get_export_mode(
    db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    s = get_admin_settings(db)
    return ExportModeOut(
        free_exports_enabled=s.free_exports_enabled,
        free_exports_until=s.free_exports_until,
        exports_free_now=exports_are_free(db),
    )


@router.put("/export-mode", response_model=ExportModeOut)
def update_export_mode(
    payload: ExportModeUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    s = get_admin_settings(db)

    if payload.free_exports_enabled is not None:
        s.free_exports_enabled = payload.free_exports_enabled

    # allow setting a promo end time, or clearing it by sending null
    s.free_exports_until = payload.free_exports_until

    db.add(s)
    db.commit()
    db.refresh(s)

    return ExportModeOut(
        free_exports_enabled=s.free_exports_enabled,
        free_exports_until=s.free_exports_until,
        exports_free_now=exports_are_free(db),
    )


@router.post("/export-mode/promo", response_model=ExportModeOut)
def start_export_promo(
    days: int = Query(0, ge=0, le=3650),
    hours: int = Query(0, ge=0, le=87600),
    minutes: int = Query(0, ge=0, le=5256000),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Starts/extends a promo window where exports are free until now + delta.
    Usage examples:
      /admin/export-mode/promo?hours=48
      /admin/export-mode/promo?days=7
      /admin/export-mode/promo?minutes=90
      /admin/export-mode/promo?days=1&hours=12
    """
    if days == 0 and hours == 0 and minutes == 0:
        raise HTTPException(
            status_code=400, detail="Provide at least one of days, hours, minutes"
        )

    delta = timedelta(days=days, hours=hours, minutes=minutes)
    now = utcnow()

    s = get_admin_settings(db)

    # If there is an existing promo still active, extend from its end; else from now
    base = (
        s.free_exports_until
        if (s.free_exports_until and s.free_exports_until > now)
        else now
    )
    s.free_exports_until = base + delta

    # Keep manual override separate; promo should work even if manual override is off.
    # But if manual override was on, you may want promos to be the only control:
    # set it off to avoid "why is it still free after promo ended?"
    s.free_exports_enabled = False

    db.add(s)
    db.commit()
    db.refresh(s)

    return ExportModeOut(
        free_exports_enabled=s.free_exports_enabled,
        free_exports_until=s.free_exports_until,
        exports_free_now=exports_are_free(db),
    )


@router.get("/metrics", response_model=MetricsSummaryOut)
def metrics(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
):
    """
    Uses UTC for all windows.
    Optional custom range: pass start_utc & end_utc (ISO timestamps).
    """
    all_time_users = int(db.query(func.count(User.id)).scalar() or 0)

    all_time_paying_users = int(
        db.query(func.count(distinct(ExportDownload.user_id)))
        .filter(
            ExportDownload.status.in_(["PAID", "CONSUMED"]),
            ExportDownload.amount_cents > 0,
            ExportDownload.paid_at.isnot(None),
        )
        .scalar()
        or 0
    )

    all_time_revenue = int(
        db.query(func.coalesce(func.sum(ExportDownload.amount_cents), 0))
        .filter(
            ExportDownload.status.in_(["PAID", "CONSUMED"]),
            ExportDownload.amount_cents > 0,
            ExportDownload.paid_at.isnot(None),
        )
        .scalar()
        or 0
    )

    windows = []

    # Today
    t0, t1 = _period_bounds_today_utc()
    windows.append(_make_window("today", t0, t1))

    # Last 7 / 30 / 365 days (rolling)
    now = utcnow()
    windows.append(_make_window("last_7_days", now - timedelta(days=7), now))
    windows.append(_make_window("last_30_days", now - timedelta(days=30), now))
    windows.append(_make_window("last_365_days", now - timedelta(days=365), now))

    # Custom
    if start_utc and end_utc:
        if end_utc <= start_utc:
            raise HTTPException(
                status_code=400, detail="end_utc must be after start_utc"
            )
        windows.append(_make_window("custom", start_utc, end_utc))

    out_windows: list[MetricsWindowOut] = []
    for w in windows:
        start = w["start"]
        end = w["end"]
        if not start or not end:
            continue

        prev_start, prev_end = _range_prev(start, end)

        new_users = _new_users_in(db, start, end)
        prev_new_users = _new_users_in(db, prev_start, prev_end)

        paying = _paying_users_in(db, start, end)
        prev_paying = _paying_users_in(db, prev_start, prev_end)

        rev = _revenue_in(db, start, end)
        prev_rev = _revenue_in(db, prev_start, prev_end)

        out_windows.append(
            MetricsWindowOut(
                label=w["label"],
                start_utc=start,
                end_utc=end,
                users_total=all_time_users,
                new_users=_growth_counts(new_users, prev_new_users),
                paying_users=_growth_counts(paying, prev_paying),
                revenue=_revenue_block(rev, prev_rev),
            )
        )

    return MetricsSummaryOut(
        all_time_users=all_time_users,
        all_time_paying_users=all_time_paying_users,
        all_time_revenue_cents=all_time_revenue,
        windows=out_windows,
    )
