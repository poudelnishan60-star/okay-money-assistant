"""Follow-up chips under each answer, chosen in code from what the answer was about, in the
user's language (English, Nepali, Romanized Nepali).

Questions already asked in this chat are not offered again (unless nothing else is left), so
new ones come up as the chat goes on. After an answer about a file, more chips are shown (the
chip row scrolls), and a sheet only gets the questions its report can answer.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.ai.cards import Suggestion
from app.ai.safety import Lang

LIMIT = 3
FILE_LIMIT = 5  # after an answer about a file

# chip id -> text per language
_CHIPS: dict[str, dict[Lang, str]] = {
    "month_vs_last": {
        Lang.EN: "This month vs last",
        Lang.NE: "यो महिना र गत महिना",
        Lang.ROM: "Yo mahina ra gaya mahina",
    },
    "where_money": {
        Lang.EN: "Where did my money go?",
        Lang.NE: "मेरो पैसा कहाँ गयो?",
        Lang.ROM: "Mero paisa kaha gayo?",
    },
    "food_budget": {
        Lang.EN: "Set a food budget",
        Lang.NE: "खानाको बजेट बनाऊ",
        Lang.ROM: "Khana ko budget banau",
    },
    "per_day": {
        Lang.EN: "How much can I spend per day?",
        Lang.NE: "दिनमा कति खर्च गर्न सक्छु?",
        Lang.ROM: "Din ma kati kharcha garna sakchu?",
    },
    "my_budgets": {
        Lang.EN: "Show my budgets",
        Lang.NE: "मेरो बजेट देखाऊ",
        Lang.ROM: "Mero budget dekhau",
    },
    "bills_week": {
        Lang.EN: "Which bills are due soon?",
        Lang.NE: "कुन बिल चाँडै तिर्नुपर्छ?",
        Lang.ROM: "Kun bill chadai tirnu parchha?",
    },
    "pay_electricity": {
        Lang.EN: "Pay my electricity bill",
        Lang.NE: "बिजुलीको बिल तिर्नु",
        Lang.ROM: "Bijuli ko bill tirnu",
    },
    "goals": {
        Lang.EN: "How are my savings goals?",
        Lang.NE: "मेरो बचत लक्ष्य कस्तो छ?",
        Lang.ROM: "Mero bachat goal kasto chha?",
    },
    "run_low": {
        Lang.EN: "Will I run low this month?",
        Lang.NE: "यो महिना पैसा पुग्छ?",
        Lang.ROM: "Yo mahina paisa pugchha?",
    },
    "compare_spending": {
        Lang.EN: "How does this compare with my spending?",
        Lang.NE: "यो मेरो खर्चसँग कस्तो छ?",
        Lang.ROM: "Yo mero kharcha sanga kasto chha?",
    },
    "file_by_type": {
        Lang.EN: "Break the file down by type",
        Lang.NE: "फाइललाई प्रकार अनुसार छुट्याऊ",
        Lang.ROM: "File lai type anusar chhutyau",
    },
    "file_biggest": {
        Lang.EN: "Biggest payments in the file",
        Lang.NE: "फाइलका सबैभन्दा ठूला भुक्तानी",
        Lang.ROM: "File ka sabai bhanda thula payment",
    },
    "file_by_week": {
        Lang.EN: "Week by week in the file",
        Lang.NE: "फाइलमा हप्ता अनुसार",
        Lang.ROM: "File ma hapta anusar",
    },
    "file_unusual": {
        Lang.EN: "Anything unusual in the file?",
        Lang.NE: "फाइलमा केही असामान्य छ?",
        Lang.ROM: "File ma kehi asamanya chha?",
    },
    "file_cut_back": {
        Lang.EN: "Where can I cut back?",
        Lang.NE: "कहाँ खर्च कम गर्न सक्छु?",
        Lang.ROM: "Kaha kharcha kam garna sakchhu?",
    },
    "file_compare": {
        Lang.EN: "Compare the file with my Khalti account",
        Lang.NE: "फाइललाई मेरो खल्ती खातासँग तुलना गर",
        Lang.ROM: "File lai mero Khalti khata sanga tulana gara",
    },
    "file_in_out": {
        Lang.EN: "Money in vs money out in the file",
        Lang.NE: "फाइलमा आएको र गएको पैसा",
        Lang.ROM: "File ma aayeko ra gayeko paisa",
    },
    "file_balance": {
        Lang.EN: "How did the balance change?",
        Lang.NE: "ब्यालेन्स कसरी बदलियो?",
        Lang.ROM: "Balance kasari badliyo?",
    },
    "file_summary": {
        Lang.EN: "Sum up the file in 3 lines",
        Lang.NE: "फाइललाई ३ लाइनमा भन",
        Lang.ROM: "File lai 3 line ma bhana",
    },
    "file_paid_for": {
        Lang.EN: "What did I pay for?",
        Lang.NE: "मैले केको लागि तिरेँ?",
        Lang.ROM: "Maile ke ko lagi tirey?",
    },
    "money_flow": {
        Lang.EN: "Show my money flow",
        Lang.NE: "मेरो पैसाको आवतजावत देखाऊ",
        Lang.ROM: "Mero paisa ko aawat jawat dekhau",
    },
    "file_flow": {
        Lang.EN: "Money flow in the file",
        Lang.NE: "फाइलमा पैसाको आवतजावत",
        Lang.ROM: "File ma paisa ko aawat jawat",
    },
    "top_merchants": {
        Lang.EN: "Where do I spend the most?",
        Lang.NE: "सबैभन्दा धेरै कहाँ खर्च हुन्छ?",
        Lang.ROM: "Sabai bhanda dherai kaha kharcha hunchha?",
    },
}

_BY_TOPIC: dict[str, list[str]] = {
    "spending": ["month_vs_last", "money_flow", "top_merchants", "food_budget"],
    "transactions": ["where_money", "month_vs_last", "my_budgets"],
    "budgets": ["per_day", "where_money", "run_low"],
    "budget_proposal": ["my_budgets", "per_day"],
    "goals": ["run_low", "where_money"],
    "goal_proposal": ["goals", "run_low"],
    "bills": ["pay_electricity", "run_low"],
    "forecast": ["bills_week", "per_day", "where_money"],
    "help": ["where_money", "bills_week"],
    "app_flow": ["bills_week", "run_low"],
    # A photo or PDF (a receipt, a bill): what it was, and how it fits the account.
    "attachment": [
        "file_paid_for",
        "file_summary",
        "compare_spending",
        "where_money",
        "my_budgets",
    ],
    # A sheet (a statement): its report first, then reading it, then the account.
    "attachment_table": [
        "file_by_type",
        "file_biggest",
        "file_unusual",
        "file_cut_back",
        "file_by_week",
        "file_flow",
        "file_compare",
        "file_in_out",
        "file_balance",
        "file_summary",
    ],
}
_DEFAULT = ["month_vs_last", "where_money", "food_budget"]  # the empty-state chips
_FILE_TOPICS = {"attachment", "attachment_table"}
# Sheet chips that need a part of the sheet's report (sheets.report_parts): a sheet without
# a type column or dates doesn't get "by type" or "week by week".
_NEEDS = {
    "file_by_type": "types",
    "file_biggest": "biggest",
    "file_by_week": "periods",
    "file_in_out": "in_out",
    "file_flow": "in_out",
    "file_balance": "balance",
}

_SMART_DEPOSIT = Suggestion(text="Smart Deposit", type="feature", feature="smart_deposit")
_AUTOPAY = Suggestion(text="Autopay", type="feature", feature="autopay")


def _plain(text: str) -> str:
    return text.strip().lower().rstrip("?")


def suggestions_for(
    topics: set[str],
    lang: Lang,
    asked: str = "",
    limit: int | None = None,
    *,
    asked_before: Iterable[str] = (),
    file_parts: set[str] | None = None,
) -> list[Suggestion]:
    """`asked`: this question; `asked_before`: the user's earlier questions in this chat.
    `file_parts`: what the sheet's report shows (None: no sheet)."""
    order = [
        "attachment_table",
        "attachment",
        "budget_proposal",
        "goal_proposal",
        "app_flow",
        "forecast",
        "bills",
        "budgets",
        "goals",
        "spending",
        "transactions",
        "help",
    ]
    ids: list[str] = []
    for topic in order:
        if topic in topics:
            ids += [c for c in _BY_TOPIC[topic] if c not in ids]
    if not ids:
        ids = list(_DEFAULT)
    if file_parts is not None:
        ids = [c for c in ids if _NEEDS.get(c, "") in file_parts | {""}]
    if limit is None:
        limit = FILE_LIMIT if topics & _FILE_TOPICS else LIMIT
    now = _plain(asked)
    before = {_plain(a) for a in asked_before} | {now}
    texts = [_CHIPS[c][lang] for c in ids]
    fresh = [t for t in texts if _plain(t) not in before]
    if not fresh:  # everything was asked already: offer them again, but not this question
        fresh = [t for t in texts if _plain(t) != now]
    chips = [Suggestion(text=t) for t in fresh[:limit]]
    if topics & {"goals", "goal_proposal"}:
        chips.append(_SMART_DEPOSIT)
    elif "bills" in topics:
        chips.append(_AUTOPAY)
    return chips
