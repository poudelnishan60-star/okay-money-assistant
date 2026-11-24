"""Mock help articles for search_help_articles.

The how-to articles are MOCK CONTENT for the prototype, generic and without numbers;
replace them with Khalti's official help articles before launch. The company articles
(what Khalti is, the IME Pay merger, who runs it, services, Super Wallet, contacts,
cardless cash, businesses, awards...) come from the fact sheet "Khalti by IME: Company
Fact Sheet" (24 Nov 2026). The articles on Khalti's
rules (limits, the overnight balance cap, KYC and one wallet, refunds and complaints,
fraud or a lost phone, scams, card disputes) take every number from app/rules.py, so the
help, the get_wallet_rules tool and the limit checks never disagree. No fee amounts: fees
are shown in the Khalti app.
"""

from app.money import format_npr
from app.rules import (
    ACCOUNT_RULES,
    CARDLESS_ATM_PER_DAY_PAISA,
    CARDLESS_ATM_PER_MONTH_PAISA,
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
        "My wallet hasn't been used for a long time. Is it still active?",
        ACCOUNT_RULES[0],
        "inactive dormant unused old wallet reactivate closed",
    ),
]

# Facts about Khalti from the fact sheet "Khalti by IME: Company Fact Sheet" (24 Nov 2026; its
# sources: khalti.com/about, /info/*, docs.khalti.com, the App Store and Nepali news). Left out
# on purpose: fee amounts (the app shows them; decided 24 Nov 2026) and the developer test
# accounts' MPIN and OTP (O-Kay never states an MPIN or OTP).
COMPANY_ARTICLES: list[tuple[str, str, str]] = [
    (
        "What is Khalti by IME?",
        "Khalti is Nepal's largest digital wallet. Since July 2025 it has run as Khalti by IME "
        "under IME Khalti Limited, after merging with IME Pay, licensed by Nepal Rastra Bank as "
        "a payment service provider. It has 12.7 million registered users (about 5 million "
        'verified). It launched on 26 January 2017 at CAN Infotech; "Khalti" is Nepali for '
        '"pocket". Registered office: Panipokhari-03, Kathmandu. You can sign up only in the '
        "app, not on the website.",
        "khalti ime company about what is who owns licence license nrb users pocket sign up "
        "register website",
    ),
    (
        "What happened to IME Pay?",
        "IME Pay and Khalti merged: an MoU in February 2025, Nepal Rastra Bank's final approval "
        "on 19 June 2025 (the first merger in Nepal's digital payments), and joint operation as "
        "Khalti by IME from 17 July 2025 (2082/04/01). The IME Pay app closed on Kartik 30, "
        "2082, and accounts that hadn't moved to Khalti stopped working. IME Pay users kept "
        "their balance, interest and reward points; Daami Points now combine both apps' rewards.",
        "ime pay imepay merger merge closed moved migrate old account daami points",
    ),
    (
        "Who founded Khalti?",
        "Amit Agrawal, Arbin Sah, Dhruva Adhikari and Manish Modi. Three of them had started "
        "Janaki Technology in 2007 and Sparrow SMS in 2010. The app was finished in 15 days, in "
        "two rented rooms in Pulchowk, for the CAN fair in January 2017. Before the merger "
        "Sparrow Pay ran Khalti from Bakhundole, Lalitpur; WorldLink and Triveni Group invested "
        "later.",
        "founder founders founded history started who made sparrow",
    ),
    (
        "Who runs Khalti?",
        "Chairman: Krishna Prasad Sharma. Acting CEO: Ashish Gautam (as Khalti's About page "
        "lists; before him Binay Khadka, then Praveen Regmi from 17 November 2025). Chief "
        "Product Officer Sanjeev Chandra Neupane, Chief Technology Officer Subit Raj Pokharel, "
        "Chief Operating Officer Puspa Raj Nyaupane, Chief Financial Officer Ajit Bagale, Chief "
        "Risk Officer Ujjwal Das Shrestha. Directors: Sachin Dhakal, Amit Agrawal, Dhruba "
        "Adhikari, Dibakar Paudel, Manish Modi and Sitaram Thapa.",
        "ceo chairman leadership management director directors board who runs head boss",
    ),
    (
        "What can I do with Khalti?",
        "Top up NTC and Ncell and buy data packs; pay electricity (NEA, BPC, community), water, "
        "landline, TV and internet bills; book domestic flights, hotels, movie and event "
        "tickets; pay school and college fees, Lok Sewa, IRD, DOFE, SSF, traffic fines and "
        "municipal tax; pay insurance, EMIs and credit card bills and renew DEMAT/MeroShare and "
        "your bluebook; receive money from abroad (WorldRemit, Remitly); Scan & Pay with Khalti "
        "QR; send, request and move money to and from banks; earn interest with Super Wallet "
        "and save with Smart Deposit; collect Daami Points; get prepaid and virtual Visa cards.",
        "services features what can i do offer pay bills recharge book tickets insurance emi",
    ),
    (
        "What is Super Wallet?",
        "Super Wallet pays interest on your wallet balance through Global IME Bank: 2.75% a "
        "year in May 2026 (the App Store says 3%). Interest is worked out daily and paid "
        "monthly, and the rate can change each month. It has been open to all KYC-verified "
        "users since May 2026.",
        "super wallet interest balance rate earn byaj ब्याज",
    ),
    (
        "How do I contact Khalti?",
        "Support: support@khalti.com, landline 01-5970017, toll-free (NTC) 16600158888, "
        "WhatsApp/Viber +977 9801165561. Grievance officer: Anil Tharu, +977 9801856460, "
        "grievance@khalti.com (24/7). If Khalti doesn't resolve a complaint, you can complain "
        "to Nepal Rastra Bank at gunaso.nrb.org.np. Businesses: merchant@khalti.com. O-Kay can "
        "also open Khalti support with a transaction attached.",
        "contact support phone number email customer care call helpline grievance complaint "
        "person talk human",
    ),
    (
        "Can I withdraw cash without a card?",
        "Yes, at Nabil Bank ATMs, with an OTP instead of a card (since January 2026): up to "
        f"{format_npr(CARDLESS_ATM_PER_DAY_PAISA)} a day and "
        f"{format_npr(CARDLESS_ATM_PER_MONTH_PAISA)} a month. The steps are shown in the "
        "Khalti app; this article doesn't list them.",
        "cash withdraw withdrawal atm cardless without card nabil otp paisa jhikne",
    ),
    (
        "Can freelancers receive payments from abroad?",
        "Yes. Since April 2026 freelancers can receive payments from abroad straight into the "
        "wallet, through a system built with Stripe. Money from abroad also comes through "
        "WorldRemit and Remitly.",
        "freelancer freelance abroad stripe foreign payment international receive",
    ),
    (
        "What's new at Khalti?",
        "August 2026: Khalti joined IRD's Taxpayer Incentive Gift Programme 2083: payments over "
        "Rs. 100 are entered into daily and fortnightly prize draws. May 2026: Super Wallet "
        "opened to all KYC-verified users, and Khalti Stock Hub launched at Khalti Jatra 2083. "
        "April 2026: freelancers can receive payments from abroad (Stripe). January 2026: cash "
        "from Nabil Bank ATMs without a card.",
        "new latest recent update updates 2026 stock hub draw taxpayer ird jatra",
    ),
    (
        "Does Khalti work for businesses?",
        "Yes: Payment Gateway, Khalti Pasal, Bazaar, school fee payment, corporate and agent "
        "services, international remittance and Daami QR (QR payments that give customers "
        "instant rewards and give the business information about its buyers). The gateway has "
        "web checkout, SDKs for Android, Flutter and iOS, and WooCommerce and WHMCS plugins, "
        "and accepts the Khalti wallet, partner banks' e-banking and mobile banking, SCT/VISA "
        "cards and connectIPS. Developers: docs.khalti.com (test at dev.khalti.com, live at "
        "khalti.com/api/v2). Contact: merchant@khalti.com.",
        "business merchant payment gateway api developer integrate website sdk qr shop seller",
    ),
    (
        "How big is Khalti?",
        "12.7 million registered users (about 5 million verified), 10 million+ transactions a "
        "month, 50+ bank and financial institution partners (another Khalti page says 60+) and "
        "100,000+ POS and agent points. Its main competitor is eSewa, estimated at about 80% "
        "of the market.",
        "users how many size big transactions partners banks esewa market",
    ),
    (
        "What awards has Khalti won?",
        "NCHL's award for the payment service provider processing the most digital "
        "transactions (2023 and 2024), NRB recognition for digital transactions (2024), the "
        "WITSA Global Innovation & Tech Excellence Award (2022) and the Google Business Group "
        "Stories Search Contest (global winner, 2017); also the United Nations Fintech "
        "Innovation Fund. IME Pay won the Digital Services ICT Award (2024), the HRM Award for "
        "Corporate Excellence in FinTech (2023) and the Visa Excellence in Fintech Partnership "
        "Award (2023).",
        "award awards prize recognition won achievement",
    ),
    (
        "Is Khalti safe?",
        "Khalti is licensed by Nepal Rastra Bank and holds ISO 27001:2013, plus PCI DSS and "
        f"AMTIVO badges. {SECURITY_RULES[0]} {SECURITY_RULES[2]}",
        "safe secure security certified iso pci trust trustworthy",
    ),
    (
        "What are Khalti's terms for my account?",
        " ".join(ACCOUNT_RULES) + " " + KYC_RULES[1],
        "terms conditions legal law court rights block close hold account",
    ),
    (
        "What are Khalti Membership and Khalti Pro?",
        "Paid loyalty plans, since February 2023. Membership gives 2% cashback on your own "
        "top-ups, double points and 8 free bank transfers a month. The price is shown in the "
        "app.",
        "membership pro loyalty plan cashback points premium",
    ),
    (
        "Is Khalti hiring?",
        "Send job applications to vacancy@khalti.com. Management trainees rotate through "
        "fintech operations, business strategy and growth, customer experience, product and "
        "service management, and risk and compliance. 2026 job posts were for risk and "
        "compliance, security testing, software development, social media and IT "
        "infrastructure.",
        "job jobs career careers hiring vacancy work trainee",
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
        "without you having to remember. It is a recurring deposit with Manjushree "
        "Finance, from Rs. 100, for 6 to 60 months.",
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
    *COMPANY_ARTICLES,
]
