"""
Ledger (Module 4), Stock (Module 6), and Reports (Module 7). None of these
have a database table -- exactly as the blueprint specifies ("derived
report, not a form"). Every number here is computed, on request, from Sale /
CashEntry / Expense / Production.

One real open question baked into /stock: the running total below starts
counting from zero at the very first Production/Sale record in the database.
On day one of using this software, if the factory already has physical stock
sitting in the yard, that existing stock needs to be entered as a starting
point -- otherwise the app will show less stock than actually exists until
enough new production catches up. Worth raising with the client before
go-live; a simple fix is a one-time "opening balance" entry, which isn't
built yet.
"""
from datetime import date as Date
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(tags=["reports"])


def _party_ledger_txns(db: Session, party: str, date_from=None, date_to=None):
    sales_q = db.query(models.Sale).filter(models.Sale.party_name == party)
    cash_q = db.query(models.CashEntry).filter(models.CashEntry.name == party)
    if date_from:
        sales_q = sales_q.filter(models.Sale.date >= date_from)
        cash_q = cash_q.filter(models.CashEntry.date >= date_from)
    if date_to:
        sales_q = sales_q.filter(models.Sale.date <= date_to)
        cash_q = cash_q.filter(models.CashEntry.date <= date_to)

    rows = []
    for s in sales_q.all():
        rows.append({
            "date": s.date, "particulars": f"{s.quantity:g} bricks taken ({s.brick_type})",
            "debit": s.total_value, "credit": 0.0, "_seq": (s.date, 0, s.id),
        })
    for c in cash_q.all():
        rows.append({
            "date": c.date, "particulars": f"Payment received ({c.mode})",
            "debit": 0.0, "credit": c.amount, "_seq": (c.date, 1, c.id),
        })
    rows.sort(key=lambda r: r["_seq"])
    running = 0.0
    out = []
    for r in rows:
        running += r["debit"] - r["credit"]
        out.append({"date": r["date"], "particulars": r["particulars"],
                     "debit": r["debit"], "credit": r["credit"], "balance": running})
    return out


@router.get("/ledger/summary")
def ledger_summary(
    date_from: Optional[Date] = None, date_to: Optional[Date] = None,
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user),
):
    parties = {p.name for p in db.query(models.Party).all()}
    result = []
    for name in sorted(parties):
        txns = _party_ledger_txns(db, name, date_from, date_to)
        balance = txns[-1]["balance"] if txns else 0.0
        result.append({"party": name, "balance": balance, "entries": len(txns)})
    return result


@router.get("/ledger/{party_name}")
def ledger_detail(
    party_name: str, date_from: Optional[Date] = None, date_to: Optional[Date] = None,
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user),
):
    return _party_ledger_txns(db, party_name, date_from, date_to)


@router.get("/stock")
def stock(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """Split per brick type -- '500 four-inch + 300 six-inch' can't be added into
    one meaningful number, since they're different physical products. Each type
    gets its own produced/sold/current-stock figures."""
    brick_types = {r[0] for r in db.query(models.Production.brick_type).distinct().all()} | \
                  {r[0] for r in db.query(models.Sale.brick_type).distinct().all()}
    result = []
    for bt in sorted(brick_types) or ["4 inch", "6 inch"]:
        produced = sum(r.bricks for r in db.query(models.Production).filter(models.Production.brick_type == bt).all())
        sold = sum(r.quantity for r in db.query(models.Sale).filter(models.Sale.brick_type == bt).all())
        result.append({"brick_type": bt, "current_stock": produced - sold, "total_produced": produced, "total_sold": sold})
    return result


@router.get("/stock/trend")
def stock_trend(
    date_from: Date, date_to: Date, brick_type: str = "4 inch",
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user),
):
    """Closing stock for each day in range, for ONE brick type at a time --
    powers the bar chart. Computed the same way as /stock, just accumulated
    one day at a time."""
    from datetime import timedelta
    base_produced = sum(r.bricks for r in db.query(models.Production).filter(
        models.Production.date < date_from, models.Production.brick_type == brick_type).all())
    base_sold = sum(r.quantity for r in db.query(models.Sale).filter(
        models.Sale.date < date_from, models.Sale.brick_type == brick_type).all())
    running_produced, running_sold = base_produced, base_sold
    results, current = [], date_from
    while current <= date_to:
        running_produced += sum(r.bricks for r in db.query(models.Production).filter(
            models.Production.date == current, models.Production.brick_type == brick_type).all())
        running_sold += sum(r.quantity for r in db.query(models.Sale).filter(
            models.Sale.date == current, models.Sale.brick_type == brick_type).all())
        results.append({"date": current.isoformat(), "closing": running_produced - running_sold})
        current += timedelta(days=1)
    return results


@router.get("/reports/dashboard")
def dashboard(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """bricks_produced_today / bricks_sold_today are combined across BOTH brick
    types -- fine as a rough 'how much did we move today' headline number, but
    for anything where the brick type actually matters, use /stock (split by
    type) or the Production/Sales lists themselves."""
    today = Date.today()

    def sum_col(model, col, **filters):
        q = db.query(model).filter(model.date == today)
        for k, v in filters.items():
            q = q.filter(getattr(model, k) == v)
        return sum(getattr(row, col) for row in q.all())

    return {
        "date": today.isoformat(),
        "bricks_produced_today": sum_col(models.Production, "bricks"),
        "bricks_sold_today": sum_col(models.Sale, "quantity"),
        "cash_received_today": sum_col(models.CashEntry, "amount"),
        "expenses_today": sum_col(models.Expense, "amount"),
    }


@router.get("/reports/monthly")
def monthly_report(
    year: Optional[int] = None, month: Optional[int] = None,
    db: Session = Depends(get_db), user: models.User = Depends(get_current_user),
):
    today = Date.today()
    year = year or today.year
    month = month or today.month
    start = Date(year, month, 1)
    end = Date(year + (month == 12), (month % 12) + 1, 1)

    def month_rows(model):
        return db.query(model).filter(model.date >= start, model.date < end).all()

    sales_rows = month_rows(models.Sale)
    prod_rows = month_rows(models.Production)
    cash_rows = month_rows(models.CashEntry)
    exp_rows = month_rows(models.Expense)
    raw_rows = month_rows(models.RawMaterial)
    ledger = ledger_summary(date_from=None, date_to=None, db=db, user=user)  # all-time outstanding

    return {
        "period": start.strftime("%B %Y"),
        "sales_this_month": sum(r.total_value for r in sales_rows),
        "bricks_produced": sum(r.bricks for r in prod_rows),
        "bricks_sold": sum(r.quantity for r in sales_rows),
        "cash_received": sum(r.amount for r in cash_rows),
        "outstanding_credit": sum(p["balance"] for p in ledger if p["balance"] > 0),
        "labor_fuel_expenses": sum(r.amount for r in exp_rows),
        "raw_material_cost": sum(r.cost for r in raw_rows),
    }
