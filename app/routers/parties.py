from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/parties", tags=["parties"])


@router.get("", response_model=list[schemas.PartyOut])
def list_parties(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The whole Party Directory -- the frontend uses this to populate the
    autocomplete suggestion list on Sales Book and Cash Book (Module 8)."""
    return db.query(models.Party).order_by(models.Party.name).all()
