from fastapi import Depends, HTTPException, status
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.email or user.email.lower() != settings.ADMIN_EMAIL.lower():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user
