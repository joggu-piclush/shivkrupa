from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[schemas.ExpenseOut])
def list_expenses(
    date_from: Optional[Date] = None,
    date_to: Optional[Date] = None,
    particulars: Optional[str] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    q = db.query(models.Expense)
    if date_from:
        q = q.filter(models.Expense.date >= date_from)
    if date_to:
        q = q.filter(models.Expense.date <= date_to)
    if particulars:
        q = q.filter(models.Expense.particulars == particulars)
    return q.order_by(models.Expense.date.desc(), models.Expense.id.desc()).all()


@router.get("/particulars", response_model=list[str])
def list_particulars(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Distinct Particulars values seen so far -- this is what makes the filter
    dropdown and the autocomplete suggestion list grow on their own."""
    rows = db.query(models.Expense.particulars).distinct().all()
    return [r[0] for r in rows]


@router.get("/details", response_model=list[str])
def list_details(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Distinct Details values seen so far (labourer names / vehicle numbers) -- its
    own suggestion list, deliberately separate from the Party Directory (Module 8)."""
    rows = db.query(models.Expense.details).filter(models.Expense.details != "").distinct().all()
    return [r[0] for r in rows]


@router.post("", response_model=schemas.ExpenseOut)
def create_expense(
    payload: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    sr_no = str(db.query(models.Expense).count() + 1).zfill(3)
    entry = models.Expense(**payload.model_dump(), sr_no=sr_no, created_by=user.username)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=schemas.ExpenseOut)
def update_expense(
    entry_id: int,
    payload: schemas.ExpenseCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Expense).filter(models.Expense.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Expense entry not found.")
    for field, value in payload.model_dump().items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}")
def delete_expense(
    entry_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    entry = db.query(models.Expense).filter(models.Expense.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Expense entry not found.")
    db.delete(entry)
    db.commit()
    return {"deleted": True, "id": entry_id}
