"""
OTP generation, sending and checking.

Three modes, chosen by the OTP_PROVIDER environment variable on the server:

  OTP_PROVIDER not set (or "dev") -> DEV MODE (the default, and how it has worked so far).
      The server makes the code itself and prints it in the server log. Nothing
      is sent to anyone. Fine for testing, useless for real staff.

  OTP_PROVIDER=email    -> EMAIL MODE. The server makes the code and emails it through
      Resend (resend.com, free for this volume). Needs:
          RESEND_API_KEY     the key from the Resend dashboard (secret: set it only on the server)
          OTP_EMAIL_FROM     who the email comes from, e.g. "Shivkrupa Enterprises <login@piclush.in>".
                             Defaults to Resend's test sender, which can only mail the Resend account owner.
          SEED_ADMIN_EMAIL   the address that receives the login's code
      The code is stored only as a hash and is never printed in the log.

  OTP_PROVIDER=fast2sms -> WHATSAPP MODE. Fast2SMS makes the code, sends it on WhatsApp
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
import hashlib
import hmac
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


KNOWN_PROVIDERS = ("", "dev", "email", "fast2sms")


def provider() -> str:
    return os.environ.get("OTP_PROVIDER", "").strip().lower()


def mask_email(email: str) -> str:
    """'aryan@piclush.in' -> 'a***@piclush.in' (the login screen never shows the whole address)."""
    email = (email or "").strip()
    if "@" not in email:
        return "your email"
    local, _, domain = email.rpartition("@")
    return (local[:1] + "***") + "@" + domain


def where_text(user) -> str:
    """Words for the login message, e.g. ' by email to a***@piclush.in' (never shows a whole address or number)."""
    prov = provider()
    if prov == "email":
        return " by email to " + mask_email(user.email)
    tail = "".join(ch for ch in (user.mobile or "") if ch.isdigit())[-4:]
    channel = " on WhatsApp" if prov == "fast2sms" else ""
    return channel + (f" to your number ending {tail}" if tail else " to your registered number")


def delivery_note() -> str:
    """Extra advice appended to the login message."""
    return " If you don't see it, check your Spam folder." if provider() == "email" else ""


def generate_otp() -> str:
    return "".join(random.SystemRandom().choices("0123456789", k=otp_length()))


def _clean_mobile(mobile: str) -> str:
    """Fast2SMS wants the plain 10-digit Indian number: drop +91, spaces, dashes."""
    return re.sub(r"\D", "", mobile or "")[-10:]


def _hash_code(code: str) -> str:
    """Emailed codes are kept only as a keyed hash, so a copy of the database never shows a usable code."""
    key = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me").encode("utf-8")
    return "h$" + hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


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
# Email (Resend)
# ---------------------------------------------------------------------------
_EMAIL_SHAPE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$")


def _send_email_code(to_email: str, code: str) -> None:
    """Emails the code through Resend's web API (Railway's cheaper plans block ordinary email ports,
    so a web API is the way). Raises OtpSendError with a plain reason; nothing secret goes in the message."""
    key = os.environ.get("RESEND_API_KEY", "").strip()
    if not key:
        raise OtpSendError("RESEND_API_KEY is not set on the server.")
    to_email = (to_email or "").strip()
    if not _EMAIL_SHAPE.match(to_email):
        raise OtpSendError("This login has no valid email address (set SEED_ADMIN_EMAIL on the server).")
    sender = os.environ.get("OTP_EMAIL_FROM", "").strip() or "Shivkrupa Enterprises <onboarding@resend.dev>"
    base = os.environ.get("RESEND_BASE_URL", "https://api.resend.com").rstrip("/")
    minutes = OTP_EXPIRE_MINUTES
    text = (f"Your Shivkrupa Enterprises login code is {code}\n\n"
            f"It works for {minutes} minutes. Type it on the sign-in screen.\n\n"
            "If you did not try to sign in, ignore this email. Never share this code with anyone.\n")
    html = (f'<div style="font-family:Arial,sans-serif;max-width:420px;margin:auto;padding:24px;color:#222">'
            f'<p style="margin:0 0 8px">Your Shivkrupa Enterprises login code is</p>'
            f'<p style="font-size:34px;letter-spacing:8px;font-weight:bold;margin:8px 0 16px">{code}</p>'
            f'<p style="margin:0 0 8px;color:#555">It works for {minutes} minutes. Type it on the sign-in screen.</p>'
            f'<p style="margin:0;color:#888;font-size:13px">If you did not try to sign in, ignore this email. '
            f'Never share this code with anyone.</p></div>')
    body = {"from": sender, "to": [to_email], "subject": "Your Shivkrupa Enterprises login code", "text": text, "html": html}
    req = urllib.request.Request(
        base + "/emails",
        data=json.dumps(body).encode("utf-8"),
        # Resend refuses requests without a User-Agent, so say plainly who is calling.
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": "ShivkrupaEnterprises-App/1.0 (login OTP)"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:   # Resend answered with an error; its body says why
        raw = e.read()
        try:
            err = json.loads(raw)
        except ValueError:
            err = {}
        reason = (err.get("message") if isinstance(err, dict) else None) or f"HTTP {e.code}"
        print(f"[otp] Resend did not send the email (HTTP {e.code}): {reason}")
        raise OtpSendError("Resend refused to send the email.")
    except Exception as e:                # no connection, timeout...
        raise OtpSendError(f"Could not reach Resend ({type(e).__name__}).")
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    print(f"[otp] Email code handed to Resend for {mask_email(to_email)} (id={data.get('id') if isinstance(data, dict) else None!r})")


# ---------------------------------------------------------------------------
# Public functions used by the login routes
# ---------------------------------------------------------------------------
def send_otp_sms(mobile: str, code: str):
    """DEV MODE only: prints the code in the server log instead of sending it."""
    print(f"\n[DEV MODE] OTP for {mobile}: {code}  (not sent to anyone; set OTP_PROVIDER to send for real)\n")


def create_otp_for_user(db: Session, user: "models.User") -> str:
    """Starts a login attempt: sends a code and returns the opaque otp_token.
    Raises OtpTooManyRequests or OtpSendError (nothing is left half-done in either case)."""
    username, mobile = user.username, user.mobile
    prov = provider()
    if prov not in KNOWN_PROVIDERS:               # a typo must never quietly fall back to printing codes in the log
        raise OtpSendError(f"OTP_PROVIDER has an unknown value ({prov!r}); use email, fast2sms or leave it unset.")
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=WINDOW_MINUTES)
    recent = (db.query(models.OtpCode)
              .filter(models.OtpCode.username == username, models.OtpCode.created_at >= window_start.replace(tzinfo=None))
              .count())
    if recent >= MAX_CODES_PER_WINDOW:
        raise OtpTooManyRequests()

    dev = prov in ("", "dev")
    token = secrets.token_urlsafe(24)
    if prov == "fast2sms":
        stored = ""                                # Fast2SMS holds the code, not us
        _fast2sms_send(mobile)                     # raises OtpSendError -> nothing stored, nothing cancelled
    elif prov == "email":
        code = generate_otp()
        _send_email_code(user.email, code)         # raises OtpSendError -> nothing stored, nothing cancelled
        stored = _hash_code(code)                  # only a hash is kept
    else:
        code = stored = generate_otp()             # dev mode: plain code, printed below

    # A new code cancels any older unused one for this person.
    for old in db.query(models.OtpCode).filter(models.OtpCode.username == username, models.OtpCode.consumed == False).all():  # noqa: E712
        old.consumed = True
    db.add(models.OtpCode(token=token, username=username, code=stored,
                          expires_at=now + timedelta(minutes=OTP_EXPIRE_MINUTES)))
    db.commit()
    if dev:
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
    elif entry.code.startswith("h$"):              # email mode: we hold only a hash of the code
        ok = secrets.compare_digest(entry.code, _hash_code(code))
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
