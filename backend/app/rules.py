"""Khalti's wallet rules as data: transaction limits, the overnight balance cap, KYC,
security, refunds and complaint times. The one place these values live: get_wallet_rules
quotes them, open_app_flow checks amounts against them, and later the help articles fill in
their numbers from here.

They are never written into the system prompt: the grounding check only accepts "Rs."
amounts that appear in a tool result, so they reach the model through get_wallet_rules.

Values are for KYC-verified users. Money is integer paisa (Rs. 1 = 100).

TODO before launch: verify every value against NRB's Unified Payment System Directive 2082
(Apr 2026) with Khalti compliance; the source below predates it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.money import format_npr

SOURCE = "Khalti Terms & Conditions and Transaction Limits page (NRB Unified Directive, 7 Mar 2025)"
LAST_CHECKED = dt.date(2026, 11, 24)
# Checked again on 24 Nov 2026 against the fact sheet "Khalti by IME: Company Fact Sheet"
# (khalti.com/info/transaction-limits, /info/terms, /info/charges): it added the Khalti card
# limits, cardless ATM withdrawal, inactive wallets and Khalti's rights. Checked on 25 Nov 2026
# against khalti.com's public pages (data the user gave): the limits match; fees, the dispute
# and dormant-wallet policies, KYC timing and bank transfers were added. Where the site
# contradicts itself, the official pages win (the transaction-limits page, which follows NRB,
# and the charges page; the user's decision, 25 Nov 2026).

# --- transaction limits ------------------------------------------------------------------

MIN_PAYMENT_PAISA = 10_00  # any transfer or payment
ESCROW_MIN_PAISA = 100_00


@dataclass(frozen=True, slots=True)
class Limit:
    key: str
    label: str
    per_txn_paisa: int
    per_day_paisa: int
    per_month_paisa: int
    min_paisa: int = MIN_PAYMENT_PAISA


LIMITS: dict[str, Limit] = {
    lim.key: lim
    for lim in (
        Limit("merchant_payment", "Merchant payment", 2_00_000_00, 2_00_000_00, 10_00_000_00),
        Limit("bank_to_wallet", "Bank to wallet", 2_00_000_00, 2_00_000_00, 10_00_000_00),
        Limit("wallet_to_bank", "Wallet to bank", 2_00_000_00, 2_00_000_00, 10_00_000_00),
        Limit("wallet_to_wallet", "Wallet to wallet", 50_000_00, 50_000_00, 5_00_000_00),
        Limit(
            "escrow", "Khalti Escrow", 25_000_00, 50_000_00, 5_00_000_00, min_paisa=ESCROW_MIN_PAISA
        ),
        Limit(
            "card_load_visa_mastercard",
            "Card load (Visa/Mastercard)",
            1_00_000_00,
            2_00_000_00,
            10_00_000_00,
        ),
        Limit("card_load_sct", "Card load (SCT)", 1_00_000_00, 2_00_000_00, 5_00_000_00),
        Limit(
            "khalti_card_online_pos",
            "Khalti card: online/POS",
            2_00_000_00,
            5_00_000_00,
            10_00_000_00,
        ),
        Limit("khalti_card_atm", "Khalti card: ATM", 5_000_00, 25_000_00, 25_000_00),
        Limit("khalti_card_contactless", "Khalti card: contactless", 5_000_00, 5_000_00, 50_000_00),
    )
}

# The app flows whose amount is checked against a limit before a button is shown.
FLOW_LIMITS = {
    "send_money": "wallet_to_wallet",
    "load_money": "bank_to_wallet",
    "withdraw_to_bank": "wallet_to_bank",
}

NO_LIMIT_PAYMENTS = (
    "government taxes, fees and fines",
    "electricity, telecom and drinking water bills",
    "insurance premiums",
    "social security contributions",
    "school fees",
)
# The services in the wallet history that are among them (left out of merchant payments).
NO_LIMIT_SERVICES = frozenset({"electricity", "khanepani", "mobile_topup", "data_pack"})

# Cash from Nabil Bank ATMs without a card, with an OTP (since January 2026).
CARDLESS_ATM_PER_DAY_PAISA = 5_000_00
CARDLESS_ATM_PER_MONTH_PAISA = 25_000_00

# Services that mark a transfer as to or from a bank account rather than another wallet.
BANK_LOAD_SERVICE = "bank_load"
BANK_WITHDRAW_SERVICE = "bank_withdraw"

# --- balance and deposits ----------------------------------------------------------------

OVERNIGHT_BALANCE_CAP_PAISA = 50_000_00
OVERNIGHT_CAP_RULE = "Anything above it must be moved out of the wallet before the day ends."

DEPOSITS_PER_DAY = 10  # deposits into a personal wallet
DEPOSIT_COUNT_NOTE = (
    "NRB sometimes raises this for a season, as it did to 50 a day from Dashain to Chhath 2026."
)

# --- KYC, security, refunds --------------------------------------------------------------

KYC_RULES = (
    "KYC must be verified before any transaction.",
    "One wallet per KYC.",
    "Not more than one wallet on one phone in 30 days.",
    "No false KYC and no one else's KYC.",
)

KYC_VERIFY_HOURS = 48  # "1-2 days (up to 48 hours)", khalti.com/kyc

# Dormant wallets (khalti.com/info/inactive-and-dormant-wallet-treatment-policy).
DORMANT_AFTER_MONTHS = 18  # a personal wallet with no transaction
DORMANT_AFTER_MONTHS_BUSINESS = 6  # merchants, POS and dealers
DORMANT_WARNING_DAYS = 15
DORMANT_ARCHIVE = "10 years and 90 days"
DORMANT_RULES = (
    f"A wallet with no transaction for {DORMANT_AFTER_MONTHS} months becomes dormant "
    f"({DORMANT_AFTER_MONTHS_BUSINESS} months for merchant, POS and dealer wallets): sign-in "
    "and all payments stop.",
    f"Khalti sends an SMS or email {DORMANT_WARNING_DAYS} days before, and again once it is "
    "locked.",
    "To reopen a KYC-verified wallet: a written letter, a photo of you holding your original "
    "ID and proof of address. An unverified wallet: an OTP on your mobile, two past "
    "transactions confirmed, and KYC completed.",
    f"Money unclaimed after {DORMANT_ARCHIVE} goes to CSR or as Nepal Rastra Bank directs; "
    "records are kept for 10 years.",
)

# The account itself (Khalti's terms).
ACCOUNT_RULES = (
    f"A wallet unused for {DORMANT_AFTER_MONTHS} months becomes dormant and is locked. To "
    "reopen it, contact Khalti and verify yourself (see the dormant wallet rules).",
    "Khalti can hold, block or close a wallet, or report it to the authorities, without notice.",
    "Nepali law applies, and cases go to courts in Kathmandu.",
)

FRAUD_WRITTEN_REPORT_HOURS = 24
SECURITY_RULES = (
    "Keep your MPIN and password secret; Khalti never asks for them.",
    "Report fraud to Khalti right away; if you report by phone, follow up in writing within "
    f"{FRAUD_WRITTEN_REPORT_HOURS} hours.",
    "Khalti isn't responsible for losses on a rooted or jailbroken phone.",
)

# Khalti support's contacts (fact sheet, 24 Nov 2026). O-Kay adds them to every answer where
# support comes up (chat.py), and the "How do I contact Khalti?" article uses them.
SUPPORT_EMAIL = "support@khalti.com"
SUPPORT_LANDLINE = "01-5970017"
SUPPORT_TOLL_FREE = "16600158888"  # NTC
SUPPORT_WHATSAPP_VIBER = "+977 9801165561"
DISPUTE_EMAIL = "dispute@khalti.com"
GRIEVANCE_OFFICER = "Anil Tharu, +977 9801856460, grievance@khalti.com (24/7)"
NRB_COMPLAINTS = "gunaso.nrb.org.np"
# Khalti's own published numbers (khalti.com/contact). Not the user's data: masking leaves
# them, so an answer that quotes them still shows them after the chat is reopened.
KHALTI_PUBLIC_NUMBERS = (
    SUPPORT_LANDLINE,
    SUPPORT_TOLL_FREE,
    SUPPORT_WHATSAPP_VIBER,
    "9801856460",
    "01-4217601",
    "9801492103",
    "9801856364",
    "9801462817",
    "9801129427",
    "9801165557",
    "9801301163",
    "9801856394",
    "9801890085",
    "9801165565",
    "9843007232",
    "9801856315",
    "9801856369",
    "9801856383",
    "9801856422",
    "9801856475",
    "01-5970053",
    "9801890083",
)
KHALTI_EMAIL_DOMAIN = "khalti.com"

REFUND_HOURS = 24
# NOT in the source: how long a pending transaction takes to go through or fail. Assumed
# to be the refund time until Khalti confirms its own figure.
PENDING_SETTLE_HOURS = 24
COMPLAINT_REPLY_HOURS = 72
CARD_DISPUTE_DAYS = 15
REFUND_RULES = (
    f"A failed transaction is refunded within {REFUND_HOURS} hours where a refund applies; "
    "it can take longer when a bank, another company or a government body is involved.",
    f"Complaints are answered within {COMPLAINT_REPLY_HOURS} hours.",
    f"Raise a card transaction dispute within {CARD_DISPUTE_DAYS} days.",
    "A dispute with a merchant (goods, service, refund policy) is between you and the merchant.",
)

# Khalti's dispute policy (khalti.com/info/disputepolicy).
DISPUTE_DAYS = 30
DISPUTE_RESOLUTION_DAYS = "20 to 25"
SUSPICIOUS_PROOF_DAYS = 35
DISPUTE_RULES = (
    f"Raise a dispute in writing within {DISPUTE_DAYS} days: email {DISPUTE_EMAIL} (or post) "
    "with your Khalti ID, the amount, the date, the other party's details, screenshots, a "
    "copy of your ID and a signed handwritten letter.",
    f"Khalti resolves it in {DISPUTE_RESOLUTION_DAYS} days (longer for complex cases).",
    f"For a transaction flagged as suspicious, proof is asked for within {SUSPICIOUS_PROOF_DAYS} "
    "days.",
    "Not covered: merchants that aren't authorised and don't deliver, money sent to the wrong "
    "Khalti user, and betting, gambling, gift cards, crypto, unknown cash or forex.",
    "For fraud, report to the police or the Cyber Bureau first.",
    f"If Khalti doesn't resolve it, complain to Nepal Rastra Bank at {NRB_COMPLAINTS}.",
)

# Withdrawing to a bank (khalti.com/bank-transfer; its limits are the limits page's).
BANK_TRANSFER_RULES = (
    "It reaches the bank within seconds.",
    "It can't be reversed once sent: check the account name and number first.",
    "Steps: Bank Transfer, choose the bank and branch, enter the account name, number and "
    "amount, then Withdraw.",
)

# --- fees ------------------------------------------------------------------------------------
# Quoted since 25 Nov 2026 (before, O-Kay only said the app shows them). From the charges page;
# where another page says otherwise, the charges page wins (the user's decision).


def _rs(paisa: int) -> str:
    return format_npr(paisa)


FEES_SOURCE = "Khalti's charges page (khalti.com/info/charges), read 25 Nov 2026"
FEES_NOTE = (
    "Fees change often and VAT applies where required: the Khalti app shows the fee before "
    "you confirm."
)
MEMBERSHIP_PRICE_PAISA = 599_00
FEES: dict[str, tuple[str, ...]] = {
    "sending": (
        f"Khalti to Khalti: free below {_rs(100_00)}; above that free for 3 a day and 30 a "
        f"month, then {_rs(10_00)} each.",
        f"To a linked bank account: the first 3 a month free, then {_rs(10_00)} each.",
        "To a bank account that isn't linked: a flat fee (the amount isn't published).",
    ),
    "loading": (
        "From a Nepali Visa or Mastercard card: 3%.",
        "From a foreign Visa or Mastercard card: 5%.",
    ),
    "bills": (
        f"NEA electricity and KUKL water: free below {_rs(500_00)}, {_rs(5_00)} from "
        f"{_rs(500_00)}.",
        f"Community electricity: {_rs(7_00)}.",
        f"Community water: free below {_rs(60_00)}, {_rs(5_00)} for {_rs(61_00)} to "
        f"{_rs(150_00)}, {_rs(10_00)} above.",
        "TV (DTH): no Khalti service charge.",
        f"Government payments: {_rs(5_00)} up to {_rs(5_000_00)}, {_rs(8_00)} up to "
        f"{_rs(10_000_00)}, {_rs(10_00)} above.",
        f"Credit card bill: {_rs(15_00)} for {_rs(100_00)} to {_rs(1_000_00)}, {_rs(25_00)} up "
        f"to {_rs(10_000_00)}, {_rs(35_00)} up to {_rs(30_000_00)}, {_rs(60_00)} up to "
        f"{_rs(1_00_000_00)}.",
        f"School fee: {_rs(10_00)}.",
        f"Social Security Fund: {_rs(5_00)}.",
        f"SIP: {_rs(10_00)}.",
        f"EMI payment: {_rs(10_00)} (100% cashback through Hulas Finserve in the app).",
        f"Bluebook renewal: {_rs(200_00)}.",
        f"Demat / Mero Share renewal: {_rs(5_00)}.",
        f"Broker collateral load: {_rs(5_00)} up to {_rs(1_000_00)}, {_rs(10_00)} above.",
        f"Loan against IME Life insurance: {_rs(50_00)}.",
    ),
    "cards": (
        f"Virtual card: {_rs(25_00)} a quarter.",
        f"Physical card: {_rs(250_00)} to issue, {_rs(250_00)} a year to renew, {_rs(250_00)} "
        "to replace a lost or damaged card.",
        f"Physical card at an ATM: {_rs(15_00)} a withdrawal or balance enquiry.",
        f"Chargeback handling: {_rs(1_000_00)}. PIN change: a fee after the second request "
        "(amount not published).",
    ),
    "other": (
        f"Paying a business through Khalti's payment gateway: {_rs(5_00)} or {_rs(10_00)}.",
        f"Cash without a card at a Nabil Bank ATM: {_rs(15_00)}.",
        f"Khalti Escrow: {_rs(10_00)}; settling an escrow dispute {_rs(100_00)}, paid by the "
        "one who complains.",
        f"Agent-assisted bank deposit: {_rs(100_00)} up to {_rs(25_000_00)}, {_rs(150_00)} up to "
        f"{_rs(50_000_00)}. Agent-assisted transfer: {_rs(100_00)} up to {_rs(10_000_00)}, "
        f"{_rs(200_00)} up to {_rs(25_000_00)}, {_rs(300_00)} up to {_rs(50_000_00)}.",
    ),
    "membership": (
        f"Khalti Membership: {_rs(MEMBERSHIP_PRICE_PAISA)}. It gives 2% cashback on your own "
        f"mobile top-ups, coupons up to {_rs(100_00)} a month for 10 months, double Khalti "
        "Points, unlimited free Khalti-to-Khalti transfers, 8 free bank transfers a month and "
        f"{_rs(100_00)} off one bluebook renewal.",
    ),
}
FEE_GROUPS = tuple(FEES)
