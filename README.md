# O-Kay AI Financial Assistant (Khalti prototype)

A self-contained prototype that upgrades Khalti's chat assistant, O-Kay, so it understands the
user's own money: spending, budgets, goals, bills and forecasts. It runs on **mock data only**;
no real customer data is ever sent to the LLM provider. The full spec is in [CLAUDE.md](CLAUDE.md).

**Live demo:** https://poudelnishan60-star.github.io/okay-money-assistant/ (unofficial, not
affiliated with Khalti). The backend runs on a free server that sleeps when idle, so the first
load after a quiet spell can take about a minute.

```
/app       Flutter (Dart 3) feature module + the website shell around it
/backend   FastAPI + SQLAlchemy + SQLite, Groq LLM calls (backend only)
render.yaml, .github/workflows/pages.yml   deployment (see "Deployment")
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
evals/               the 50-question evaluation (questions.json + runner.py)
scripts/             fixtures/calendar exports, live checks, eval, alert job
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
| GET | `/notifications` | alerts inbox, newest first, with the unread count (checks for new alerts first) |
| POST | `/notifications/read` | `{"ids": [...]}` marks those read; `{}` marks all read |
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

### Alerts

The spec's notifications: a budget at 80% and at 100%, a bill due within 3 days, unusual
spending (a category at 2x its usual level) and a weekly summary on the day the user picks.
`app/services/notifications.py` works them out in code from the same services as the screens
and stores each event once (a unique key per user, e.g. budget 4, Kartik 2083, 80%), so running
the check again never duplicates. The numbers are kept as they were when the alert fired; the
words are written when it is read, in English or Nepali (the user's language setting). The
switches in Settings stop new alerts of that kind.

On the website the alerts live in an in-app inbox (the bell): reading `GET /notifications`
runs the check for that visitor, so no scheduler is needed. Inside Khalti, a daily job would
run `python scripts/send_alerts.py` and a `PushSender` (Khalti's push service; a no-op here)
would deliver each new alert as a push notification.

The low-balance warning line (Settings → Forecast) is used by the dashboard's forecast and by
the chat's `get_balance_forecast` tool.

### Evaluation (50 questions)

`evals/questions.json` holds 50 questions: 20 English, 15 Nepali (Devanagari), 15 Romanized
Nepali, across spending, transactions, budgets, goals, bills, forecast, help, actions and
safety. Each one goes through the real chat pipeline against demo data seeded at a fixed date.
It checks:
- the expected tool calls, with the key arguments (category, period, merchant, amount);
- the numbers in the answer. Expected values are not written in the file: the runner gets them
  by running the tool itself, so they follow the data;
- cards (Confirm, Pay, bills...), the reply language, and words that must or must not appear;
- always: every "Rs." amount is grounded in a tool result, nothing in the database changed (no
  saving without Confirm, no money moved), and an MPIN/OTP typed in never reaches the model.

```bash
python scripts/eval_chat.py                   # all 50, about 25 minutes on Groq's free tier
python scripts/eval_chat.py --only en01,ne07  # or --lang rom, --topic budgets
```

A rate limit or outage counts as an error, not a wrong answer. The full report (answers, tool
calls, problems) goes to `evals/results/` (gitignored). `tests/test_evals.py` checks the
question file and the scorer with a scripted LLM, so `pytest` needs no network.

**Results, 10 Nov 2026 (Groq free tier).** Last full run: 45 of 50 passed (90%): English
20/20, Nepali 14/15, Romanized Nepali 11/15. Most answers came from the fallback models
(gpt-oss-120b, then gpt-oss-20b) because Qwen was rate-limited. The runs found real problems,
now fixed:
- Romanized questions detected as English ("Bikash lai 500 pathaidinus", "... bhaneko ke ho?");
- after a rejected answer, a model refusing the forced tool call gave "O-Kay can't answer right
  now" (now retried, then tried once more without forcing);
- "In 2020 you spent Rs. 0" (now: no data before the history starts);
- a 30-day forecast read as the month-end balance (the month end is now always given, apart);
- a Nepali help question finding no article; "money from abroad" counted as all money in;
- English replies to Romanized questions, e.g. "Tap Confirm to save it." copied from the prompt
  (now the language rule is repeated after tool results).

After those fixes, the 33 affected questions (all Nepali and Romanized, plus three English
ones) were run again: 32 passed. Still failing: "Bikash lai 500 pathaidinus" opens the right
send-money button but replies in English. Results vary between runs (39 to 45 of 50 before
the fixes) as the answering model changes, so run it more than once before comparing changes.

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
flutter run --dart-define=OKAY_AI_ENABLED=false                         # feature flag off: "O-Kay is switched off"
```

App layout:

```
lib/main.dart                     runs the website
lib/demo_host/                    the website's shell: opens straight into the O-Kay chat, mounts
                                  the assistant's routes, mock bridge, phone-width frame and label
lib/features/ai_assistant/        THE FEATURE: drops into the Khalti app as one folder
  ai_assistant.dart               public API for the host
  config.dart                     base URL, feature flag
  theme/okay_theme.dart           every design token (colours, type, radii, spacing)
  core/api_client.dart            the one HTTP client (JSON, errors, SSE stream for chat)
  core/money.dart, dates.dart     "Rs. 1,25,000.50", AD/BS dates in Nepal time
  core/bs_date.dart (+ _data)     BS calendar, generated from the backend's table
  core/privacy.dart               hidden-amounts masking
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
flow via `HostAppBridge`. With amounts hidden, those in the answer text are masked too.

The website opens straight into this chat: there is no stand-in Khalti home screen around it.
The chat's header leads to everything else: Money Insights, the alerts bell (with the unread
count) and a menu with Assistant settings and Clear chat. While the free server wakes up, the
chat says so ("Waking O-Kay up…") instead of showing a bare spinner.

Live end-to-end check against a running backend with a Groq key (not part of `flutter test`):

```bash
flutter test test_live/live_chat_test.dart
```

### Money screens

Reached from the chat's header (Money Insights, the bell, the menu) and from the chat's cards.
Money Insights links on to Transactions, Budgets, Goals and Bills.

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
- **Alerts**: the bell in the chat's header and on Money Insights shows the unread count;
  the inbox lists budget, bill, unusual-spending and weekly-summary alerts. Tapping one marks
  it read and opens the screen it is about (an unusual-spending alert opens that category's
  transactions).
- **Settings**: language (English / नेपाली / Auto), AD/BS, alerts, weekly-summary day,
  low-balance warning line, Hide amounts, how the data is used, clear chat history. Language
  and calendar apply to the chat and every screen.

With Hide amounts on (in the Khalti app: the Home screen's hide-balance eye, which shares the
same state), every amount in the chat and on these screens is masked until one is tapped (a
test opens each of them and fails if any amount shows). Lists can be pulled down to reload.

Widget tests answer from JSON fixtures exported from the real API, so they track the backend.
Regenerate them after changing the seed or the API:

```bash
cd backend && python scripts/export_app_fixtures.py
```

**Golden tests.** `test/goldens/` renders 13 key screens (chat empty, a chat answer, a
Nepali chat with Confirm and Pay cards, insights, transactions, budgets, goals, bills, alerts,
settings, two sheets, insights with amounts hidden) with the bundled fonts and compares
them with the PNGs in `test/goldens/images/`. They run with `flutter test`. After an intended
visual change:

```bash
flutter test test/goldens --update-goldens   # then look at the changed PNGs before committing
```

The images were made on Windows; other systems rasterize text a little differently, so up to
0.5% of pixels may differ. Dates are pinned (`clockProvider`), so the images don't change with
the calendar.

Live check of every screen's reads and writes against a running backend (no Groq key needed):

```bash
flutter test test_live/live_screens_test.dart
```

The feature folder imports nothing from the rest of `lib/`; a test enforces it. The host
overrides `hostAppBridgeProvider`, mounts `aiAssistantRoutes()`, and keeps
`amountPrivacyProvider` in sync with its hide-balance toggle. For its Home it can use the
exported `AskMeButton` (the floating "Ask me" button that opens the chat) and `AlertsBell`.
`#/assistant/ui-kit` shows every token and component.

**BS dates.** The app's BS calendar table is generated from the backend's `nepali-datetime`,
so both sides always agree:

```bash
cd backend && python scripts/export_bs_calendar.py
```

`nepali_utils` 3.0.8 was not used: it converts AD to BS one day late (9 Nov 2026 gave
Kartik 24; the published calendar says Kartik 23) and its 2084 table differs from the
published calendar (Jestha 2084 has 31 days, not 32).

## Deployment

| Part | Where | How it updates |
|---|---|---|
| Website (Flutter web) | GitHub Pages: https://poudelnishan60-star.github.io/okay-money-assistant/ | Automatically, on every push to `main` that changes `app/` (`.github/workflows/pages.yml`) |
| Backend (FastAPI) | Render, free plan: https://okay-money-assistant-api.onrender.com | **Manually**: in Render, open the service and press Manual Deploy > Deploy latest commit |

**Website.** The workflow builds with `--base-href /<repo>/` and takes the backend's address
from the repository variable `OKAY_API_BASE_URL` (Settings > Secrets and variables > Actions >
Variables). It is not a secret: the browser calls it.

**Backend.** `render.yaml` is a Render Blueprint: Python 3.13, `pip install .`, uvicorn, health
check on `/health`, and these settings: `PUBLIC_MODE=true` (every visitor gets a private copy of
the demo data), `CORS_ORIGINS` (only the Pages site may call the API; no localhost),
`FORWARDED_ALLOW_IPS=*` (so the per-visitor limits see the visitor's address behind Render's
proxy). `GROQ_API_KEY` is **not** in the file: it is typed into Render (service > Environment)
and lives only there. The service was created from the public repository URL, without giving
Render access to the GitHub account, which is why backend changes are deployed by hand.

What the free plan means:
- The server sleeps after 15 minutes without requests; the next visitor waits up to about a
  minute while it wakes. The website itself loads at once.
- Nothing on disk survives a restart or a deploy. That is fine for this demo: the mock data is
  seeded again on start, and a visitor whose copy is gone gets a fresh one automatically. Their
  budgets, goals and chat history from before are lost.
- Groq's free tier is about 2-3 questions a minute per model. `/chat` is rate-limited per
  visitor and overall, and answers "O-Kay is busy" when the limit is reached.
- When the cap on visitor copies is reached, the oldest copy is dropped (never the new visitor).

To set it up again from scratch: push the repository to GitHub, enable Pages with "GitHub
Actions" as the source, set `OKAY_API_BASE_URL`, then in Render choose New > Blueprint, give the
repository URL, enter `GROQ_API_KEY` and deploy. If the Render address differs from the one in
`CORS_ORIGINS` / `OKAY_API_BASE_URL`, update both.

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
| 8 | Notifications, polish, golden tests, 50-question eval | done |
| 9 | Deploy the website and backend | done |

The assistant ships as a **public website** (the Flutter web build) and merges into the
Khalti app later; see "Public website first" in [CLAUDE.md](CLAUDE.md). It is an unofficial
prototype, not affiliated with Khalti, and uses mock data only.
