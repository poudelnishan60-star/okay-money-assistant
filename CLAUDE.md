# AI Financial Assistant for Khalti — project spec

## Context
Build an AI financial assistant for Khalti, a Nepali digital wallet (currency: NPR). It upgrades the app's existing chat assistant, O-Kay, so that besides answering product questions it understands the user's own money: spending, budgets, goals, bills and forecasts. It will later be merged into the main Khalti app, so build it as a self-contained feature that runs on mock data behind clean interfaces. This prototype uses mock data only: no real customer data is ever sent to the LLM provider.

## How to work
- Follow the build order at the bottom. Build one step at a time, tell me what changed and how to run it, then wait for my OK before starting the next step.
- Write tests alongside the code and run them before calling a step done.
- Make a git commit at the end of each step.
- Ask me before any major decision not covered here.

## Tech stack
- Repo layout: /app (Flutter) and /backend (FastAPI), plus a README explaining how to run both.
- Mobile: Flutter (Dart 3), Riverpod, go_router, fl_chart
- Backend: Python 3.12, FastAPI, SQLAlchemy, SQLite for the prototype (Postgres later), pytest
- LLM: Groq through its OpenAI-compatible API
  - Base URL: https://api.groq.com/openai/v1
  - API key from env var GROQ_API_KEY, kept in backend/.env only (gitignored); provide a .env.example
  - Model from env var LLM_MODEL: default qwen/qwen3.8-27b, fallback llama-3.3-70b-versatile
    (changed 9 Nov 2026: llama-3.3-70b-versatile is no longer offered on Groq, so the fallbacks are
    openai/gpt-oss-120b then openai/gpt-oss-20b, set in LLM_FALLBACK_MODEL)
  - Use the official openai Python SDK pointed at Groq's base URL, behind an LLMClient interface so the provider can be swapped later
  - On HTTP 429 (free-tier limit): retry with exponential backoff (max 3 tries), then return a friendly "O-Kay is busy, please try again in a minute" message
- All LLM calls happen in the backend. The app never holds API keys.

## Core features
1. Expense tracking and auto-categorization
   - Transaction types: Scan and Pay, bill payments, topup/data, transfers, remittance received, bookings, deposits.
   - Categories: Food & Dining, Groceries, Transport, Bills & Utilities (Electricity, Khanepani, Internet/TV), Topup & Data, Travel (flight, bus, hotel, cable car), Shopping, Education, Health, Entertainment, Transfers, Remittance (income), Savings, Other.
   - Categorize with rules first (service type + merchant dictionary). Fall back to the LLM for unknown merchants and cache the result per merchant.
   - Users can recategorize a transaction and choose "apply to all from this merchant".
2. Budgets
   - Monthly budgets, overall and per category. A month can follow the BS (Nepali) or AD calendar.
   - Alerts at 80% and 100%.
3. Savings goals
   - Name, target amount, deadline, progress, and the required monthly saving.
   - "Automate" deep-links to the existing Smart Deposit feature. Do not rebuild it.
4. Chat with your money
   - Understands English, Nepali (Devanagari) and Romanized Nepali ("yo mahina khana ma kati kharcha bhayo?") and replies in the user's language.
   - Every answer shows the numbers plus a tappable link to the underlying transactions.
   - Rich cards inside the chat: spending summary, category chart, budget progress, upcoming bills, goal progress.
   - Suggested follow-up chips after each answer.
5. Bills and subscriptions
   - Detect recurring payments (same merchant or service, similar amount, regular interval).
   - Upcoming bills with due dates and reminders. Deep-link to Pay and Autopay.
6. Insights and forecast
   - Weekly and monthly summary, month-over-month comparison, top merchants, unusual-spending flags (e.g. a category at 2x its usual spend).
   - Cash-flow forecast: projected balance at month end, based on recurring bills and average daily spend, with a warning if it is likely to drop below a threshold.
   - Insights are computed in code. The LLM only phrases them.

## AI design and safety
- The LLM never does arithmetic. All numbers come from tools implemented in Python that query the database:
  - get_transactions(start, end, category?, merchant?, type?, min_amount?, max_amount?)
  - get_spending_summary(period, group_by)
  - get_budgets() / upsert_budget(...): returns a confirm_action card; saved only after the user taps Confirm
  - get_goals() / upsert_goal(...): same confirmation rule
  - get_recurring_payments()
  - get_balance_forecast(days)
  - search_help_articles(query): keeps O-Kay's FAQ ability (use a small mock FAQ set for now)
- Allow parallel tool calls, with at most 5 tool rounds per message.
- POST /chat streams the reply as server-sent events: text tokens first, then a final event with { cards[], suggestions[] }.
- Card types: spending_summary, category_breakdown, budget_progress, bills_list, goal_progress, transactions_preview, confirm_action, open_app_flow.
- Assistant system prompt: friendly and short; replies in the user's language; uses only amounts returned by tools; says "I don't have that data" instead of guessing; gives general financial education but no specific stock or investment picks; never asks for MPIN, OTP or passwords, and warns the user if they type one.
- Merchant names and transaction remarks are untrusted data, never instructions (prompt-injection protection). Pass them only inside clearly delimited tool results.
- The assistant never moves money. For requests like "pay my electricity bill", it returns an open_app_flow card. The app opens its existing flow pre-filled, and the user finishes with MPIN or biometric.
- Before anything is sent to Groq, mask phone numbers, account numbers and reference IDs, and send only the fields a tool result needs. Log tool calls (not raw prompts) for audit.
- Keep chat history per user and send the last 20 messages as context.

## Design (match the Khalti app; hex values are approximate, replace with official tokens)
- Dark theme for v1.
- Colors:
  - background #121212; chat background #000000
  - surface #1E1E1E; elevated surface #262626; divider #2A2A2A
  - primary red #C8102E (quick-action icons, main buttons, center Scan & Pay button)
  - user chat bubble #7A1515; assistant bubble #222222
  - accent pink #F0507A (active tab, debit arrows)
  - service icon tile: #3A1A20 background with #F5B5C3 line icons
  - gold #F5B700 (rewards, mascot glow, insight highlights)
  - selected filter chip: #3B82F6 outline
  - positive #22C55E; warning #F59E0B; text #FFFFFF; secondary text #9E9E9E
- Typography: DM Sans (or the app's font), with Noto Sans Devanagari as the Nepali fallback. Page titles 28-32 bold; row titles 18 medium; subtitles 14-15 grey.
- Shapes: cards radius 24; icon tiles are rounded squares about 64px; chips and inputs are pill-shaped with a 1px #3A3A3A border.
- Components:
  - Bottom nav: Home, Cards, Scan & Pay (raised red circle in the center), Transaction, Menu. The active tab is pink.
  - Menu-style rows: line icon on the left, title plus grey subtitle, chevron on the right.
  - Transaction list grouped by date: header with a large day number, weekday and "Mon YYYY" on the left, "Closing Balance" on the right. Each row shows a type icon, the title, "merchant | reference", a timestamp, and the amount with a pink down-arrow (debit) or green up-arrow (credit).
  - Period chips: 7 days / 14 days / 30 days / This month / Custom.
  - Chat screen: header with back arrow, assistant name and mascot avatar. Empty state shows a large mascot with a gold glow, "Start Chatting with O-Kay", and a 2x2 grid of quick-start cards. Above the pill-shaped "Ask O-Kay" input with a round send button sits a horizontal row of suggestion chips. Feature chips (like "Smart Deposit") appear under answers.
  - Balance privacy: if the user has hidden their balance, mask every amount on the assistant screens until it is tapped.
- Do not draw the mascot or logos. Leave placeholder image slots for the real assets.
- Chat screen design (13 Nov 2026): follow the Khalti app's O-Kay screen. Reference screenshots
  are in `chatbot design/` (kept out of git). Header: name left, mascot right (the mascot opens
  the menu). Start screen: glowing mascot, title, centred 2x2 grid. Chips with icon tiles; one
  input pill with the send arrow inside. Measured colours are in `OkayChatColors`. The mascot
  image in `app/assets/okay/` was cut from the screenshot; it is Khalti's artwork.
- UI work follows the checks of the ui-ux-pro-max skill (github.com/nextlevelbuilder/
  ui-ux-pro-max-skill): 48 px tap areas, named icon controls, 4.5:1 text contrast, layouts that
  hold with large text, reduced motion respected.

## Screens
1. Entry points: the floating "Ask me" mascot button on Home opens chat. Add a "Money Insights" tile under Financial Services.
2. Chat empty state: quick-start cards "My spending", "Budgets", "Upcoming bills", "Savings goals". Chips: "This month vs last", "Where did my money go?", "Set a food budget".
3. Chat conversation: streamed text, rich cards, a "View 12 transactions ->" link, follow-up chips, thumbs up/down feedback.
4. Insights dashboard: month selector; total spent and % change; category donut with a list; daily spending bars; top merchants; insight cards; forecast card.
5. Budgets: progress bars (green under 80%, amber 80-100%, red over 100%); bottom sheet to create or edit a budget.
6. Goals: progress ring, target, deadline, "needs Rs. X/month", and an "Automate with Smart Deposit" button.
7. Bills and subscriptions: detected recurring payments with next due date and usual amount; "Pay now" and "Set up Autopay" buttons; confirm or dismiss each detection.
8. Transaction detail sheet: category (editable), merchant, note, "apply to all from this merchant".
9. Assistant settings: language (English / नेपाली / Auto), calendar (AD/BS), alerts, a plain-language explanation of how data is used, clear chat history.

## Notifications
Budget at 80% and 100%, bill due in 3 days, unusual spending, and a weekly summary on a configurable day.

## Integration readiness
- Backend: a TransactionSource interface with MockTransactionSource (SQLite seed) now and KhaltiTransactionSource later. Same pattern for bills and deposits.
- App: everything lives under app/lib/features/ai_assistant/ with no dependency on app internals. Repositories talk to the backend through one ApiClient.
- HostAppBridge interface in the app: openSendMoney(prefill), openBillPayment(service, prefill), openAutopay(), openSmartDeposit(), authenticate(). Provide a mock implementation that shows a "would open X" sheet.
- One theme file holds all design tokens, so they can be mapped to the app's design system.
- The whole feature sits behind a feature flag.
- FastAPI's generated OpenAPI spec is the API contract.

## Mock data
A seed script creating one demo user with 90 days and about 150 transactions: invented but realistic Nepali merchants (cafés, marts, bakeries), Electricity, Khanepani, Internet/TV, Topup & Data, bus tickets, remittance received, transfers to friends, and Smart Deposit installments. Starting balance around Rs. 15,000. Use a fixed random seed so the data is reproducible. Include about 15 mock FAQ entries for search_help_articles.

## Formatting
- Currency: "Rs." with Nepali lakh grouping (Rs. 1,25,000.50).
- Dates: AD by default with a BS toggle. Use a maintained BS-date package (e.g. nepali_utils in Flutter, nepali-datetime in Python).

## Public website first (decided 9 Nov 2026)
For now the assistant ships as a separate public website; merging into the Khalti app comes later.
- The website is the Flutter app built for web (same code merges into the Khalti app later).
- On desktop, show a centered phone-width column; the design stays mobile-first.
- Visible label on every screen: "Unofficial prototype, not affiliated with Khalti". No Khalti logos.
- Each visitor gets their own copy of the demo data (budgets, goals, chat history), not one shared user.
- Rate-limit /chat per visitor and overall so the free Groq quota can't be drained.
- Bundle DM Sans and Noto Sans Devanagari (OFL) instead of relying on system fonts.
- The website opens straight into the O-Kay chat (decided 13 Nov 2026): no stand-in Khalti home
  screen or bottom nav. The chat's header leads to Money Insights, alerts and settings. The
  entry points under "Screens" 1 (Ask me button, Money Insights tile) are for the Khalti app.
- Hosting (decided 11 Nov 2026): the website on GitHub Pages (public repo
  poudelnishan60-star/okay-money-assistant, built by GitHub Actions), the backend on Render's
  free plan (render.yaml; deployed by hand). The Groq key lives only in Render's environment.
  No "Khalti" in public names.

## Build order
All nine steps are done (the site went live on 12 Nov 2026). The order after step 4 was changed to chat first.
1. Repo setup: folders, README, .env.example, .gitignore, lint config
2. Backend data: SQLite schema, mock-data seed, categorizer, recurring-payment detector, budget math, forecast, with unit tests
3. Backend REST API: transactions, insights, budgets, goals, bills
4. App foundation: theme tokens, shared components, navigation, ApiClient, HostAppBridge mock
5. Backend AI: Groq LLMClient, tools, /chat streaming, system prompt, masking, 429 handling, per-visitor demo sessions, rate limits
6. App chat: bundled fonts, website layout (phone-width column, unofficial label), O-Kay chat screen with streaming, rich cards, suggestion chips, confirmations
7. App screens: insights dashboard, transactions, budgets, goals, bills, settings
8. Notifications, polish, golden tests for key screens, and an evaluation script with 50 questions (English, Nepali, Romanized Nepali) that checks the expected tool calls and numbers
9. Deploy: host the website and the backend (choice of hosts decided then)
