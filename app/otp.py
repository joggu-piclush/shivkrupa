"""
OTP generation and verification, plus the SMS sending step.

IMPORTANT AND DELIBERATE: `send_otp_sms()` below does NOT send a real SMS.
I don't have an SMS provider account or API key for you, so I can't wire up
a real one -- and I'm not going to fake one that silently does nothing while
pretending to work. Instead it logs the code to your server's console, which
is exactly enough to develop and test the whole login flow yourself right
now.

When you're ready to send real SMS (see the cost breakdown we discussed --
roughly Rs. 0.10-0.20 per OTP via MSG91 or 2Factor.in):
  1. Sign up with the provider and complete DLT template registration
     (their onboarding walks you through this -- required by Indian law
     for transactional SMS).
  2. Put their API key in your .env file (see .env.example).
  3. Replace the body of send_otp_sms() with their API call. It's usually
     a single requests.post(...) -- their docs will have a copy-paste
     example.
Nothing else in this file needs to change.
"""
import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from . import models

OTP_LENGTH = int(os.environ.get("OTP_LENGTH", "4"))  # blueprint: 4 or 6, demo used 4
OTP_EXPIRE_MINUTES = 5


def generate_otp() -> str:
    return "".join(random.choices("0123456789", k=OTP_LENGTH))


def send_otp_sms(mobile: str, code: str):
    """Replace this function's body with a real SMS API call when you're ready. See module docstring."""
    print(f"\n[DEV MODE] OTP for {mobile}: {code}  (would be sent via SMS in production)\n")


def create_otp_for_user(db: Session, username: str, mobile: str) -> str:
    """Generates a code, stores it, 'sends' it, and returns the opaque otp_token."""
    code = generate_otp()
    token = secrets.token_urlsafe(24)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    entry = models.OtpCode(token=token, username=username, code=code, expires_at=expires_at)
    db.add(entry)
    db.commit()
    send_otp_sms(mobile, code)
    return token


def verify_otp(db: Session, otp_token: str, code: str) -> str | None:
    """Returns the username if the code is correct, unexpired, and unused. Otherwise None."""
    entry = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.token == otp_token, models.OtpCode.consumed == False)  # noqa: E712
        .first()
    )
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry.expires_at.replace(tzinfo=timezone.utc):
        return None
    if entry.code != code:
        return None
    entry.consumed = True
    db.commit()
    return entry.username
