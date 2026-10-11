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


@router.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect ID or password.")

    otp_token = otp.create_otp_for_user(db, user.username, user.mobile)
    return schemas.LoginResponse(message="OTP sent to your registered mobile number.", otp_token=otp_token)


@router.post("/verify-otp", response_model=schemas.TokenResponse)
def verify_otp_endpoint(payload: schemas.VerifyOtpRequest, db: Session = Depends(get_db)):
    username = otp.verify_otp(db, payload.otp_token, payload.code)
    if not username:
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
    new_token = otp.create_otp_for_user(db, user.username, user.mobile)
    return schemas.LoginResponse(message="A new code has been sent.", otp_token=new_token)
