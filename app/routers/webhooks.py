from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.export import ExportDownload
from app.models.stripe_event import StripeWebhookEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _utcnow():
    return datetime.now(timezone.utc)


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    if not getattr(settings, "STRIPE_WEBHOOK_SECRET", None):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook not configured",
        )
    # 1) read raw payload for signature verification
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature")

    # 2) verify signature
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event.get("id")
    event_type = event.get("type")

    # 3) idempotency: store event_id with unique constraint
    try:
        db.add(StripeWebhookEvent(event_id=event_id, status="received"))
        db.commit()
    except IntegrityError:
        db.rollback()
        # already processed (or being processed); acknowledge to stop retries
        return {"ok": True, "duplicate": True}

    # default mark as ignored unless processed
    try:
        if event_type != "checkout.session.completed":
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update({"status": "ignored", "processed_at": _utcnow()})
            db.commit()
            return {"ok": True, "ignored": True}

        session = event["data"]["object"]

        # required validations
        if session.get("mode") != "payment":
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "ignored",
                    "processed_at": _utcnow(),
                    "error": "mode!=payment",
                }
            )
            db.commit()
            return {"ok": True}

        if session.get("payment_status") != "paid":
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {"status": "ignored", "processed_at": _utcnow(), "error": "not paid"}
            )
            db.commit()
            return {"ok": True}

        metadata = session.get("metadata") or {}
        export_id = metadata.get("export_id")
        if not export_id:
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "error",
                    "processed_at": _utcnow(),
                    "error": "missing export_id",
                }
            )
            db.commit()
            return {"ok": True}

        amount_total = session.get("amount_total")
        currency = (session.get("currency") or "").upper()

        # 4) lock row & update safely
        rec = (
            db.query(ExportDownload)
            .filter(ExportDownload.id == export_id)
            .with_for_update()
            .first()
        )
        if not rec:
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "error",
                    "processed_at": _utcnow(),
                    "error": "export not found",
                }
            )
            db.commit()
            return {"ok": True}

        # If already paid/consumed, treat idempotently
        if rec.status in {"PAID", "CONSUMED"}:
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update({"status": "processed", "processed_at": _utcnow()})
            db.commit()
            return {"ok": True}

        # Ensure we're only fulfilling PENDING records
        if rec.status != "PENDING":
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "error",
                    "processed_at": _utcnow(),
                    "error": f"unexpected status {rec.status}",
                }
            )
            db.commit()
            return {"ok": True}

        # Validate amount/currency to prevent mismatches
        if int(amount_total or 0) != int(rec.amount_cents):
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "error",
                    "processed_at": _utcnow(),
                    "error": "amount mismatch",
                }
            )
            db.commit()
            return {"ok": True}

        if currency != (rec.currency or "").upper():
            db.query(StripeWebhookEvent).filter(
                StripeWebhookEvent.event_id == event_id
            ).update(
                {
                    "status": "error",
                    "processed_at": _utcnow(),
                    "error": "currency mismatch",
                }
            )
            db.commit()
            return {"ok": True}

        # Mark paid
        rec.status = "PAID"
        rec.paid_at = _utcnow()
        rec.provider = "stripe"
        rec.provider_ref = session.get("id")  # checkout session id
        db.add(rec)

        db.query(StripeWebhookEvent).filter(
            StripeWebhookEvent.event_id == event_id
        ).update({"status": "processed", "processed_at": _utcnow()})
        db.commit()
        return {"ok": True}

    except Exception as e:
        db.rollback()
        db.query(StripeWebhookEvent).filter(
            StripeWebhookEvent.event_id == event_id
        ).update({"status": "error", "processed_at": _utcnow(), "error": str(e)[:400]})
        db.commit()
        return {"ok": True}
