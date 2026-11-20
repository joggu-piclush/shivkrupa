"""
ONE-OFF data correction, at the owner's request: give entries that were saved before the app capitalised as you
type the same capital letters the app uses now ("sharma builders" -> "Sharma Builders").

Which fields: only text typed in words -- party names, sites, remarks, payment modes, expense particulars/details,
raw-material names, suppliers and "entered by". Never dates, amounts, mobile numbers, Sr. Nos, brick types
("4 inch"), "carting by", usernames or anything else.

Parties are matched by exact spelling everywhere (Sales, Cash, the Party Directory and so the Ledger), so one
spelling rule is applied to all of them at once and they stay in step. Two directory names that differ only in
capitals ("mehta traders" / "Mehta Traders") become one party: the duplicate directory row is dropped, its
address / mobile fills any blank on the one kept, and the entries of both spellings now sit under the one name.

Nothing is deleted except those duplicate directory rows. Runs once, behind a marker file and after a full copy of
the database has been saved (see main.py). To be taken out of the code again right after it has run.
"""
from . import models
from .textfix import capitalize_words as cap


def _fix(rows, fields):
    """Capitalise the named text fields of every row; returns how many rows changed."""
    changed = 0
    for row in rows:
        touched = False
        for field in fields:
            old = getattr(row, field)
            new = cap(old)
            if new != old:
                setattr(row, field, new)
                touched = True
        changed += touched
    return changed


def capitalise_existing_entries(db) -> dict:
    """Does the whole correction in the caller's session (the caller commits) and returns counts only."""
    counts = {"parties_merged": 0, "parties_renamed": 0, "sales": 0, "cash": 0, "expenses": 0, "production": 0, "raw_materials": 0}

    # --- the Party Directory first: group names that become the same, keep one, rename it ---
    groups = {}
    for party in db.query(models.Party).order_by(models.Party.id).all():
        groups.setdefault(cap(party.name), []).append(party)
    keepers = {}
    for new_name, rows in groups.items():
        keep = next((r for r in rows if r.name == new_name), rows[0])  # the one already spelt right, else the oldest
        keepers[new_name] = keep
        for other in rows:
            if other is keep:
                continue
            if not keep.address and other.address:
                keep.address = other.address
            if not keep.mobile and other.mobile:
                keep.mobile = other.mobile
            db.delete(other)
            counts["parties_merged"] += 1
    db.flush()  # the duplicates must be gone before a name is changed, or the unique name would clash
    for new_name, keep in keepers.items():
        if keep.name != new_name:
            keep.name = new_name
            counts["parties_renamed"] += 1
        keep.address = cap(keep.address)
    db.flush()

    # --- the entries, with the same rule ---
    counts["sales"] = _fix(db.query(models.Sale).all(), ("party_name", "address", "remarks"))
    counts["cash"] = _fix(db.query(models.CashEntry).all(), ("name", "address", "mode"))
    counts["expenses"] = _fix(db.query(models.Expense).all(), ("particulars", "details"))
    counts["production"] = _fix(db.query(models.Production).all(), ("entered_by",))
    counts["raw_materials"] = _fix(db.query(models.RawMaterial).all(), ("material", "supplier"))
    return counts
