"""
Two jobs live here:

1. Password hashing -- we NEVER store a password as typed. `hash_password`
   runs it through bcrypt (one-way; the original can't be recovered from the
   hash), and `verify_password` checks a login attempt against that hash.

2. JWT access tokens -- once someone is fully logged in (password + OTP both
   correct), we hand them a signed token. Every later request must include
   that token; `decode_access_token` checks its signature and expiry. If
   someone tampers with the token or it's expired, this raises and the
   request gets rejected.

SECRET_KEY must be a long random string, set via an environment variable in
production -- never hardcoded and never committed to git. The fallback below
is ONLY for local development on your own machine.
"""
import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", "24"))


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the username if the token is valid; raises JWTError otherwise."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]
