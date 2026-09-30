# Shivkrupa Enterprises -- Full Stack App

FastAPI + SQLite backend, plus a connected frontend (`frontend/index.html`),
implementing every module from the approved blueprint: Sales Book, Cash
Book, Expenses Book, Raw Materials Book, Ledger, Production (two brick
sizes), Stock (split per brick size), Reports, Party Directory, and Login+OTP.

## Run it locally (first time)

```bash
# 1. Create an isolated Python environment
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional but recommended) copy the environment template and edit it
cp .env.example .env

# 4. Start the backend
uvicorn app.main:app --reload
```

The first time it starts, it creates `shivkrupa.db` (empty, all tables) and
prints the seeded login:

```
[startup] Seeded first login -> username='admin' password='admin123'.
```

Visit **http://localhost:8000/docs** for a full interactive API explorer.

## Run the frontend

`frontend/index.html` is a single self-contained file -- just open it
directly in a browser (double-click it, or `open frontend/index.html`).
It talks to the backend at `http://localhost:8000` (see the `API_BASE`
constant near the top of its `<script>` if you need to point it elsewhere,
e.g. after deploying the backend to a VPS).

It has a **Desktop / Mobile** toggle at the top so you can preview both
layouts from the same page -- that toggle is a preview convenience only,
not a real device check.

## The login flow

```
POST /auth/login        {username, password}       -> {otp_token}
POST /auth/verify-otp   {otp_token, code}           -> {access_token}
```

Every other endpoint requires that access_token:
`Authorization: Bearer <access_token>`

No real SMS account is connected yet, so the OTP prints to this server's
own console instead of being texted anywhere -- watch the terminal running
`uvicorn` while you log in:

```
[DEV MODE] OTP for 9800000000: 8736  (would be sent via SMS in production)
```

## Two brick sizes

The factory makes two brick sizes with different pallet yields:

| Brick size | Bricks per pallet |
|---|---|
| 4 inch | 100 |
| 6 inch | 66 |

Every Production and Sales entry records which size it's for, and the
pallet-to-bricks math always happens on the server (`app/routers/production.py`,
`PALLET_SIZE` dict) so the two numbers can never disagree. **Stock is
tracked separately per size** -- `GET /stock` returns one entry per brick
type, never a single combined number, since 500 four-inch bricks and 500
six-inch bricks are different products.

## Raw Materials Book

A new module logging materials arriving at the factory (cement, sand,
coal...) -- Date, Material, Quantity, Unit (Truck/Bag/etc.), Cost, Supplied
By. Material, Unit, and Supplier each get their own auto-growing suggestion
list, deliberately separate from the customer Party Directory. Right now
this only logs what arrived and its cost -- it does **not** yet give a
running "how much cement is on hand" figure, or connect to Sales. See
Question 11 in the blueprint if the client wants that too.

## What's already tested and confirmed working

Every one of these was run against this exact code (backend AND frontend
together, through the real UI, hitting the real running server) before it
was handed to you:

- Wrong password rejected, correct password issues an OTP, wrong OTP
  rejected, correct OTP issues a real session token, a code can only be
  used once
- Every module refuses a request with no valid token
- Production: 5 pallets of 4-inch correctly gives 500 bricks; 5 pallets of
  6-inch correctly gives 330, not 500; an unknown brick type is rejected
  with a 400, not silently miscalculated
- Stock correctly reports two independent figures after mixed production
  and sales across both sizes
- Sales Book correctly filters and displays by Brick Type
- Raw Materials: create, edit-in-place (not duplicated), and delete all
  confirmed; its three suggestion lists (Material/Unit/Supplier) grow
  correctly as new values are typed, with Truck/Bag always available even
  before anyone's used them
- Creating a Sale or Cash entry automatically adds/updates that party in
  the Party Directory, and that update is immediately visible from the
  *other* book's form too
- Editing any entry updates it in place (same ID, same Sr. No.); deleting a
  real entry works, deleting one that doesn't exist returns a clean 404
- The Ledger correctly nets a fully-paid party to zero and shows an unpaid
  one as still due
- Monthly Reports correctly includes Raw Material cost alongside
  everything else
- The mobile "More" screen's Ledger, Stock, and Reports sections populate
  correctly from the same live data as the desktop view

One real bug this testing caught and fixed: the date-range filters on every
module originally carried over hardcoded demo dates from the sales-pitch
mockup. A brand-new entry dated today would have silently not appeared,
because the filter was still range-locked to an old demo date range. Fixed
by leaving those fields blank so they default to "first of this month
through today" on every login.

## One real gap to plan around: opening stock

`GET /stock` is `total bricks ever produced` minus `total bricks ever
sold`, per size. That's correct from the moment this system starts
recording data -- but on day one, if the factory already has bricks
sitting in the yard, those won't be counted. Either the client provides
the current physical stock (per size) so it can be entered as a one-time
starting balance, or the numbers will read low until enough new production
catches up. Not built yet -- flag it before go-live.

## Before this goes live for real

- [ ] Set a real `SECRET_KEY` in `.env`
- [ ] Change `SEED_ADMIN_PASSWORD`, or add proper user management
- [ ] Replace `send_otp_sms()` in `app/otp.py` with a real SMS provider call
      (MSG91 / 2Factor.in)
- [ ] Narrow `allow_origins` in `app/main.py` from `"*"` to your real
      frontend's domain
- [ ] Update `API_BASE` in `frontend/index.html` to your deployed backend's URL
- [ ] Decide the opening-stock number with the client (above)
- [ ] Decide whether Raw Materials needs its own running stock figure too
      (blueprint Question 11)
- [ ] Deploy behind HTTPS (a VPS + Let's Encrypt/Caddy, as discussed)
