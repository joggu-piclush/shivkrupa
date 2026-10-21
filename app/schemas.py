"""
Pydantic schemas: the "shape" of every request body and response.

FastAPI checks incoming JSON against these automatically -- if a request is
missing a required field or sends text where a number belongs, the API
rejects it with a clear error before your code even runs. This is most of
what makes FastAPI worth using over writing raw request-parsing by hand.
"""
from pydantic import BaseModel
from datetime import date as Date, datetime
from typing import Optional


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    message: str
    otp_token: str  # short-lived reference to this login attempt; NOT an access token


class VerifyOtpRequest(BaseModel):
    otp_token: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Party Directory (Module 8) ----------
class PartyOut(BaseModel):
    name: str
    address: str
    mobile: str
    model_config = {"from_attributes": True}


# ---------- Sales Book (Module 1) ----------
class SaleCreate(BaseModel):
    date: Date
    party_name: str
    address: str = ""
    mobile: str = ""
    brick_type: str = "4 inch"  # "4 inch" | "6 inch"
    quantity: float
    total_value: float
    carting_by: str = "Party"
    carting_value: float = 0


class SaleOut(SaleCreate):
    id: int
    sr_no: str
    model_config = {"from_attributes": True}


# ---------- Cash Book (Module 2) ----------
class CashEntryCreate(BaseModel):
    date: Date
    name: str
    address: str = ""
    mobile: str = ""
    amount: float
    mode: str


class CashEntryOut(CashEntryCreate):
    id: int
    model_config = {"from_attributes": True}


# ---------- Expenses Book (Module 3) ----------
class ExpenseCreate(BaseModel):
    date: Date
    particulars: str
    details: str = ""
    amount: float


class ExpenseOut(ExpenseCreate):
    id: int
    sr_no: str
    model_config = {"from_attributes": True}


# ---------- Production Tracker (Module 5) ----------
class ProductionCreate(BaseModel):
    date: Date
    brick_type: str = "4 inch"  # "4 inch" | "6 inch"
    pallets: float
    cement_bags: float = 0
    entered_by: str


class ProductionOut(BaseModel):
    id: int
    date: Date
    brick_type: str
    pallets: float
    bricks: float
    cement_bags: float = 0
    entered_by: str
    model_config = {"from_attributes": True}


# ---------- Raw Materials Book (new module) ----------
class RawMaterialCreate(BaseModel):
    date: Date
    material: str
    quantity: float
    unit: str = ""  # no longer used by the app; kept so older entries still load
    cost: float
    supplier: str = ""


class RawMaterialOut(RawMaterialCreate):
    id: int
    sr_no: str
    model_config = {"from_attributes": True}


# ---------- Ledger (Module 4) ----------
class LedgerTxn(BaseModel):
    date: Date
    particulars: str
    address: str = ""  # delivery site / address for this entry
    debit: float
    credit: float
    balance: float


class LedgerSummaryRow(BaseModel):
    party: str
    balance: float
