"""Mock help articles for search_help_articles.

MOCK CONTENT for the prototype only: wording is generic and deliberately avoids fees,
limits and other numbers. Replace with Khalti's official help articles before launch.
"""

FAQ_ARTICLES: list[tuple[str, str, str]] = [
    (
        "How do I load money into my Khalti wallet?",
        "Open Load Money, pick your bank or linked account, enter the amount and confirm. "
        "The money shows in your wallet once the bank approves it.",
        "load fund add money bank topup wallet",
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
        "electricity nea bill bijuli",
    ),
    (
        "How do I pay my Khanepani bill?",
        "Open Khanepani, choose your water office (for example KUKL), enter your customer "
        "number, check the bill and pay.",
        "khanepani water kukl bill pani",
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
        "smart deposit saving save automatic goal",
    ),
    (
        "How do I set up Autopay for a bill?",
        "After paying a bill, choose Set up Autopay, pick the date and confirm. Khalti will "
        "remind you before each payment, and you can turn it off at any time.",
        "autopay automatic bill schedule recurring",
    ),
    (
        "A payment failed but money was deducted. What should I do?",
        "Failed payments are normally reversed to your wallet automatically. Check the "
        "transaction status in your history; if it still shows deducted, contact support with "
        "the transaction ID.",
        "failed payment deducted refund reversal pending stuck",
    ),
    (
        "I forgot my MPIN. How do I reset it?",
        "Go to Settings, Security, Reset MPIN and verify with the OTP sent to your phone. "
        "Never share your MPIN or OTP with anyone, including people who say they are from "
        "Khalti.",
        "mpin forgot reset pin password security",
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
        "send money transfer friend wallet p2p",
    ),
    (
        "Can I receive remittance in Khalti?",
        "Yes. Ask the sender to choose Khalti as the payout method with your registered mobile "
        "number. You will get a notification when it reaches your wallet.",
        "remittance receive abroad foreign payout",
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
]
