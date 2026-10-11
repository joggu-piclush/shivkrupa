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

from . import models, auth
from .database import engine, SessionLocal
from .routers import auth_router, sales, cash, expenses, production, raw_materials, parties, reports

models.Base.metadata.create_all(bind=engine)

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
)

app.include_router(auth_router.router)
app.include_router(sales.router)
app.include_router(cash.router)
app.include_router(expenses.router)
app.include_router(production.router)
app.include_router(raw_materials.router)
app.include_router(parties.router)
app.include_router(reports.router)


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
                role="admin",
            ))
            db.commit()
            print(f"[startup] Seeded first login -> username={username!r}. "
                  f"(Password is not printed; it comes from SEED_ADMIN_PASSWORD.)")
    finally:
        db.close()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "Shivkrupa Enterprises API"}
