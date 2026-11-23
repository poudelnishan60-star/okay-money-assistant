"""Mock help articles for search_help_articles.

MOCK CONTENT for the prototype only. Replace with Khalti's official help articles before
launch. The how-to articles are generic and have no numbers. The articles on Khalti's
rules (limits, the overnight balance cap, KYC and one wallet, refunds and complaints,
fraud or a lost phone, scams, card disputes) take every number from app/rules.py, so the
help, the get_wallet_rules tool and the limit checks never disagree. No fee amounts: fees
are shown in the Khalti app. The inactive-wallet article has no source yet (see there).
"""

from app.money import format_npr
from app.rules import (
    ESCROW_MIN_PAISA,
    FRAUD_WRITTEN_REPORT_HOURS,
    KYC_RULES,
    LIMITS,
    MIN_PAYMENT_PAISA,
    NO_LIMIT_PAYMENTS,
    OVERNIGHT_BALANCE_CAP_PAISA,
    OVERNIGHT_CAP_RULE,
    REFUND_HOURS,
    REFUND_RULES,
    SECURITY_RULES,
)


def _limit(key: str) -> str:
    lim = LIMITS[key]
    return (
        f"{lim.label}: {format_npr(lim.per_txn_paisa)} per transaction, "
        f"{format_npr(lim.per_day_paisa)} a day, {format_npr(lim.per_month_paisa)} a month"
    )


_CAP = format_npr(OVERNIGHT_BALANCE_CAP_PAISA)

# Articles on Khalti's rules; every number comes from app/rules.py.
RULE_ARTICLES: list[tuple[str, str, str]] = [
    (
        "What are Khalti's transaction limits?",
        "For KYC-verified users: "
        + "; ".join(_limit(k) for k in LIMITS)
        + f". No limit for {', '.join(NO_LIMIT_PAYMENTS)}. The minimum for any transfer or "
        f"payment is {format_npr(MIN_PAYMENT_PAISA)} (Khalti Escrow "
        f"{format_npr(ESCROW_MIN_PAISA)}). O-Kay can tell you how much of today's limit is left.",
        "limit limits maximum max how much send transfer daily monthly per day सीमा sima "
        "kati pathauna",
    ),
    (
        "How much money can I keep in my wallet?",
        f"You can keep up to {_CAP} in your wallet overnight. {OVERNIGHT_CAP_RULE} You can "
        "withdraw it to your bank account, put it in Smart Deposit or spend it.",
        "balance cap maximum keep hold overnight wallet limit over too much ब्यालेन्स",
    ),
    (
        "Can I have more than one Khalti wallet?",
        " ".join(KYC_RULES),
        "kyc wallet second another two account one phone identity someone else",
    ),
    (
        "How long do refunds and complaints take?",
        " ".join(REFUND_RULES),
        "refund time complaint how long reversal return money back failed firta फिर्ता dispute",
    ),
    (
        "I lost my phone or someone used my account. What do I do?",
        "Block your wallet right away in Khalti's security settings (O-Kay can open it for "
        f"you). {SECURITY_RULES[1]} Reset your MPIN and password once you can sign in "
        f"again. {SECURITY_RULES[2]}",
        "lost phone stolen fraud hacked block report someone used account mpin shared "
        "हरायो harayo chori",
    ),
    (
        "How do I spot a scam?",
        "Khalti never asks for your OTP, MPIN or password, by phone, SMS or social media. A "
        "caller who says they are from Khalti and asks for a code is a scam, and so is a prize "
        "or lottery that needs a fee first. Don't pay or share anything, and report it to "
        f"Khalti right away, then in writing within {FRAUD_WRITTEN_REPORT_HOURS} hours.",
        "scam fraud fake call caller prize lottery fee otp mpin ठगी thagi",
    ),
    (
        "How do I dispute a card payment?",
        f"{REFUND_RULES[2]} Contact Khalti support with the transaction attached (O-Kay can "
        f"open it for you). {REFUND_RULES[3]}",
        "card dispute chargeback visa mastercard wrong charge merchant",
    ),
    (
        # NOT from the source: it has no rule for inactive wallets, so no numbers here.
        # Check with Khalti compliance before launch.
        "My wallet hasn't been used for a long time. Is it still active?",
        "A wallet that hasn't been used for a long time may be marked inactive. To use it "
        "again, contact Khalti support; you may be asked to verify your KYC again.",
        "inactive dormant unused old wallet reactivate closed",
    ),
]

FAQ_ARTICLES: list[tuple[str, str, str]] = [
    (
        "How do I load money into my Khalti wallet?",
        "Open Load Money, pick your bank or linked account, enter the amount and confirm. "
        "The money shows in your wallet once the bank approves it.",
        "load fund add money bank topup wallet लोड पैसा हाल्ने बैंक halne",
    ),
    (
        "What is Scan & Pay?",
        "Scan & Pay lets you pay a shop by scanning its QR code. Tap the red Scan & Pay "
        "button, scan the code, check the merchant name and amount, then confirm with your "
        "MPIN or fingerprint.",
        "scan pay qr merchant shop fonepay",
    ),
    (
        "How do I pay my electricity (NEA) bill?",
        "Go to Electricity, choose your NEA counter, enter your SC number and customer ID, "
        "check the due amount and pay. You can save the account to pay faster next month.",
        "electricity nea bill bijuli बिजुली बिल",
    ),
    (
        "How do I pay my Khanepani bill?",
        "Open Khanepani, choose your water office (for example KUKL), enter your customer "
        "number, check the bill and pay.",
        "khanepani water kukl bill pani खानेपानी पानी",
    ),
    (
        "How do I buy a data pack or mobile topup?",
        "Open Topup & Data, enter the mobile number, pick a topup amount or a data pack and "
        "confirm. Packs are added to the number within a few moments.",
        "topup recharge data pack ntc ncell mobile balance",
    ),
    (
        "What is Smart Deposit?",
        "Smart Deposit saves a fixed amount for you on a schedule, so your savings grow "
        "without you having to remember. You choose the amount and how often.",
        "smart deposit saving save automatic goal बचत bachat",
    ),
    (
        "How do I set up Autopay for a bill?",
        "After paying a bill, choose Set up Autopay, pick the date and confirm. Khalti will "
        "remind you before each payment, and you can turn it off at any time.",
        "autopay automatic bill schedule recurring",
    ),
    (
        "A payment failed but money was deducted. What should I do?",
        "Failed payments are normally reversed to your wallet automatically, within "
        f"{REFUND_HOURS} hours where a refund applies. Check the transaction status in your "
        "history; if it is still not back after that, contact support with the transaction "
        "ID (O-Kay can open support with it attached).",
        "failed payment deducted refund reversal pending stuck",
    ),
    (
        "I forgot my MPIN. How do I reset it?",
        "Go to Settings, Security, Reset MPIN and verify with the OTP sent to your phone. "
        "Never share your MPIN or OTP with anyone, including people who say they are from "
        "Khalti.",
        "mpin forgot reset pin password security एमपिन बिर्सें birse",
    ),
    (
        "How do I complete KYC?",
        "Open your profile, choose KYC, fill in your details and upload a clear photo of your "
        "ID and yourself. Verification lets you use more services.",
        "kyc verify identity document citizenship",
    ),
    (
        "How do I send money to a friend?",
        "Open Send Money, enter your friend's Khalti ID or mobile number, the amount and an "
        "optional note, then confirm with your MPIN.",
        "send money transfer friend wallet p2p पठाउने pathaune",
    ),
    (
        "Can I receive remittance in Khalti?",
        "Yes. Ask the sender to choose Khalti as the payout method with your registered mobile "
        "number. You will get a notification when it reaches your wallet.",
        "remittance receive abroad foreign payout रेमिट्यान्स विदेश bidesh",
    ),
    (
        "How do I book bus or flight tickets?",
        "Open Bus or Flight under Travel, search your route and date, choose a seat or fare "
        "and pay. Your ticket appears in your booking history.",
        "bus flight ticket booking travel hotel",
    ),
    (
        "Is it safe to share my OTP?",
        "No. Your OTP and MPIN are only for you. Khalti and O-Kay will never ask for them. If "
        "someone asks, do not share and report it to support.",
        "otp share safe fraud scam security",
    ),
    (
        "How do I see my transaction history or a statement?",
        "Tap Transaction in the bottom bar. Use the 7, 14 or 30 day chips or a custom range to "
        "filter, and open any transaction to see its details.",
        "history statement transactions record",
    ),
    (
        "What does O-Kay do with my data?",
        "O-Kay reads your Khalti transactions to answer questions about your spending. Phone "
        "numbers, account numbers and reference IDs are masked before anything is sent to the "
        "AI service, and O-Kay can never move money on its own.",
        "okay privacy data ai assistant safe",
    ),
    *RULE_ARTICLES,
]
