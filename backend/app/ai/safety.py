"""Text safety before anything reaches the LLM provider.

- mask_pii():        phone numbers, account numbers, reference ids, e-mails -> placeholders
- redact_secrets():  an MPIN / OTP / password typed into the chat -> removed, user warned
- untrusted():       merchant names and transfer notes are data, never instructions
- detect_language(): English, Nepali (Devanagari) or Romanized Nepali
"""

from __future__ import annotations

import re
from enum import StrEnum

_DIGIT = "[0-9०-९]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Nepali mobiles: 98/97/96 + 8 digits, optional +977 prefix.
_PHONE = re.compile(rf"(?<!{_DIGIT})(?:\+?977[\s-]?)?9[678]\d{{8}}(?!{_DIGIT})")
# Khalti-style references: 8+ upper-case letters/digits containing both.
_REFERENCE = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,}\b")
# Account / card numbers: 8+ digits, possibly spaced in groups. (Dates use '-' so are kept.)
_LONG_NUMBER = re.compile(r"(?<![\w.,])\d(?:\s?\d){7,}(?![\w.,])")


def mask_pii(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    text = _REFERENCE.sub("[ref]", text)
    return _LONG_NUMBER.sub("[number]", text)


_SENSITIVE_TERMS = (  # words that announce an MPIN, OTP or password
    r"(?:m\s*-?\s*pin|pin(?:\s*code)?|otp|one[\s-]*time[\s-]*(?:password|code)|"
    r"pass\s*word|passcode|password|pwd|एमपिन|पिन|ओटिपी|ओटीपी|पासवर्ड)"
)
# "my mpin is 1234", "OTP: 482913", "पिन ४५६७"
_SECRET_NUMBER = re.compile(
    rf"(\b|^){_SENSITIVE_TERMS}\b[^\n]{{0,25}}?({_DIGIT}(?:[\s-]?{_DIGIT}){{3,7}})(?!{_DIGIT})",
    re.IGNORECASE,
)
# "password is hunter2", "password: S3cret!"
_SECRET_WORDY = re.compile(
    r"\b(pass\s*word|password|passcode|pwd)\b\s*(?:is|=|:|-)\s*(\S{4,})", re.IGNORECASE
)


def redact_secrets(text: str) -> tuple[str, bool]:
    """Remove anything that looks like an MPIN, OTP or password. Returns (text, found)."""
    found = False

    def _number(m: re.Match[str]) -> str:
        nonlocal found
        found = True
        start, end = m.span(2)
        whole = m.group(0)
        offset = m.start(0)
        return whole[: start - offset] + "[redacted]" + whole[end - offset :]

    text = _SECRET_NUMBER.sub(_number, text)

    def _wordy(m: re.Match[str]) -> str:
        nonlocal found
        if m.group(2) == "[redacted]":
            return m.group(0)
        found = True
        return m.group(0).replace(m.group(2), "[redacted]")

    text = _SECRET_WORDY.sub(_wordy, text)
    return text, found


def untrusted(text: str | None, max_len: int = 80) -> str | None:
    """Merchant names and remarks come from other people. Mask PII, strip anything that could
    look like markup/delimiters, flatten whitespace and cap the length."""
    if text is None:
        return None
    clean = mask_pii(text).replace("<", "‹").replace(">", "›")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean if len(clean) <= max_len else clean[: max_len - 1] + "…"


class Lang(StrEnum):
    EN = "en"
    NE = "ne"  # Nepali in Devanagari
    ROM = "rom"  # Romanized Nepali ("yo mahina khana ma kati kharcha bhayo?")


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_ROMAN_STRONG = {
    "kati",
    "kharcha",
    "kharch",
    "mahina",
    "mahinama",
    "bhayo",
    "bhaeko",
    "garnu",
    "garna",
    "garera",
    "garnus",
    "chha",
    "cha",
    "xa",
    "chhu",
    "mero",
    "maile",
    "kasari",
    "kina",
    "kun",
    "kaha",
    "hijo",
    "aaja",
    "bholi",
    "hapta",
    "bachat",
    "bijuli",
    "khana",
    "khaja",
    "dekhau",
    "dekhaunu",
    "dinus",
    "sakchu",
    "parcha",
    "parchha",
    "huncha",
    "hunchha",
    "rakh",
    "rakha",
    "tirnu",
    "tirne",
    "baki",
    "baaki",
    "katti",
    "pathaunu",
    "kharchha",
    "lagyo",
    "gayo",
    "aayo",
    # Found missing by the eval ("Bikash lai 500 pathaidinus", "... bhaneko ke ho?").
    "lai",
    "bhaneko",
    "pathaidinus",
    "pathaideu",
    "pathau",
    "pathaunus",
    "garidinus",
    "garideu",
    "banaidinus",
    "banaideu",
    "rakhdinus",
    "rakhideu",
    "tiridinus",
    "tirideu",
    "kasto",
    "kahile",
    "kaile",
    "tapai",
    "tapain",
    "tapaiko",
    "hamro",
    "ahile",
    "aile",
    "pachi",
    "dherai",
    "sabai",
    "bhanda",
    "samma",
    "jamma",
    "kura",
    "chahiyo",
    "chaiyo",
    "thiyo",
    "thiye",
    "gareko",
    "pugyo",
    "kinna",
    "kinne",
}
_ROMAN_WEAK = {
    "ma", "ko", "ho", "ni", "ta", "haru", "yo", "tyo", "ra", "pani", "paisa", "ke", "ani",
}  # fmt: skip


def detect_language(text: str) -> Lang:
    if _DEVANAGARI.search(text):
        return Lang.NE
    words = re.findall(r"[a-z]+", text.lower())
    strong = sum(w in _ROMAN_STRONG for w in words)
    weak = sum(w in _ROMAN_WEAK for w in words)
    if strong >= 1 and (strong + weak >= 2 or len(words) <= 3):
        return Lang.ROM
    return Lang.EN


# Fixed texts the backend says itself (never generated by the LLM).
MESSAGES: dict[str, dict[Lang, str]] = {
    "busy": {
        Lang.EN: "O-Kay is busy, please try again in a minute.",
        Lang.NE: "O-Kay अहिले व्यस्त छ, कृपया एक मिनेटपछि फेरि प्रयास गर्नुहोस्।",
        Lang.ROM: "O-Kay ahile busy chha, ek minute pachi feri try garnus.",
    },
    "secret_warning": {
        Lang.EN: (
            "Please never share your MPIN, OTP or password, not even with O-Kay. I've removed "
            "it from this chat. If you think someone else has it, change it in Settings now."
        ),
        Lang.NE: (
            "कृपया आफ्नो MPIN, OTP वा पासवर्ड कसैलाई नदिनुहोस्, O-Kay लाई पनि होइन। मैले यसलाई "
            "च्याटबाट हटाएँ। अरू कसैले थाहा पाएको लाग्छ भने अहिले नै Settings मा बदल्नुहोस्।"
        ),
        Lang.ROM: (
            "Kripaya aafno MPIN, OTP wa password kasailai nadinus, O-Kay lai pani hoina. Maile "
            "yo chat bata hatae. Aru kasaile thaha payo jasto lagchha bhane Settings ma badalnus."
        ),
    },
    "no_data": {
        Lang.EN: "I don't have that data.",
        Lang.NE: "मसँग त्यो डाटा छैन।",
        Lang.ROM: "Malai tyo data chaina.",
    },
    "unavailable": {
        Lang.EN: "O-Kay can't answer right now. Please try again a little later.",
        Lang.NE: "O-Kay अहिले जवाफ दिन सक्दैन। कृपया केही बेरपछि प्रयास गर्नुहोस्।",
        Lang.ROM: "O-Kay ahile jawaf dina sakdaina. Kripaya ali pachi try garnus.",
    },
    "not_configured": {
        Lang.EN: "O-Kay isn't connected to its AI service yet (no API key on the server).",
        Lang.NE: "O-Kay अझै AI सेवासँग जोडिएको छैन (सर्भरमा API key छैन)।",
        Lang.ROM: "O-Kay ajhai AI service sanga jodieko chaina (server ma API key chaina).",
    },
}


def message(key: str, lang: Lang) -> str:
    return MESSAGES[key][lang]
