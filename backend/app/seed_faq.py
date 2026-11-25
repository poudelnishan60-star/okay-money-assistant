"""Mock help articles for search_help_articles.

The how-to articles are MOCK CONTENT for the prototype, generic and without numbers;
replace them with Khalti's official help articles before launch. The company articles
(what Khalti is, the IME Pay merger, who runs it, services, Super Wallet, contacts,
cardless cash, businesses, awards...) come from the fact sheet "Khalti by IME: Company
Fact Sheet" (24 Nov 2026). The articles on Khalti's
rules (limits, the overnight balance cap, KYC and one wallet, refunds and complaints,
fraud or a lost phone, scams, card disputes) take every number from app/rules.py, so the
help, the get_wallet_rules tool and the limit checks never disagree.

SITE_ARTICLES (25 Nov 2026) come from data the user gave from khalti.com's public pages:
the office, department contacts, apps, services and billers, loading money and partner
banks, bank transfers, disputes, fees, businesses, developers, Smart Chhori and policies.
Fees are quoted since then (the user's decision); like every rule, they come from
app/rules.py. Where khalti.com contradicts itself, the official pages win (the limits and
charges pages). Linked banks and cards carry over from IME Pay (this data replaced an
earlier "link them again").
"""

from app.money import format_npr
from app.rules import (
    ACCOUNT_RULES,
    BANK_TRANSFER_RULES,
    CARDLESS_ATM_PER_DAY_PAISA,
    CARDLESS_ATM_PER_MONTH_PAISA,
    DISPUTE_RULES,
    DORMANT_RULES,
    ESCROW_MIN_PAISA,
    FEES,
    FEES_NOTE,
    FRAUD_WRITTEN_REPORT_HOURS,
    KYC_RULES,
    KYC_VERIFY_HOURS,
    LIMITS,
    MIN_PAYMENT_PAISA,
    NO_LIMIT_PAYMENTS,
    OVERNIGHT_BALANCE_CAP_PAISA,
    OVERNIGHT_CAP_RULE,
    REFUND_HOURS,
    REFUND_RULES,
    SECURITY_RULES,
    SUPPORT_EMAIL,
    SUPPORT_LANDLINE,
    SUPPORT_TOLL_FREE,
    SUPPORT_WHATSAPP_VIBER,
)

_BILL_FEES = {line.split(":")[0]: line for line in FEES["bills"]}


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
        " ".join(DORMANT_RULES),
        "inactive dormant unused old wallet reactivate reopen closed locked 18 months",
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
        "Khalti by IME, run by IME Khalti Limited, from 17 July 2025 (2082/04/01). IME Pay is no "
        "longer a separate app: its wallet services moved into the Khalti app, and the IME Pay "
        "app closed on Kartik 30, 2082; accounts that hadn't moved to Khalti stopped working. "
        "IME Pay users moved to the Khalti app with a guided migration that keeps their data: "
        "their balance, interest and reward points (Daami Points now combine both apps' "
        "rewards), and linked banks and cards carry over automatically. KYC from either app is "
        "accepted, so there is no need to do it again. IME remittance can be received directly "
        "in the Khalti app.",
        "ime pay imepay merger merge closed moved migrate old account daami points separate app "
        "still work ime khalti limited remittance bank link relink kyc",
    ),
    (
        "Who founded Khalti?",
        "Four co-founders: Amit Agrawal (from Birgunj; then studying at White House College), "
        "and Arbin Sah (Bara; also spelled Arvind Sah), Dhruva Adhikari (Pokhara) and Manish "
        "Modi (Janakpur), then third-year students at Pulchowk Engineering Campus. Three of them "
        "had started Janaki Technology, the parent company, in 2007 and Sparrow SMS in 2010. The "
        "app was finished in 15 days, in two rented rooms in Pulchowk, for the CAN fair, and "
        "Khalti launched formally on 26 January 2017. Amit Agrawal was CEO of Sparrow Pay, which "
        "ran Khalti from Bakhundole, Lalitpur. In 2021 Binay Khadka became CEO and the co-founders "
        "stayed on the board. WorldLink and Triveni Group invested later, and in July 2025 IME "
        "Pay and Khalti merged as Khalti by IME.",
        "founder founders co-founder founded history started launch who made sparrow arvind "
        "arbin amit dhruva manish janaki",
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
        f"Support: {SUPPORT_EMAIL}, landline {SUPPORT_LANDLINE}, toll-free (NTC) "
        f"{SUPPORT_TOLL_FREE}, WhatsApp/Viber {SUPPORT_WHATSAPP_VIBER}. Grievance officer: "
        "Anil Tharu, +977 9801856460, "
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
        "khalti.com: 10 million+ users, 200,000+ merchants, 10 million+ transactions a month, "
        "50+ bank and financial institution partners and 100,000+ POS and agent locations. "
        "Other reports: 12.7 million registered users (about 5 million verified). Its main "
        "competitor is eSewa, estimated at about 80% of the market.",
        "users how many size big transactions partners banks esewa market merchants",
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
        "Khalti is licensed by Nepal Rastra Bank and certified for ISO 27001:2013, PCI DSS "
        f"and AMTIVO. {SECURITY_RULES[0]} {SECURITY_RULES[2]}",
        "safe secure security certified iso pci trust trustworthy",
    ),
    (
        "What are Khalti's terms for my account?",
        " ".join(ACCOUNT_RULES) + " " + KYC_RULES[1],
        "terms conditions legal law court rights block close hold account",
    ),
    (
        "What are Khalti Membership and Khalti Pro?",
        "Paid loyalty plans, since February 2023. " + FEES["membership"][0],
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

# From khalti.com's public pages (data the user gave, 25 Nov 2026). Fees and rule figures come
# from app/rules.py; the rest is as the site states it.
SITE_ARTICLES: list[tuple[str, str, str]] = [
    (
        "Where is Khalti's office and when is it open?",
        "IME Khalti Ltd., Panipokhari, Kathmandu (Bagmati Province). Open Sunday to Friday, "
        "9 am to 6 pm; closed on Saturdays and public holidays.",
        "office address location head office where visit hours open time saturday",
    ),
    (
        "What does Khalti aim to do?",
        "Its mission: seamless, secure and smart financial services for every Nepali, built on "
        "innovation, inclusivity and people's trust. It promises a personal, accessible app; "
        "money that moves freely across services; remittance from abroad; and one app for all "
        "financial services. Its six areas: easy payments (bills, QR, settlements), moving "
        "money (banks, remittance, wallets), travel and hotels, entertainment and lifestyle "
        "(movies, events, OTT), financial services (savings, insurance, investments) and tools "
        "for merchants. Milestones: 2017 Khalti launched and IME Pay got its first wallet "
        "licence; 2018 remittance straight into IME Pay and the Smart Chhori programme; 2025 "
        "IME Pay and Khalti united.",
        "mission vision aim goal values history milestones promise pillars",
    ),
    (
        "Which Khalti team do I contact for flights, events, bluebook or disputes?",
        "Flight tickets: 9801856364, traveldesk@khalti.com (7 am to 8 pm). Bluebook renewal: "
        "01-5970053, message 9801890083. Events: 9801462817, events@khalti.com. Disputes: "
        "dispute@khalti.com. Grievance officer (24/7): Anil Tharu, +977 9801856460, "
        "grievance@khalti.com; if unresolved, gunaso.nrb.org.np. Anything else: "
        f"{SUPPORT_LANDLINE}, toll-free {SUPPORT_TOLL_FREE}, WhatsApp/Viber "
        f"{SUPPORT_WHATSAPP_VIBER}, {SUPPORT_EMAIL}.",
        "department team contact flight travel desk event bluebook dispute grievance number email",
    ),
    (
        "How do businesses, schools, banks and agents contact Khalti?",
        "Payment gateway sales: 9801165557, 9801301163, 9801856394, merchant@khalti.com. "
        "Merchant integration help: 9801890085, 9801165565, 9843007232, merchantcare@khalti.com; "
        "merchant operations: 9801856315. Bazaar: 9801165557, 9801856369 (tech 9801856383), "
        "bazaar@khalti.com. Schools: 9801856422, 9801856383, 9801856475, education@khalti.com. "
        "Banks and financial institutions: 9801129427, bfi@khalti.com. Pasal and agents: "
        "01-4217601, Viber 9801492103, pasal@khalti.com, pasalsupport@khalti.com.",
        "merchant business school bank partnership agent pasal sales integration contact "
        "number email bazaar",
    ),
    (
        "Where can I download Khalti or follow it online?",
        "Android: Google Play (com.khalti). iPhone: the App Store (Khalti Digital Wallet "
        "Nepal). You can log in on the web at web.khalti.com, but you can sign up only in the "
        "app. Khalti is on Facebook (khalti.official), Instagram and X (khaltiofficial), "
        "LinkedIn, YouTube and Messenger (m.me/khalti.official). Website: khalti.com; blog: "
        "blog.khalti.com.",
        "download app android iphone ios play store web login facebook instagram social "
        "follow website",
    ),
    (
        "Which internet, TV and landline bills can I pay?",
        "Internet: WorldLink, Vianet, WiFi Nepal, TechMinds, NTC ADSL, Dish Home FTTH, "
        "WebSurfer, Subisu, Net Max, Pokhara Internet, Prabhu Net and NT FTTH. TV: SimTV, "
        "MeroTV, DishHome, ClearTV and NetTV, with your CAS, chip or account number; "
        + _BILL_FEES["TV (DTH)"]
        + " Landline: NTC, with your 8-digit landline number (up to 2% cashback).",
        "internet wifi tv dth dish home landline bill provider worldlink vianet subisu nettv which",
    ),
    (
        "Can I pay insurance premiums with Khalti?",
        "Yes: Neco Insurance, Nepal Life, Surya Jyoti, Citizen Life, Sanima Reliance Life, IME "
        "Life, Reliable Life, National Life, MetLife, LIC, Asian Life, Union Life, Himalayan "
        "Life, Prabhu Life, Rastriya Beema Sansthan and Sunlife. Promo code INSURE100 gives "
        "Rs. 100 cashback on your first payment. Insurance premiums have no transaction limit.",
        "insurance premium policy life pay insurer beema बीमा",
    ),
    (
        "What is Khalti Suraksha?",
        "Medical and accident insurance bought in the app: Rs. 350 a year for cover of "
        "Rs. 2,30,000, plus health-care benefits Khalti puts at more than Rs. 1,50,000. You can "
        "buy it for yourself or for someone else (their phone number, full name and father's "
        "name).",
        "suraksha insurance medical accident health cover",
    ),
    (
        "How do I buy movie or event tickets?",
        "Movies: choose the movie, date, showtime and seats, then pay; the e-ticket is in My "
        "Bookings. Cinemas include QFX, BigMovies, INI Cinema, Ranjana, Fcube, One Cinemas, "
        "Cineplex, BSR Movies, Bishwojyoti, Kirtipur Cineplex, City Cinema, Midtown Galleria, "
        "KSR, City Max, Friends Cinemas, Dwarika, View Cinemas, QS Cinema, Pathivara and CK. "
        "Events: concerts, sports and other events, under Events.",
        "movie film cinema ticket qfx event concert sports booking show",
    ),
    (
        "How do I book a domestic flight?",
        "1. Choose the date and route and search.\n2. Filter by time, price or airline "
        "(Buddha Air, Yeti Airlines, Saurya Airlines, Shree Airlines, Simrik Air).\n3. Enter "
        "the passenger details and pay.\nThe e-ticket comes in My Bookings and by SMS. Promo "
        "code FLYWITHKHALTI: Rs. 250 off your first flight, with cashback up to Rs. 600. Fare "
        "rules: khalti.com/info/flight-fare-rules-and-regulations.",
        "flight plane air ticket domestic buddha yeti book airline hawaijahaj",
    ),
    (
        "Can I pay for rides with Khalti?",
        "Yes, with Tootle, Pathao, SuperApp, Ride Me and Lozoom, with cashback on each ride.",
        "ride taxi bike pathao tootle indrive transport sharing",
    ),
    (
        "How do I renew my bluebook with Khalti?",
        "In the Kathmandu Valley only (Kathmandu, Lalitpur, Bhaktapur): the renewal, third-party "
        "vehicle insurance and pick-up and drop-off of your bluebook. "
        + _BILL_FEES["Bluebook renewal"]
        + " Help: 01-5970053.",
        "bluebook vehicle renewal tax bike car insurance yatayat",
    ),
    (
        "How do I pay school fees?",
        "Choose the school, enter the student's details and the amount, and pay; you get an SMS "
        "when the fee reaches the school. "
        + _BILL_FEES["School fee"]
        + " School fees have no transaction limit. Schools can join for free: they are "
        "listed in the app and receive fees in their bank in real time (registration, PAN/VAT "
        "and tax clearance certificates and a logo; education@khalti.com).",
        "school fee college tuition student pay education",
    ),
    (
        "What is the Khalti Ma Bridge Course?",
        "A bridge course for students who passed the SEE, with Cambridge Education and Smart "
        "Academy, with scholarships of up to 100% for selected students.",
        "bridge course see student scholarship class 11",
    ),
    (
        "Which banks can I load money from?",
        "Banks: ADBL, Citizens, Everest, Global IME, Jyoti Bikash, Kamana Sewa, Machhapuchhre, "
        "Muktinath, NIC Asia, Nepal Bank, Prabhu, Prime Commercial, Shangrila, Shine Resunga, "
        "Siddhartha, Nepal Investment Mega, Rastriya Banijya, Nabil, NMB, Mahalaxmi, Laxmi "
        "Sunrise, Kumari, Nepal SBI, Himalayan, Standard Chartered, Sanima, Civil, Lumbini, "
        "Saptakoshi, Miteri, Green, Garima, Excel, Sindhu and ICFC. Finance companies: Nepal "
        "Finance, Best, Central, Manjushree, Multipurpose, Pokhara, Goodwill, Gurkhas, "
        "Progressive, United and Reliance.",
        "bank banks partner which list load finance company supported",
    ),
    (
        "How do I send money to a bank account?",
        " ".join(BANK_TRANSFER_RULES)
        + f" Limit: {_limit('wallet_to_bank')}. Fees: {FEES['sending'][1]} {FEES['sending'][2]}",
        "bank transfer withdraw send to bank account wallet to bank reverse",
    ),
    (
        "How do I raise a dispute?",
        " ".join(DISPUTE_RULES),
        "dispute wrong transaction complaint claim fraud police written letter dispute email",
    ),
    (
        "What are Khalti's fees?",
        "Some of them: "
        + " ".join(FEES["sending"][:2])
        + " "
        + FEES["loading"][0]
        + " "
        + _BILL_FEES["NEA electricity and KUKL water"]
        + f" {FEES_NOTE} O-Kay can give the fee for any service.",
        "fee fees charge charges cost price service charge shulka शुल्क",
    ),
    (
        "How does Khalti's payment gateway work?",
        "Customers pay with the Khalti wallet, internet or mobile banking, connectIPS or SCT "
        "cards. Pricing is by contract: a one-time API charge and a fee per transaction, with "
        "no yearly maintenance fee. Money lands in the merchant's wallet and can be withdrawn "
        "to one bank account at any time for free; refunds go back to the customer's Khalti "
        "at once. Test keys work without a contract up to Rs. 999 (minimum Rs. 10). "
        "Integration takes 2 hours to 1 day, with SDKs for the web, Android, iOS and Flutter "
        "and plugins for WooCommerce and WHMCS. Needed: company registration, PAN/VAT and tax "
        "clearance certificates and a logo. Sign up at admin.khalti.com.",
        "payment gateway merchant website accept online checkout integrate business ecommerce",
    ),
    (
        "What are Khalti Bazaar, Daami QR and enterprise payments?",
        "Bazaar: a hosted store to sell digital services, products, gift vouchers, courses, "
        "bookings, forms and monthly subscriptions; you pay per sale with no ongoing fee, after "
        "business KYC with PAN or VAT (sign up, training and contract, list items, sell). QR "
        "payments: accept instant QR payments, and Daami QR adds loyalty rewards. Enterprise: "
        "complete payment solutions for large organisations.",
        "bazaar sell online store qr daami merchant enterprise corporate shop",
    ),
    (
        "How do I become a Khalti Pasal or agent?",
        "Shops can join Khalti's agent network as a Khalti Pasal (khalti.com/pasal and "
        "khalti.com/agent) and earn up to 4.5% cashback. Contact: 01-4217601, Viber "
        "9801492103, pasal@khalti.com.",
        "pasal agent shop representative join earn cashback retailer",
    ),
    (
        "How do developers integrate Khalti?",
        "Docs: docs.khalti.com (billing API: serviceapi.docs.khalti.com; code: github.com/khalti). "
        "ePayment: test at dev.khalti.com/api/v2, live at khalti.com/api/v2, with the header "
        '"Authorization: Key <secret key>". POST /epayment/initiate/ (return_url, website_url, '
        "amount, purchase_order_id, purchase_order_name) returns pidx and payment_url; POST "
        "/epayment/lookup/ with pidx gives the status. Amounts are in paisa, at least 1000. "
        "Treat only Completed as success and always confirm with lookup after the callback. "
        "Payment links expire after 60 minutes.",
        "developer api integrate epayment docs sdk sandbox code lookup initiate pidx",
    ),
    (
        "What is Smart Chhori?",
        "A course in the Khalti app on money and digital skills for young women aged 15 to 35: "
        "video lessons, quizzes in Nepali or English, badges and cash rewards for each level, "
        "and a certificate. Its goal is 10,000 households; it is backed by Spring Accelerator, "
        "DFID, USAID, DFAT and the Nike Foundation.",
        "smart chhori women girls course literacy training",
    ),
    (
        "Where are Khalti's privacy policy and terms?",
        "Privacy: khalti.com/info/privacy-policy. Terms: khalti.com/info/terms. Information "
        "security: khalti.com/it-policy. Dispute policy: khalti.com/info/disputepolicy. Help "
        "and FAQ: khalti.com/info/support.",
        "privacy policy terms conditions legal document link infosec",
    ),
]

FAQ_ARTICLES: list[tuple[str, str, str]] = [
    (
        "How do I load money into my Khalti wallet?",
        "Open Load Money and choose how: e-banking or mobile banking (instant; your bank's "
        "e-banking or mobile banking must be on), your linked bank (Bank-link), connectIPS "
        "(after a one-time form signed at your bank branch), a Visa, Mastercard, Amex or SCT "
        "card that is enabled for online payments, a deposit voucher at a bank counter (no "
        "bank account needed: Nepal Investment Bank, NIC Asia Bank, ICFC Finance, Lumbini "
        "Bikas Bank, Shangrila Development Bank), or money sent from another Khalti wallet. "
        f"Card loading fees: {FEES['loading'][0]} {FEES['loading'][1]}",
        "load fund add money bank wallet connectips ebanking card counter deposit voucher "
        "लोड पैसा हाल्ने बैंक halne",
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
        "check the due amount and pay. You can save the account to pay faster next month. One "
        "payment can be up to Rs. 5,00,000. "
        + _BILL_FEES["NEA electricity and KUKL water"]
        + " "
        + _BILL_FEES["Community electricity"],
        "electricity nea bill bijuli बिजुली बिल",
    ),
    (
        "How do I pay my Khanepani bill?",
        "Open Khanepani, choose your water office (Nepal Khanepani Sansthan / KUKL or a "
        "local community office), enter your customer ID, check the bill and pay. "
        + _BILL_FEES["NEA electricity and KUKL water"]
        + " "
        + _BILL_FEES["Community water"],
        "khanepani water kukl bill pani खानेपानी पानी",
    ),
    (
        "How do I buy a data pack or mobile topup?",
        "Open Topup & Data, enter the mobile number (NTC, Ncell or Smart Cell), pick a topup "
        "amount or a data pack and confirm. Packs are added to the number within a few "
        "moments. Top-ups give instant cashback, and Khalti Members get 2% back on their own "
        "number.",
        "topup recharge data pack ntc ncell smart cell mobile balance",
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
        "1. Log in to the Khalti app.\n2. Open Profile and tap Edit.\n3. Fill in the form: "
        "your father's, mother's, grandfather's and spouse's names; date of birth, gender and "
        "occupation; address (zone, district, municipality, ward); your ID's number and where "
        "and when it was issued.\n4. Add a photo of your face and of your ID's front and "
        f"back, and submit.\nKhalti checks it within {KYC_VERIFY_HOURS} hours (1 to 2 days). "
        + KYC_RULES[0],
        "kyc verify identity document citizenship how complete form",
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
    *SITE_ARTICLES,
]
