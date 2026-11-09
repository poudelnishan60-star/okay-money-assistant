"""Follow-up chips under each answer, chosen in code from what the answer was about, in the
user's language (English, Nepali, Romanized Nepali)."""

from __future__ import annotations

from app.ai.cards import Suggestion
from app.ai.safety import Lang

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
    "top_merchants": {
        Lang.EN: "Where do I spend the most?",
        Lang.NE: "सबैभन्दा धेरै कहाँ खर्च हुन्छ?",
        Lang.ROM: "Sabai bhanda dherai kaha kharcha hunchha?",
    },
}

_BY_TOPIC: dict[str, list[str]] = {
    "spending": ["month_vs_last", "top_merchants", "food_budget"],
    "transactions": ["where_money", "month_vs_last", "my_budgets"],
    "budgets": ["per_day", "where_money", "run_low"],
    "budget_proposal": ["my_budgets", "per_day"],
    "goals": ["run_low", "where_money"],
    "goal_proposal": ["goals", "run_low"],
    "bills": ["pay_electricity", "run_low"],
    "forecast": ["bills_week", "per_day", "where_money"],
    "help": ["where_money", "bills_week"],
    "app_flow": ["bills_week", "run_low"],
}
_DEFAULT = ["month_vs_last", "where_money", "food_budget"]  # the empty-state chips

_SMART_DEPOSIT = Suggestion(text="Smart Deposit", type="feature", feature="smart_deposit")
_AUTOPAY = Suggestion(text="Autopay", type="feature", feature="autopay")


def suggestions_for(
    topics: set[str], lang: Lang, asked: str = "", limit: int = 3
) -> list[Suggestion]:
    order = [
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
    asked_norm = asked.strip().lower().rstrip("?")
    chips = [
        Suggestion(text=_CHIPS[c][lang])
        for c in ids
        if _CHIPS[c][lang].lower().rstrip("?") != asked_norm
    ][:limit]
    if topics & {"goals", "goal_proposal"}:
        chips.append(_SMART_DEPOSIT)
    elif "bills" in topics:
        chips.append(_AUTOPAY)
    return chips
