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

Requires the Flutter SDK (stable channel, Dart 3; developed on Flutter 3.47.9). Start the
backend first, then:

```bash
cd app
flutter pub get
flutter analyze
flutter test
flutter run -d chrome             # or an Android emulator / phone
```

The app finds the backend at `http://10.0.2.2:8000` on the Android emulator and
`http://127.0.0.1:8000` elsewhere. Override at build time:

```bash
flutter run --dart-define=OKAY_API_BASE_URL=http://192.168.1.10:8000   # phone on Wi-Fi
flutter run --dart-define=OKAY_AI_ENABLED=false                         # feature flag off
```

App layout:

```
lib/main.dart                     runs the demo host
lib/demo_host/                    stand-in for the Khalti app (Home, bottom nav, Menu)
lib/features/ai_assistant/        THE FEATURE: drops into the Khalti app as one folder
  ai_assistant.dart               public API for the host
  config.dart                     base URL, feature flag
  theme/okay_theme.dart           every design token (colours, type, radii, spacing)
  core/api_client.dart            the one HTTP client (JSON, errors, SSE stream for chat)
  core/money.dart, dates.dart     "Rs. 1,25,000.50", AD/BS dates in Nepal time
  core/bs_date.dart (+ _data)     BS calendar, generated from the backend's table
  core/privacy.dart               hide-balance masking
  host/                           HostAppBridge interface + mock ("would open X" sheets)
  widgets/                        shared components
  routes.dart                     /assistant/... routes behind the feature flag
  screens/                        UI kit now; real screens in steps 5 and 7
```

The feature folder imports nothing from the rest of `lib/`; a test enforces it. The host
overrides `hostAppBridgeProvider`, mounts `aiAssistantRoutes()`, and keeps
`amountPrivacyProvider` in sync with its hide-balance toggle. Menu → "Assistant UI kit"
shows every token and component.

**BS dates.** The app's BS calendar table is generated from the backend's `nepali-datetime`,
so both sides always agree:

```bash
cd backend && python scripts/export_bs_calendar.py
```

`nepali_utils` 3.0.8 was not used: it converts AD to BS one day late (9 Nov 2026 gave
Kartik 24; the published calendar says Kartik 23) and its 2084 table differs from the
published calendar (Jestha 2084 has 31 days, not 32).

## Build steps

| # | Step | Status |
|---|------|--------|
| 1 | Repo setup: folders, README, .env.example, .gitignore, lint config | done |
| 2 | Backend data: schema, seed, categorizer, recurring detector, budgets, forecast | done |
| 3 | Backend REST API | done |
| 4 | App foundation: theme, components, navigation, ApiClient, HostAppBridge mock | done |
| 5 | App screens | |
| 6 | Backend AI: Groq LLMClient, tools, /chat SSE, masking, 429 handling | |
| 7 | App chat | |
| 8 | Notifications, polish, golden tests, 50-question eval | |
