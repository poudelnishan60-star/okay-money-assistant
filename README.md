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
app/ai/              LLM client, tools, cards, prompt, safety (masking), chat loop, classifier
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
| GET / PUT | `/me/settings` | assistant settings: language, calendar, alerts, weekly-summary day, low-balance threshold |
| POST | `/sessions` | public site: a private copy of the demo data for this visitor |
| POST | `/chat` | ask O-Kay; streams server-sent events (see below) |
| GET / DELETE | `/chat/history` | the conversation / clear it |
| PUT | `/chat/messages/{id}/feedback` | thumbs `up` / `down` |

### O-Kay chat (AI)

Copy `backend/.env.example` to `backend/.env` (exactly that name) and put your Groq key in it
(`GROQ_API_KEY=...`, from https://console.groq.com/keys). Without a key the chat still works end
to end but answers "O-Kay isn't connected yet".

`POST /chat {"message": "yo mahina khana ma kati kharcha bhayo?", "language": "auto"}` streams:

```
event: status  data: {"tool": "get_spending_summary"}
event: token   data: {"text": "Yo mahina khana ma Rs. 1,270 kharcha bhayo."}
event: done    data: {"message_id": 7, "cards": [...], "suggestions": [...], "language": "rom", "error": null}
```

How it stays safe and correct:

- The model never does arithmetic. Its tools (`app/ai/tools.py`) compute every number with the
  same services as the REST API and hand over pre-formatted amounts; cards are built in code.
- Budgets and goals are only *proposed* (`confirm_action` card); the app saves them by calling
  `POST /budgets` / `POST /goals` after the user taps Confirm.
- It never moves money: payments become an `open_app_flow` card that opens Khalti's own
  screen; the user finishes with MPIN.
- Before anything goes to Groq: phone, account and reference numbers are masked, an
  MPIN/OTP/password typed into the chat is removed (and the user is warned), merchant names
  and notes are neutralized and wrapped in `<tool_result>` tags as data.
- HTTP 429 from Groq (or a garbled tool call): up to 3 tries with backoff, moving down the model
  chain qwen/qwen3.8-27b -> openai/gpt-oss-120b -> openai/gpt-oss-20b, then
  "O-Kay is busy, please try again in a minute". (The spec's llama-3.3-70b-versatile is no
  longer offered on Groq.) Qwen runs with `reasoning_effort=none`, and any
  `<think>` text is stripped.
- Tool calls are logged (`tool_call_log`, masked arguments); raw prompts are not.
- A code check backs the "never invents numbers or actions" rule: every "Rs." amount in an
  answer must appear in a tool result (this turn or earlier in the chat), and "tap Confirm" /
  "the button below" need that card. If not, the server sends a `reset` event (the app drops the
  text) and the model gets one corrective round that must call a tool.
- The last 20 messages are sent as context; at most 5 tool rounds per message.

**Groq free tier:** 8,000 tokens/minute and 1,000 requests/day *per model*; one question
uses about 3,000 tokens, so expect roughly 2-3 questions a minute per model. Fine for a demo;
a busy public site needs a paid Groq tier (or lower limits in `.env`).

Live check against Groq (mock data only): `python scripts/live_chat_check.py`.

Unknown merchants (rules couldn't place them) are categorized by the LLM once per merchant and
cached: `python -m app.ai.classifier`.

For the public website set `PUBLIC_MODE=true`: each visitor calls `POST /sessions` and sends the
returned id as `X-User-Id`; copies expire after `SESSION_TTL_DAYS`. `/chat` is rate-limited per
visitor and overall (see `.env.example`).

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
  chat/                           O-Kay chat: screen, controller, repository, cards
  core/visitor_session.dart       public site: a private demo copy per browser
  data/                           models, repositories (one per screen) and Riverpod providers
  screens/                        insights, transactions, budgets, goals, bills, settings, UI kit
```

### The website (Flutter web)

Start the backend, then build and serve the site:

```bash
cd app
flutter build web --release
python -m http.server 8080 --directory build/web --bind 127.0.0.1
```

Open http://127.0.0.1:8080. On a laptop the app sits in a centred phone-width column; every
screen says "Unofficial prototype · not affiliated with Khalti · mock data only". Each browser
gets its own copy of the demo data (`POST /sessions`, remembered in local storage, renewed if
it expires); `--dart-define=OKAY_VISITOR_SESSIONS=false` makes everyone share the demo user.
Fonts (DM Sans, Noto Sans Devanagari; SIL OFL, `app/assets/fonts/`) are bundled.

### O-Kay chat

Streamed answers, cards (spending, where-it-went bars, budgets, bills with Pay/Autopay, goals
with Smart Deposit, transactions, confirm, open-in-Khalti), follow-up chips, thumbs, retry, clear
chat. Budgets/goals are saved only when the user taps Confirm; payments open the host app's own
flow via `HostAppBridge`. With the balance hidden, amounts in the answer text are masked too.

Live end-to-end check against a running backend with a Groq key (not part of `flutter test`):

```bash
flutter test test_live/live_chat_test.dart
```

### Money screens

Reached from Home → Financial Services → "Money Insights" and from the chat's cards.

- **Insights**: month selector (AD or BS months), total spent and change against the same days
  of last month, insight cards (unusual spending, biggest category), month-end forecast with
  a low-balance warning, category donut with a list, day-by-day bars, top merchants. Tapping a
  category opens its transactions.
- **Transactions**: period chips (7 / 14 / 30 days, this month, custom range), grouped by day
  with the closing balance, paging. The detail sheet changes the category, optionally for every
  transaction from that merchant.
- **Budgets**: bars with words as well as colour (on track / near limit / over), "about Rs. X a
  day for N days"; a sheet to create, edit or delete one (AD or BS month).
- **Goals**: progress ring, target, deadline, "needs Rs. X/month", "Automate with Smart
  Deposit" (opens the host's Smart Deposit through `HostAppBridge`).
- **Bills**: detected recurring payments with next due date and usual amount, Pay now, Set up
  Autopay, confirm or dismiss (with undo).
- **Settings**: language (English / नेपाली / Auto), AD/BS, alerts, weekly-summary day, how the
  data is used, clear chat history. Language and calendar apply to the chat and every screen.

Widget tests answer from JSON fixtures exported from the real API, so they track the backend.
Regenerate them after changing the seed or the API:

```bash
cd backend && python scripts/export_app_fixtures.py
```

Live check of every screen's reads and writes against a running backend (no Groq key needed):

```bash
flutter test test_live/live_screens_test.dart
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
| 5 | Backend AI: Groq LLMClient, tools, /chat SSE, masking, 429 handling, per-visitor sessions, rate limits | done |
| 6 | App chat: fonts, website layout, O-Kay chat screen | done |
| 7 | App screens: insights, transactions, budgets, goals, bills, settings | done |
| 8 | Notifications, polish, golden tests, 50-question eval | |
| 9 | Deploy the website and backend | |

For now the assistant ships as a **public website** (the Flutter web build) and merges into the
Khalti app later; see "Public website first" in [CLAUDE.md](CLAUDE.md). It is an unofficial
prototype, not affiliated with Khalti, and uses mock data only.
