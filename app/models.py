"""
One class per table. Each maps directly to a module from the blueprint:

  User         -> logins (Module 10)
  Party        -> the shared Party Directory (Module 8)
  Sale         -> Sales Book (Module 1)
  CashEntry    -> Cash Book (Module 2)
  Expense      -> Expenses Book (Module 3)
  Production   -> Factory Production Tracker (Module 5)
  RawMaterial  -> Raw Materials Book (new module, sits between Production and Stock)
  OtpCode      -> the one-time codes issued during login (Module 10)

Ledger, Stock, and Reports have NO table of their own -- exactly like the
mockup, they are computed on the fly from Sale / CashEntry / Expense /
Production. That was a deliberate design decision in the blueprint ("derived
report, not a form"), and it carries straight through into the real database:
there is nothing to keep in sync, because there's nothing duplicated.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Boolean
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    mobile = Column(String, nullable=False)
    role = Column(String, default="admin")  # admin | office_staff | supervisor
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Party(Base):
    __tablename__ = "parties"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    address = Column(String, default="")
    mobile = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Sale(Base):
    __tablename__ = "sales"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    sr_no = Column(String, nullable=False)
    party_name = Column(String, nullable=False, index=True)
    address = Column(String, default="")
    mobile = Column(String, default="")
    brick_type = Column(String, nullable=False, default="4 inch")  # "4 inch" | "6 inch"
    quantity = Column(Float, nullable=False)
    total_value = Column(Float, nullable=False)
    carting_by = Column(String, default="Party")  # "Party" | "Company"
    carting_value = Column(Float, default=0)
    created_by = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CashEntry(Base):
    __tablename__ = "cash_entries"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    name = Column(String, nullable=False, index=True)
    address = Column(String, default="")
    mobile = Column(String, default="")
    amount = Column(Float, nullable=False)
    mode = Column(String, nullable=False)  # Cash | UPI | Bank Transfer | ...
    created_by = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    sr_no = Column(String, nullable=False)
    particulars = Column(String, nullable=False, index=True)
    details = Column(String, default="")
    amount = Column(Float, nullable=False)
    created_by = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Production(Base):
    __tablename__ = "production"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    brick_type = Column(String, nullable=False, default="4 inch")  # "4 inch" | "6 inch"
    pallets = Column(Float, nullable=False)
    bricks = Column(Float, nullable=False)  # pallets * pallet size FOR THIS brick_type
    cement_bags = Column(Float, nullable=False, default=0, server_default="0")  # cement bags used for this batch
    entered_by = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def average(self):
        """Bricks per cement bag -- calculated on the fly, never stored (see calc.py)."""
        from .calc import average_for
        return average_for(self.brick_type, self.pallets, self.cement_bags)


class RawMaterial(Base):
    __tablename__ = "raw_materials"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    sr_no = Column(String, nullable=False)
    material = Column(String, nullable=False, index=True)  # e.g. "Cement", "Sand", "Coal"
    quantity = Column(Float, nullable=False)
    # No longer asked for in the app (quantity is just a number now). Column is kept so
    # older entries that already have a unit keep it; new entries store "".
    unit = Column(String, nullable=False, default="", server_default="")
    cost = Column(Float, nullable=False)
    supplier = Column(String, default="")  # who supplied it -- own suggestion list, not the Party Directory
    created_by = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, index=True, nullable=False)  # opaque ref to this login attempt
    username = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
