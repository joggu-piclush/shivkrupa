from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/parties", tags=["parties"])


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
