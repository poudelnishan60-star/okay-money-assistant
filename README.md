# O-Kay AI Financial Assistant (Khalti prototype)

A self-contained prototype that upgrades Khalti's chat assistant, O-Kay, so it understands the
user's own money: spending, budgets, goals, bills and forecasts. It runs on **mock data only**;
no real customer data is ever sent to the LLM provider. The full spec is in [CLAUDE.md](CLAUDE.md).

```
/app       Flutter (Dart 3) feature module + demo host shell
/backend   FastAPI + SQLAlchemy + SQLite, Groq LLM calls (backend only)
```

## Backend

Requires Python 3.12+ (developed on 3.13).

```bash
cd backend
py -3.13 -m venv .venv            # macOS/Linux: python3 -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env              # then put your GROQ_API_KEY in .env
python -m app.seed                # (re)create khalti_ai.db with the demo data
uvicorn app.main:app --reload
```

The seed is reproducible: a fixed random seed plus the anchor date decide every row. By default
the 90 days of history end yesterday (Nepal time); `python -m app.seed --anchor 2026-11-09`
pins it (the tests use that date). Merchants are invented and amounts are labelled estimates of
typical Kathmandu prices; see the docstring in `backend/app/seed.py`.

Backend layout:

```
app/domain.py        types: transaction, category, direction (money is integer paisa)
app/models.py        SQLite schema (SQLAlchemy)
app/sources/         TransactionSource / BillSource / DepositSource + Mock* implementations
app/api/             FastAPI routes, request/response schemas, dependencies
app/services/        categorizer, recurring detector, budgets, goals, forecast, insights, bills
app/periods.py       AD and BS months in Nepal time
app/money.py         "Rs. 1,25,000.50" formatting
app/seed.py          demo data (+ seed_faq.py: 16 mock help articles)
```

- Health check: http://127.0.0.1:8000/health
- API contract (OpenAPI): http://127.0.0.1:8000/docs and `/openapi.json`
- If the database is empty, the server seeds the demo data on startup (`AUTO_SEED=true`).
  `backend/.env` and the default `backend/khalti_ai.db` are found from any working directory.

### API

Conventions: money is **integer paisa** in fields ending `_paisa` (Rs. 1 = 100; the app
formats it); dates are AD `YYYY-MM-DD`; timestamps carry the Nepal offset (`+05:45`); periods
are inclusive. The user comes from an `X-User-Id` header that defaults to `demo_user`
(prototype only; real Khalti auth replaces it in `app/api/deps.py`).

| Method | Path | What |
|---|---|---|
| GET | `/me` | name, balance, balance-hidden flag |
| GET | `/categories` | categories, subcategories, which count as spending |
| GET | `/transactions` | newest first; `period=7d/14d/30d/this_month` or `start`/`end`; filter by `category`, `merchant`, `type`, `direction`, `min_paisa`, `max_paisa`; `limit`/`offset` |
| GET | `/transactions/{id}` | one transaction |
| PATCH | `/transactions/{id}/category` | recategorize; `apply_to_merchant` for all from that merchant |
| GET | `/insights/summary` | `period=month/week/custom`, `month=YYYY-MM`, `calendar=AD/BS`: totals, % change, categories, daily bars, top merchants |
| GET | `/insights/dashboard` | summary + unusual spending + insight cards + forecast, in one call |
| GET | `/insights/forecast` | `days=N` or to month end; low-balance warning (`threshold_paisa`) |
| GET / POST | `/budgets` | this month's status of each budget / create-or-update by category |
| PATCH / DELETE | `/budgets/{id}` | edit / remove |
| GET / POST | `/goals` | goals with progress and "needs Rs. X/month" / create |
| PATCH / DELETE | `/goals/{id}` | edit / remove |
| GET | `/smart-deposits` | existing Smart Deposit plans (read-only) |
| GET | `/bills` | detected bills & subscriptions, soonest due first |
| PUT | `/bills/{id}/status` | `confirmed` / `dismissed` / `detected` (undo) |

Lint and tests:

```bash
ruff check . && ruff format --check .
pytest
```

`backend/.env` is gitignored. The API key never leaves the backend; the app never holds it.

## App

Requires the Flutter SDK (stable channel, Dart 3).

```bash
cd app
flutter pub get
flutter analyze
flutter test
flutter run                       # pick a device / emulator / chrome
```

The Android emulator reaches the backend at `http://10.0.2.2:8000`; desktop and web use
`http://127.0.0.1:8000`. The base URL is set in the app's config (added in step 4).

## Build steps

| # | Step | Status |
|---|------|--------|
| 1 | Repo setup: folders, README, .env.example, .gitignore, lint config | done |
| 2 | Backend data: schema, seed, categorizer, recurring detector, budgets, forecast | done |
| 3 | Backend REST API | done |
| 4 | App foundation: theme, components, navigation, ApiClient, HostAppBridge mock | |
| 5 | App screens | |
| 6 | Backend AI: Groq LLMClient, tools, /chat SSE, masking, 429 handling | |
| 7 | App chat | |
| 8 | Notifications, polish, golden tests, 50-question eval | |
