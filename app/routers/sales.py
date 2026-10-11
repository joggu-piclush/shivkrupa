"""
Sales Book (Module 1). Every other data-entry module (Cash, Expenses,
Production) is a near copy of this file's shape: list-with-filters, create,
update, delete, all gated by get_current_user.

Two things worth noting because they map straight to blueprint decisions:
  - `party_directory_upsert()` is what makes Module 8 (Smart Autofill) real:
    every time a sale is saved, we remember that party's address/mobile so
    it can be suggested next time, from ANY module that uses parties.
  - Sr. No. is computed server-side (max existing + 1) so it can never
    collide, even with two people saving at the same moment.
"""
from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/sales", tags=["sales"])


def party_directory_upsert(db: Session, name: str, address: str, mobile: str):
    if not name:
        return
    party = db.query(models.Party).filter(models.Party.name == name).first()
    if party:
        party.address = address or party.address
        party.mobile = mobile or party.mobile
    else:
        db.add(models.Party(name=name, address=address, mobile=mobile))


@router.get("", response_model=list[schemas.SaleOut])
def list_sales(
    date_from: Optional[Date] = None,
    date_to: Optional[Date] = None,
    party: Optional[str] = None,
    brick_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Sale)
    if date_from:
        q = q.filter(models.Sale.date >= date_from)
    if date_to:
        q = q.filter(models.Sale.date <= date_to)
    if party:
        q = q.filter(models.Sale.party_name == party)
    if brick_type:
        q = q.filter(models.Sale.brick_type == brick_type)
    return q.order_by(models.Sale.date.desc(), models.Sale.id.desc()).all()


@router.post("", response_model=schemas.SaleOut)
def create_sale(
    payload: schemas.SaleCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    max_sr = db.query(models.Sale).count()
    sr_no = str(max_sr + 1).zfill(3)
    sale = models.Sale(**payload.model_dump(), sr_no=sr_no, created_by=user.username)
    db.add(sale)
    party_directory_upsert(db, payload.party_name, payload.address, payload.mobile)
    db.commit()
    db.refresh(sale)
    return sale


@router.put("/{sale_id}", response_model=schemas.SaleOut)
def update_sale(
    sale_id: int,
    payload: schemas.SaleCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale entry not found.")
    for field, value in payload.model_dump().items():
        setattr(sale, field, value)
    party_directory_upsert(db, payload.party_name, payload.address, payload.mobile)
    db.commit()
    db.refresh(sale)
    return sale


@router.delete("/{sale_id}")
def delete_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale entry not found.")
    db.delete(sale)
    db.commit()
    return {"deleted": True, "id": sale_id}
