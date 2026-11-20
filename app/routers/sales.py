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

from .. import models, schemas, textfix
from ..database import get_db
from ..deps import get_current_user
from .parties import prune_party_if_unused

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


def tidy_remark(text: str) -> str:
    """A remark as it is shown in the drop-down: spaces squeezed to single ones and the first letter of every
    word raised ('deliver  tomorrow' -> 'Deliver Tomorrow'). It only ever raises letters, never lowers, so 'UPI' stays 'UPI'."""
    return textfix.capitalize_words(" ".join((text or "").split()))


REMARKS_LIST_LIMIT = 300  # a drop-down with thousands of lines is no use to anyone


@router.get("/remarks", response_model=list[str])
def list_remarks(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Every distinct remark used on a sale, for the Remarks drop-down -- most used first, then most recent.
    Nothing extra is stored: it is read from the sales themselves, so a new remark appears the moment a sale
    with it is saved, and goes away only if every sale using it is deleted. 'urgent', 'Urgent ' and 'URGENT'
    count as one remark (shown with the most recent spelling)."""
    rows = (
        db.query(models.Sale.remarks, models.Sale.date, models.Sale.id)
        .filter(models.Sale.remarks != "")
        .order_by(models.Sale.date, models.Sale.id)  # oldest first, so the last spelling seen is the newest
        .all()
    )
    seen = {}  # remark lower-cased -> [times used, order last used, spelling]
    for order, (remark, _date, _id) in enumerate(rows):
        shown = tidy_remark(remark)
        if not shown:
            continue
        entry = seen.setdefault(shown.casefold(), [0, 0, shown])
        entry[0] += 1
        entry[1] = order
        entry[2] = shown
    ranked = sorted(seen.values(), key=lambda e: (-e[0], -e[1]))
    return [e[2] for e in ranked[:REMARKS_LIST_LIMIT]]


@router.post("", response_model=schemas.SaleOut)
def create_sale(
    payload: schemas.SaleCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payload = textfix.tidy(payload, "party_name", "address", "remarks")  # saved with capitals on every word
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
    payload = textfix.tidy(payload, "party_name", "address", "remarks")  # saved with capitals on every word
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale entry not found.")
    old_party = sale.party_name
    for field, value in payload.model_dump().items():
        setattr(sale, field, value)
    party_directory_upsert(db, payload.party_name, payload.address, payload.mobile)
    if old_party != payload.party_name:  # renamed: the old name goes if nothing else uses it
        db.flush()
        prune_party_if_unused(db, old_party)
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
    party_name = sale.party_name
    db.delete(sale)
    db.flush()
    prune_party_if_unused(db, party_name)  # that was the party's last entry? then its Ledger card goes too
    db.commit()
    return {"deleted": True, "id": sale_id}
