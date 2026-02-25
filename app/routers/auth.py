from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.orm import Session
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    make_access_token,
    make_refresh_token,
    decode_token,
    new_jti,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import SignupIn, LoginIn, GoogleIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


def _set_auth_cookies(resp: Response, access: str, refresh: str):
    common = dict(
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    if settings.COOKIE_DOMAIN:
        common["domain"] = settings.COOKIE_DOMAIN

    # access cookie (short)
    resp.set_cookie(
        key=ACCESS_COOKIE,
        value=access,
        max_age=settings.ACCESS_TTL_MIN * 60,
        **common,
    )
    # refresh cookie (long)
    resp.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh,
        max_age=settings.REFRESH_TTL_DAYS * 24 * 3600,
        **common,
    )


def _clear_auth_cookies(resp: Response):
    common = dict(path="/")
    if settings.COOKIE_DOMAIN:
        common["domain"] = settings.COOKIE_DOMAIN
    resp.delete_cookie(ACCESS_COOKIE, **common)
    resp.delete_cookie(REFRESH_COOKIE, **common)


@router.post("/signup", response_model=UserOut)
def signup(payload: SignupIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already in use")

    user = User(email=email, password_hash=hash_password(payload.password))
    user.refresh_jti = new_jti()
    db.add(user)
    db.commit()
    db.refresh(user)

    access = make_access_token(str(user.id))
    refresh = make_refresh_token(str(user.id), user.refresh_jti)
    _set_auth_cookies(response, access, refresh)

    return UserOut(id=str(user.id), email=user.email)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # rotate refresh jti on login
    user.refresh_jti = new_jti()
    db.add(user)
    db.commit()

    access = make_access_token(str(user.id))
    refresh = make_refresh_token(str(user.id), user.refresh_jti)
    _set_auth_cookies(response, access, refresh)

    return UserOut(id=str(user.id), email=user.email)


@router.post("/google", response_model=UserOut)
def google_login(payload: GoogleIn, response: Response, db: Session = Depends(get_db)):
    try:
        idinfo = google_id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    sub = idinfo.get("sub")
    email = (idinfo.get("email") or "").lower().strip() or None

    if not sub:
        raise HTTPException(status_code=401, detail="Invalid Google token")

    user = db.query(User).filter(User.google_sub == sub).first()
    if not user and email:
        # link by email if exists
        user = db.query(User).filter(User.email == email).first()
        if user and not user.google_sub:
            user.google_sub = sub

    if not user:
        user = User(email=email, google_sub=sub)

    user.refresh_jti = new_jti()
    db.add(user)
    db.commit()
    db.refresh(user)

    access = make_access_token(str(user.id))
    refresh = make_refresh_token(str(user.id), user.refresh_jti)
    _set_auth_cookies(response, access, refresh)

    return UserOut(id=str(user.id), email=user.email)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = payload.get("sub")
    jti = payload.get("jti")
    if not user_id or not jti:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.refresh_jti or user.refresh_jti != jti:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    # rotate
    user.refresh_jti = new_jti()
    db.add(user)
    db.commit()

    access = make_access_token(str(user.id))
    refresh2 = make_refresh_token(str(user.id), user.refresh_jti)
    _set_auth_cookies(response, access, refresh2)

    return {"ok": True}


@router.post("/logout")
def logout(response: Response, db: Session = Depends(get_db), request: Request = None):
    # best-effort revoke current session if cookie present
    if request is not None:
        token = request.cookies.get(REFRESH_COOKIE)
        if token:
            try:
                payload = decode_token(token)
                if payload.get("type") == "refresh":
                    user_id = payload.get("sub")
                    user = db.query(User).filter(User.id == user_id).first()
                    if user:
                        user.refresh_jti = None
                        db.add(user)
                        db.commit()
            except Exception:
                pass

    _clear_auth_cookies(response)
    return {"ok": True}
