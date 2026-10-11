"""
Database connection setup.

SQLite stores everything in a single file. That file IS the database -- no
separate server process to install, configure, or pay for. For backups, you
can literally just copy that file.

The path is read from the DATABASE_URL environment variable so it can point
at a mounted persistent volume once deployed (e.g. Railway/Render), rather
than the container's own ephemeral disk. Locally, with no env var set, it
just falls back to a file sitting next to this code -- exactly as before.

`check_same_thread=False` is required because FastAPI can handle a request on
a different thread than the one that opened the connection -- SQLAlchemy's
connection pool manages thread-safety for us above this layer.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./shivkrupa.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: gives each request its own DB session, always closed after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
