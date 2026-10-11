"""
`get_current_user` is a FastAPI dependency. Any route that adds
`user: models.User = Depends(get_current_user)` to its function signature is
automatically protected -- FastAPI runs this first, and if it raises, the
route body never executes. This is the one gate every Sales/Cash/Expenses/
Production/Party request has to pass through, which is what makes Module 10
("no way to reach any module without completing both login steps") true for
the whole API, not just the login screen.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from . import models, auth
from .database import get_db

bearer_scheme = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        username = auth.decode_access_token(creds.credentials)
    except JWTError:
        raise unauthorized

    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise unauthorized
    return user
