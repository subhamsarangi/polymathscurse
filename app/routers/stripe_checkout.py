import stripe
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.feature_flags import exports_are_free
from app.db.session import get_db
from app.models.export import ExportDownload
from app.models.user import User

router = APIRouter(prefix="/stripe", tags=["stripe"])


@router.post("/checkout/{export_id}")
def create_checkout_session(
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

    # if free mode is on, you shouldn't be paying
    if exports_are_free(db):
        raise HTTPException(status_code=409, detail="Exports are currently free")

    if rec.status != "PENDING":
        raise HTTPException(
            status_code=409, detail=f"Export not payable (status={rec.status})"
        )

    stripe.api_key = settings.STRIPE_API_KEY

    success_url = f"{settings.FRONTEND_URL}/export/success?export_id={export_id}"
    cancel_url = f"{settings.FRONTEND_URL}/export/cancel?export_id={export_id}"

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": settings.STRIPE_CURRENCY.lower(),
                    "product_data": {"name": "PDF Export (1 download)"},
                    "unit_amount": int(rec.amount_cents),
                },
                "quantity": 1,
            }
        ],
        metadata={"export_id": str(rec.id)},
        client_reference_id=str(rec.id),
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return {"checkout_url": session.url, "session_id": session.id}
