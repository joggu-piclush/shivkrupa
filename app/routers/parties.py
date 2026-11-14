from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/parties", tags=["parties"])


# The Party Directory is only ever filled by saving a Sale or a Cash entry, and it feeds the Ledger cards and the
# name suggestions. So a name that no Sale or Cash entry uses any more is just clutter (an empty "Settled" card in
# the Ledger): it is removed when its last entry is deleted or renamed away, and once at startup for any left over
# from before this rule existed. Only directory rows go -- never a Sale, Cash entry, or anything else.
def prune_party_if_unused(db: Session, name: str) -> None:
    """Drop `name` from the directory if no Sale or Cash entry uses it. Call after the entry change has been
    flushed; the caller commits."""
    if not name:
        return
    party = db.query(models.Party).filter(models.Party.name == name).first()
    if not party:
        return
    used = (
        db.query(models.Sale.id).filter(models.Sale.party_name == name).first() is not None
        or db.query(models.CashEntry.id).filter(models.CashEntry.name == name).first() is not None
    )
    if not used:
        db.delete(party)


def prune_unused_parties(db: Session) -> tuple:
    """Remove every directory name that no Sale or Cash entry uses. Returns (removed, kept). Caller commits."""
    used = {r[0] for r in db.query(models.Sale.party_name).distinct().all()}
    used |= {r[0] for r in db.query(models.CashEntry.name).distinct().all()}
    removed = kept = 0
    for party in db.query(models.Party).all():
        if party.name in used:
            kept += 1
        else:
            db.delete(party)
            removed += 1
    return removed, kept


def sites_by_party(db: Session) -> dict:
    """party name -> every distinct site (the 'address' typed on a Sale or Cash entry) used with that
    party, most recently used first. Nothing extra is stored: it is read from the entries themselves, so a
    new site shows up in the party's list the moment an entry with it is saved (and goes away only if
    every entry using it is deleted). 'Mumbai Site' and 'mumbai site ' count as the same site."""
    latest = {}  # (party, site lower-cased) -> (date last used, site as most recently typed)
    for model, party_col in ((models.Sale, models.Sale.party_name), (models.CashEntry, models.CashEntry.name)):
        rows = (
            db.query(party_col, model.address, func.max(model.date))
            .filter(model.address != "")
            .group_by(party_col, model.address)
            .all()
        )
        for party, site, last_used in rows:
            site = (site or "").strip()
            if not party or not site:
                continue
            key = (party, site.casefold())
            if key not in latest or last_used > latest[key][0]:
                latest[key] = (last_used, site)
    result = {}
    for (party, _), (last_used, site) in sorted(latest.items(), key=lambda kv: kv[1][0], reverse=True):
        result.setdefault(party, []).append(site)
    return result


@router.get("", response_model=list[schemas.PartyOut])
def list_parties(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    """The whole Party Directory -- the frontend uses this to populate the
    autocomplete suggestion list on Sales Book and Cash Book (Module 8), and each
    party's own list of sites for the Site box."""
    sites = sites_by_party(db)
    parties = db.query(models.Party).order_by(models.Party.name).all()
    return [
        schemas.PartyOut(name=p.name, address=p.address or "", mobile=p.mobile or "", sites=sites.get(p.name, []))
        for p in parties
    ]
