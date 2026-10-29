"""
Entry point. Run with:  uvicorn app.main:app --reload

On startup this:
  1. Creates shivkrupa.db and every table, if they don't already exist
     (safe to run repeatedly -- it never drops or overwrites existing data).
  2. Seeds ONE admin login if the users table is empty, so you have
     something to log in with immediately. Username/password/mobile come
     from environment variables, falling back to the same demo credentials
     as the mockup (admin / admin123) purely for local testing.
  3. Mounts every router under one app, and enables CORS so a frontend
     served from a different origin (e.g. a local HTML file, or later a
     separate frontend domain) is allowed to call this API.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models, auth, otp
from .database import engine, SessionLocal
from .routers import auth_router, sales, cash, expenses, production, raw_materials, parties, reports, backup

models.Base.metadata.create_all(bind=engine)


def _add_missing_columns():
    """create_all() creates NEW tables but never alters tables that already exist.
    When a feature adds a column to a table that already holds real data, it is
    listed here and added on startup. Additive only: nothing is dropped, renamed
    or rewritten, so existing entries are untouched. Safe to run on every start."""
    from sqlalchemy import inspect, text
    wanted = [
        # (table, column, SQL type + default)
        ("production", "cement_bags", "FLOAT NOT NULL DEFAULT 0"),
        ("otp_codes", "attempts", "INTEGER NOT NULL DEFAULT 0"),
        ("users", "email", "VARCHAR NOT NULL DEFAULT ''"),
    ]
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in wanted:
            if table in tables and column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                print(f"[startup] Added column {table}.{column}")


_add_missing_columns()

app = FastAPI(title="Shivkrupa Enterprises API")

# Which websites may call this API. Set ALLOWED_ORIGINS on the server to your
# real frontend address(es), comma-separated, e.g. "https://shivkrupa.vercel.app".
# If it isn't set, everything is allowed (fine for local testing only).
_origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Let the browser remember the "may I?" check for 2 hours (the most Chrome keeps), so repeat visits to the
    # same screens skip it. (FastAPI's own default is only 10 minutes.)
    max_age=7200,
)

app.include_router(auth_router.router)
app.include_router(sales.router)
app.include_router(cash.router)
app.include_router(expenses.router)
app.include_router(production.router)
app.include_router(raw_materials.router)
app.include_router(parties.router)
app.include_router(reports.router)
app.include_router(backup.router)


@app.on_event("startup")
def seed_default_admin():
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            username = os.environ.get("SEED_ADMIN_USERNAME", "admin")
            password = os.environ.get("SEED_ADMIN_PASSWORD", "admin123")
            mobile = os.environ.get("SEED_ADMIN_MOBILE", "9800000000")
            db.add(models.User(
                username=username,
                password_hash=auth.hash_password(password),
                mobile=mobile,
                email=os.environ.get("SEED_ADMIN_EMAIL", "").strip(),
                role="admin",
            ))
            db.commit()
            print(f"[startup] Seeded first login -> username={username!r}. "
                  f"(Password is not printed; it comes from SEED_ADMIN_PASSWORD.)")
        else:
            # The mobile number that receives the first login's OTP can be changed later by
            # changing SEED_ADMIN_MOBILE on the server: it is applied on the next start.
            # (The seed above only runs once, on an empty database, so without this the
            # number could never be changed after the first start.)
            # SEED_ADMIN_EMAIL does the same for the address that receives the code by email.
            username = os.environ.get("SEED_ADMIN_USERNAME", "").strip()
            mobile = os.environ.get("SEED_ADMIN_MOBILE", "").strip()
            email = os.environ.get("SEED_ADMIN_EMAIL", "").strip()
            if username and (mobile or email):
                user = db.query(models.User).filter(models.User.username == username).first()
                if user and mobile and user.mobile != mobile:
                    user.mobile = mobile
                    db.commit()
                    print(f"[startup] Login {username!r} will now get its OTP on the number ending {mobile[-4:]}.")
                if user and email and user.email != email:
                    user.email = email
                    db.commit()
                    print(f"[startup] Login {username!r} will now get its email code at {otp.mask_email(email)}.")
    finally:
        db.close()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Shivkrupa Enterprises API"}
