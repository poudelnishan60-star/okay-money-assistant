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

SOURCE = "Khalti Terms & Conditions and Transaction Limits page (NRB Unified Directive, 7 Mar 2025)"
LAST_CHECKED = dt.date(2026, 11, 20)

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

FRAUD_WRITTEN_REPORT_HOURS = 24
SECURITY_RULES = (
    "Keep your MPIN and password secret; Khalti never asks for them.",
    "Report fraud to Khalti right away, then in writing within "
    f"{FRAUD_WRITTEN_REPORT_HOURS} hours.",
    "Khalti isn't responsible for losses on a rooted or jailbroken phone.",
)

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
    # The source says only "card disputes within 15 days" (to raise or to settle?): kept
    # as worded until Khalti compliance confirms.
    f"Card disputes: within {CARD_DISPUTE_DAYS} days.",
    "A dispute with a merchant (goods, service, refund policy) is between you and the merchant.",
)

FEES_NOTE = (
    "Fees are shown in the Khalti app before you confirm a payment. O-Kay doesn't have the "
    "fee amounts."
)
