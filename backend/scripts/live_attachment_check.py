"""Live check of files in the chat against the real LLM (needs GROQ_API_KEY in backend/.env).
Draws a made-up receipt (mock data only), writes a small made-up CSV, and asks O-Kay about
each on a throwaway in-memory copy of the demo data. Prints what was read and the answers.

    python scripts/live_attachment_check.py
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.ai.attachments import Upload, read  # noqa: E402
from app.ai.chat import ChatService  # noqa: E402
from app.ai.llm import GroqLLMClient  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db, make_engine, make_session_factory  # noqa: E402
from app.periods import today_npt  # noqa: E402
from app.seed import DEMO_USER_ID, seed_database  # noqa: E402
from app.sources.mock import MockBillSource, MockTransactionSource  # noqa: E402

FONT = Path(__file__).resolve().parents[2] / "app/assets/fonts/DMSans-Regular.ttf"
RECEIPT = [
    "HIMALAYAN FRESH MART",
    "Baneshwor, Kathmandu",
    "Date: 2026-11-13   Bill no: 4471",
    "",
    "Basmati rice 5kg        1,150.00",
    "Milk 1L x2                 190.00",
    "Eggs (crate)               480.00",
    "Tea leaves 500g            325.00",
    "",
    "TOTAL              Rs. 2,145.00",
    "Paid by: Khalti wallet",
]


def receipt_jpeg() -> bytes:
    font = ImageFont.truetype(str(FONT), 28)
    img = Image.new("RGB", (640, 60 + 44 * len(RECEIPT)), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(RECEIPT):
        draw.text((30, 30 + 44 * i), line, fill="black", font=font)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


CSV = b"""Date,Description,Amount
2026-11-01,Ratna Mart groceries,1200
2026-11-03,Chiya Chautari,150.50
2026-11-05,Sawari Ride,313
2026-11-07,Refund from Daraz,-350
"""


def main() -> None:
    settings = get_settings()
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        sys.exit("No GROQ_API_KEY in backend/.env")
    engine = make_engine("sqlite://")
    init_db(engine)
    session = make_session_factory(engine)()
    seed_database(session, today_npt())
    llm = GroqLLMClient(settings)
    source = MockTransactionSource(session)

    for name, data, question in [
        ("receipt.jpg", receipt_jpeg(), "What did I buy and how much was it?"),
        ("november.csv", CSV, "How much is in this file in total?"),
    ]:
        upload = Upload(name, data)
        reading = read(upload, llm)
        print(f"\n== {name} ({reading.kind}) read as:\n{reading.content[:600]}")
        time.sleep(5)
        service = ChatService(
            session,
            llm,
            source,
            MockBillSource(source),
            DEMO_USER_ID,
            today_npt(),
            history_messages=0,
        )
        text, done = [], {}
        for ev in service.respond(question, "auto", [upload]):
            if ev.event == "token":
                text.append(ev.data["text"])
            elif ev.event == "reset":
                text = []
            elif ev.event == "done":
                done = ev.data
        print(f"-- Q: {question}\n-- A: {''.join(text).strip()}")
        chips = [s["text"] for s in done.get("suggestions", [])]
        print(f"   error: {done.get('error')}  chips: {chips}")
        print(f"   models: image {llm.last_model}")
        time.sleep(15)


if __name__ == "__main__":
    main()
