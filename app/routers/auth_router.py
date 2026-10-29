"""
Two-step login, exactly matching Module 10 of the blueprint:

  1. POST /auth/login       -- checks ID + password. If correct, generates
                                an OTP, "sends" it (see otp.py), and returns
                                an otp_token -- NOT an access token. The
                                caller still can't reach anything else yet.
  2. POST /auth/verify-otp  -- checks the code against that otp_token. Only
                                on success does it hand back a real access
                                token, which is what every other endpoint
                                requires from here on.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas, auth, otp
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_code(db: Session, user: models.User) -> str:
    """Sends a code, turning the OTP module's problems into clear messages for the login screen."""
    try:
        return otp.create_otp_for_user(db, user)
    except otp.OtpTooManyRequests:
        raise HTTPException(status_code=429, detail="Too many codes requested. Please wait a few minutes and try again.")
    except otp.OtpSendError as e:
        print(f"[otp] could not send a code for {user.username!r}: {e}")
        raise HTTPException(status_code=503, detail="Could not send the code right now. Please try again in a minute.")


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect ID or password.")

    otp_token = _start_code(db, user)
    return schemas.LoginResponse(message="Code sent" + otp.where_text(user) + "." + otp.delivery_note(),
                                 otp_token=otp_token, otp_length=otp.otp_length())


@router.post("/verify-otp", response_model=schemas.TokenResponse)
def verify_otp_endpoint(payload: schemas.VerifyOtpRequest, db: Session = Depends(get_db)):
    try:
        username = otp.verify_otp(db, payload.otp_token, payload.code)
    except otp.OtpSendError as e:
        print(f"[otp] could not check a code: {e}")
        raise HTTPException(status_code=503, detail="Could not check the code right now. Please try again in a minute.")
    if not username:
        if otp.is_locked(db, payload.otp_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Too many wrong tries. Please sign in again.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect or expired code.")

    access_token = auth.create_access_token(username)
    return schemas.TokenResponse(access_token=access_token)


@router.post("/resend-otp", response_model=schemas.LoginResponse)
def resend_otp(payload: dict, db: Session = Depends(get_db)):
    """Body: {"otp_token": "..."} -- the token from the original /login call."""
    old = db.query(models.OtpCode).filter(models.OtpCode.token == payload.get("otp_token")).first()
    if not old:
        raise HTTPException(status_code=404, detail="Login attempt not found or already completed.")
    user = db.query(models.User).filter(models.User.username == old.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Login attempt not found or already completed.")
    new_token = _start_code(db, user)
    return schemas.LoginResponse(message="A new code has been sent" + otp.where_text(user) + "." + otp.delivery_note(),
                                 otp_token=new_token, otp_length=otp.otp_length())
