import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_API_KEY


def stripe_now_configured() -> bool:
    return bool(settings.STRIPE_API_KEY)
