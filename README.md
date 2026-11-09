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
app/services/        categorizer, recurring detector, budgets, goals, forecast
app/periods.py       AD and BS months in Nepal time
app/money.py         "Rs. 1,25,000.50" formatting
app/seed.py          demo data (+ seed_faq.py: 16 mock help articles)
```

- Health check: http://127.0.0.1:8000/health
- API contract (OpenAPI): http://127.0.0.1:8000/docs and `/openapi.json`

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
| 3 | Backend REST API | |
| 4 | App foundation: theme, components, navigation, ApiClient, HostAppBridge mock | |
| 5 | App screens | |
| 6 | Backend AI: Groq LLMClient, tools, /chat SSE, masking, 429 handling | |
| 7 | App chat | |
| 8 | Notifications, polish, golden tests, 50-question eval | |
