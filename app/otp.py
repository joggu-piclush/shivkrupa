"""
OTP generation, sending and checking.

Two modes, chosen by the OTP_PROVIDER environment variable on the server:

  OTP_PROVIDER not set  -> DEV MODE (the default, and how it has worked so far).
      The server makes the code itself and prints it in the server log. Nothing
      is sent to anyone. Fine for testing, useless for real staff.

  OTP_PROVIDER=fast2sms -> REAL MODE. Fast2SMS makes the code, sends it on WhatsApp
      (SMS fallback is set up on their side if wanted) and later tells us whether
      the code typed in is right. We never see or store the real code.
      Needs two more variables:
          FAST2SMS_API_KEY   the key from Fast2SMS -> API Key page
          FAST2SMS_OTP_ID    the OTP ID from Fast2SMS -> Smart OTP (the template
                             whose first channel is WhatsApp)
      Neither value is ever written in this code or printed in the log.

Safety limits, in both modes:
  * A login attempt dies after MAX_WRONG_TRIES wrong codes (a 4-digit code could
    otherwise be guessed).
  * At most MAX_CODES_PER_WINDOW codes per person per WINDOW_MINUTES, which also
    stops anyone from running up the WhatsApp bill.
  * Asking for a new code cancels the older one.
"""
import json
import os
import random
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from . import models

OTP_EXPIRE_MINUTES = 5
MAX_WRONG_TRIES = 5
MAX_CODES_PER_WINDOW = 5
WINDOW_MINUTES = 10


class OtpSendError(Exception):
    """The code could not be sent (or checked) right now: provider down, no balance, bad setup..."""


class OtpTooManyRequests(Exception):
    """Too many codes asked for in a short time."""


def otp_length() -> int:
    """Digits in the code. Dev mode: OTP_LENGTH (default 4). Real mode: set OTP_LENGTH to
    whatever length the Fast2SMS template produces (the test message on your phone shows it).
    Kept between 4 and 6 so the login screen's boxes always fit."""
    try:
        n = int(os.environ.get("OTP_LENGTH", "4"))
    except ValueError:
        n = 4
    return max(4, min(6, n))


def provider() -> str:
    return os.environ.get("OTP_PROVIDER", "").strip().lower()


def delivery_channel_text() -> str:
    """Words for the login message, e.g. 'on WhatsApp'."""
    return "on WhatsApp" if provider() == "fast2sms" else ""


def generate_otp() -> str:
    return "".join(random.SystemRandom().choices("0123456789", k=otp_length()))


def _clean_mobile(mobile: str) -> str:
    """Fast2SMS wants the plain 10-digit Indian number: drop +91, spaces, dashes."""
    return re.sub(r"\D", "", mobile or "")[-10:]


# ---------------------------------------------------------------------------
# Fast2SMS
# ---------------------------------------------------------------------------
def _fast2sms_post(path: str, body: dict) -> dict:
    key = os.environ.get("FAST2SMS_API_KEY", "").strip()
    if not key:
        raise OtpSendError("FAST2SMS_API_KEY is not set on the server.")
    base = os.environ.get("FAST2SMS_BASE_URL", "https://www.fast2sms.com").rstrip("/")
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        # Say plainly who is calling. Python's built-in default ("Python-urllib/3.x") is turned away
        # by Fast2SMS's Cloudflare shield (error 1010), so every code request was refused.
        headers={"Authorization": key, "Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "ShivkrupaEnterprises-App/1.0 (login OTP)"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:   # the provider answered with an error status; its body may still say why
        raw = e.read()
    except Exception as e:                # no connection, timeout...
        raise OtpSendError(f"Could not reach Fast2SMS ({type(e).__name__}).")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _fast2sms_send(mobile: str) -> None:
    otp_id = os.environ.get("FAST2SMS_OTP_ID", "").strip()
    if not otp_id:
        raise OtpSendError("FAST2SMS_OTP_ID is not set on the server.")
    resp = _fast2sms_post("/dev/otp/send", {"otp_id": otp_id, "mobile": _clean_mobile(mobile)})
    if resp.get("return") is not True:
        # Log only the provider's own reason (never the key or any code).
        print(f"[otp] Fast2SMS did not send the code: {resp.get('message') or resp or 'no reply'}")
        raise OtpSendError("Fast2SMS refused to send the code.")
    # Only the provider's own status words are logged -- never the key, the number or any code.
    print(f"[otp] Fast2SMS accepted the request: message={resp.get('message')!r} request_id={resp.get('request_id')!r} fields={sorted(resp)}")


def _fast2sms_check(mobile: str, code: str) -> bool:
    resp = _fast2sms_post("/dev/otp/verify", {"mobile": _clean_mobile(mobile), "otp": code})
    ok = resp.get("return") is True
    print(f"[otp] Fast2SMS code check: {'accepted' if ok else 'rejected'} (message={resp.get('message')!r}, status_code={resp.get('status_code')!r})")
    return ok


# ---------------------------------------------------------------------------
# Public functions used by the login routes
# ---------------------------------------------------------------------------
def send_otp_sms(mobile: str, code: str):
    """DEV MODE only: prints the code in the server log instead of sending it."""
    print(f"\n[DEV MODE] OTP for {mobile}: {code}  (not sent to anyone; set OTP_PROVIDER to send for real)\n")


def create_otp_for_user(db: Session, username: str, mobile: str) -> str:
    """Starts a login attempt: sends a code and returns the opaque otp_token.
    Raises OtpTooManyRequests or OtpSendError (nothing is left half-done in either case)."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=WINDOW_MINUTES)
    recent = (db.query(models.OtpCode)
              .filter(models.OtpCode.username == username, models.OtpCode.created_at >= window_start.replace(tzinfo=None))
              .count())
    if recent >= MAX_CODES_PER_WINDOW:
        raise OtpTooManyRequests()

    real = provider() == "fast2sms"
    code = "" if real else generate_otp()          # in real mode Fast2SMS holds the code, not us
    token = secrets.token_urlsafe(24)

    if real:
        _fast2sms_send(mobile)                     # raises OtpSendError -> nothing stored, nothing cancelled

    # A new code cancels any older unused one for this person.
    for old in db.query(models.OtpCode).filter(models.OtpCode.username == username, models.OtpCode.consumed == False).all():  # noqa: E712
        old.consumed = True
    db.add(models.OtpCode(token=token, username=username, code=code,
                          expires_at=now + timedelta(minutes=OTP_EXPIRE_MINUTES)))
    db.commit()
    if not real:
        send_otp_sms(mobile, code)
    return token


def _entry_for_token(db: Session, otp_token: str):
    return db.query(models.OtpCode).filter(models.OtpCode.token == otp_token).first()


def is_locked(db: Session, otp_token: str) -> bool:
    """True once a login attempt has used up its wrong tries."""
    entry = _entry_for_token(db, otp_token)
    return bool(entry and (entry.attempts or 0) >= MAX_WRONG_TRIES)


def verify_otp(db: Session, otp_token: str, code: str) -> str | None:
    """Returns the username if the code is correct, unexpired and unused. Otherwise None.
    Raises OtpSendError only when the provider could not be asked (nothing is counted then)."""
    entry = (
        db.query(models.OtpCode)
        .filter(models.OtpCode.token == otp_token, models.OtpCode.consumed == False)  # noqa: E712
        .first()
    )
    if not entry:
        return None
    if datetime.now(timezone.utc) > entry.expires_at.replace(tzinfo=timezone.utc):
        return None
    if (entry.attempts or 0) >= MAX_WRONG_TRIES:
        return None

    code = (code or "").strip()
    if not code.isdigit() or len(code) > 8:
        ok = False
    elif entry.code:                               # dev mode: we hold the code
        ok = secrets.compare_digest(entry.code, code)
    elif provider() == "fast2sms":                 # real mode: ask Fast2SMS
        user = db.query(models.User).filter(models.User.username == entry.username).first()
        ok = bool(user) and _fast2sms_check(user.mobile, code)
    else:
        ok = False

    if not ok:
        entry.attempts = (entry.attempts or 0) + 1
        db.commit()
        return None
    entry.consumed = True
    db.commit()
    return entry.username
