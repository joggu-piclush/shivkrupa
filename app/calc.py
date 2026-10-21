"""
Production "Average": how many bricks one cement bag produced in a batch.

    average = pallets x AVERAGE_BRICKS_PER_PALLET[brick_type] / cement bags used

It is worked out every time an entry is read, never typed in and never stored,
so it always agrees with the pallets and cement bags on that entry, and an edit
to either one updates it automatically.

These are the factors the client gave for the Average. They are kept separate
from PALLET_SIZE in routers/production.py on purpose: PALLET_SIZE decides how
many bricks go into stock, this only decides the Average. If the client changes
a factor, change it here and nowhere else.
"""
from typing import Optional

AVERAGE_BRICKS_PER_PALLET = {"4 inch": 105, "6 inch": 66}


def average_for(brick_type: str, pallets: float, cement_bags: float) -> Optional[float]:
    """Bricks per cement bag, rounded to 2 decimals. None when it can't be worked
    out: no cement bags recorded (older entries, or 0 entered) or an unknown size."""
    factor = AVERAGE_BRICKS_PER_PALLET.get(brick_type)
    if factor is None or not cement_bags or cement_bags <= 0:
        return None
    return round(pallets * factor / cement_bags, 2)
