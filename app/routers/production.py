"""
Production Tracker (Module 5). Bricks is never taken from the client's
request -- it's always recalculated here as pallets * PALLET_SIZE[brick_type],
so the two numbers can never disagree.

PALLET_SIZE is now a lookup, not a single constant, because the client's
factory makes two different bricks with two different pallet yields:
  - 4 inch brick -> 100 bricks per pallet
  - 6 inch brick -> 66 bricks per pallet
If a third size is ever added, this dict is the only place that needs to
change -- nothing else in the app hardcodes a pallet size.
"""
from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/production", tags=["production"])

PALLET_SIZE = {"4 inch": 100, "6 inch": 66}
BRICK_TYPES = list(PALLET_SIZE.keys())


def bricks_for(brick_type: str, pallets: float) -> float:
    if brick_type not in PALLET_SIZE:
        raise HTTPException(status_code=400, detail=f"Unknown brick type '{brick_type}'. Expected one of {BRICK_TYPES}.")
    return pallets * PALLET_SIZE[brick_type]


@router.get("/brick-types", response_model=list[str])
def list_brick_types(user: models.User = Depends(get_current_user)):
    return BRICK_TYPES


@router.get("", response_model=list[schemas.ProductionOut])
def list_production(
    date_from: Optional[Date] = None,
    date_to: Optional[Date] = None,
    brick_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Production)
    if date_from:
        q = q.filter(models.Production.date >= date_from)
    if date_to:
        q = q.filter(models.Production.date <= date_to)
    if brick_type:
        q = q.filter(models.Production.brick_type == brick_type)
    return q.order_by(models.Production.date.desc(), models.Production.id.desc()).all()


@router.post("", response_model=schemas.ProductionOut)
def create_production(
    payload: schemas.ProductionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = models.Production(
        date=payload.date, brick_type=payload.brick_type, pallets=payload.pallets,
        bricks=bricks_for(payload.brick_type, payload.pallets), cement_bags=payload.cement_bags,
        entered_by=payload.entered_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.ProductionOut)
def update_production(
    entry_id: int,
    payload: schemas.ProductionCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Production).filter(models.Production.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Production entry not found.")
    entry.date = payload.date
    entry.brick_type = payload.brick_type
    entry.pallets = payload.pallets
    entry.bricks = bricks_for(payload.brick_type, payload.pallets)
    entry.cement_bags = payload.cement_bags
    entry.entered_by = payload.entered_by
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_production(
    entry_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Production).filter(models.Production.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Production entry not found.")
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": entry_id}
