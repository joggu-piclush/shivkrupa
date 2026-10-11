from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from .sales import party_directory_upsert

router = APIRouter(prefix="/cash", tags=["cash"])


@router.get("/modes", response_model=list[str])
def list_modes(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Distinct Mode of Payment values seen so far, for the auto-updating filter."""
    rows = db.query(models.CashEntry.mode).distinct().all()
    return [r[0] for r in rows]


@router.get("", response_model=list[schemas.CashEntryOut])
def list_cash(
    date_from: Optional[Date] = None,
    date_to: Optional[Date] = None,
    party: Optional[str] = None,
    mode: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.CashEntry)
    if date_from:
        q = q.filter(models.CashEntry.date >= date_from)
    if date_to:
        q = q.filter(models.CashEntry.date <= date_to)
    if party:
        q = q.filter(models.CashEntry.name == party)
    if mode:
        q = q.filter(models.CashEntry.mode == mode)
    return q.order_by(models.CashEntry.date.desc(), models.CashEntry.id.desc()).all()


@router.post("", response_model=schemas.CashEntryOut)
def create_cash(
    payload: schemas.CashEntryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = models.CashEntry(**payload.model_dump(), created_by=user.username)
    db.add(entry)
    party_directory_upsert(db, payload.name, payload.address, payload.mobile)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.CashEntryOut)
def update_cash(
    entry_id: int,
    payload: schemas.CashEntryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.CashEntry).filter(models.CashEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cash entry not found.")
    for field, value in payload.model_dump().items():
        setattr(entry, field, value)
    party_directory_upsert(db, payload.name, payload.address, payload.mobile)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_cash(
    entry_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.CashEntry).filter(models.CashEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Cash entry not found.")
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": entry_id}
