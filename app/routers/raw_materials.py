"""
Raw Materials Book -- new module the client asked for, positioned between
Production and Stock. Logs raw materials arriving at the factory (cement,
sand, coal, etc.).

Three separate suggestion lists, deliberately NOT sharing the Party
Directory -- a cement supplier is not a sales customer, same reasoning as
Expenses' Details field:
  - Material  (what arrived: Cement, Sand, Coal...)
  - Unit      (how it's counted: Truck, Bag... most materials are truck-wise,
               cement is specifically bag-wise, but this is just free text
               with suggestions, not a hardcoded rule, in case that changes)
  - Supplier  (who delivered it)
"""
from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/raw-materials", tags=["raw-materials"])


@router.get("", response_model=list[schemas.RawMaterialOut])
def list_raw_materials(
    date_from: Optional[Date] = None,
    date_to: Optional[Date] = None,
    material: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.RawMaterial)
    if date_from:
        q = q.filter(models.RawMaterial.date >= date_from)
    if date_to:
        q = q.filter(models.RawMaterial.date <= date_to)
    if material:
        q = q.filter(models.RawMaterial.material == material)
    return q.order_by(models.RawMaterial.date.desc(), models.RawMaterial.id.desc()).all()


@router.get("/materials", response_model=list[str])
def list_materials(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return [r[0] for r in db.query(models.RawMaterial.material).distinct().all()]


@router.get("/units", response_model=list[str])
def list_units(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = [r[0] for r in db.query(models.RawMaterial.unit).distinct().all()]
    for default in ("Truck", "Bag"):
        if default not in rows:
            rows.append(default)
    return sorted(rows)


@router.get("/suppliers", response_model=list[str])
def list_suppliers(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    return [r[0] for r in db.query(models.RawMaterial.supplier).filter(models.RawMaterial.supplier != "").distinct().all()]


@router.post("", response_model=schemas.RawMaterialOut)
def create_raw_material(
    payload: schemas.RawMaterialCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sr_no = str(db.query(models.RawMaterial).count() + 1).zfill(3)
    entry = models.RawMaterial(**payload.model_dump(), sr_no=sr_no, created_by=user.username)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.RawMaterialOut)
def update_raw_material(
    entry_id: int,
    payload: schemas.RawMaterialCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.RawMaterial).filter(models.RawMaterial.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Raw material entry not found.")
    for field, value in payload.model_dump().items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_raw_material(
    entry_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.RawMaterial).filter(models.RawMaterial.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Raw material entry not found.")
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": entry_id}
