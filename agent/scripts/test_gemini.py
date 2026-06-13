"""Test Gemini LLM (brain) for off-script caller questions.

Usage:
  python scripts/test_gemini.py
  python scripts/test_gemini.py --question "Who is this? Is this a scam?"
"""

from __future__ import annotations

import argparse
import sys

from _env import optional, require

DEFAULT_KNOWLEDGE = """
who_is_this: Sarah from ABC Benefits, a licensed Medicare benefits provider.
is_this_a_scam: This is a legitimate call. It may be recorded for quality assurance.
how_much: The licensed specialist can go over exact numbers after I connect you.
not_interested: Understood. I will remove your number. Have a great day.
"""

DEFAULT_QUESTION = "Who is this? Is this a scam?"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Gemini off-script replies")
    parser.add_argument("--question", default=DEFAULT_QUESTION, help="Caller question")
    args = parser.parse_args()

    api_key = require("GOOGLE_API_KEY")
    model_name = optional("GEMINI_MODEL", "gemini-2.5-flash-lite")

    try:
        import google.generativeai as genai
    except ImportError:
        print("ERROR: google-generativeai not installed.")
        print("Run: python -m pip install google-generativeai")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    prompt = f"""You are a friendly outbound fronter on a live US phone call.
Reply in ONE short sentence (max 20 words). Sound natural, not salesy.
Only use facts from the knowledge base. If unsure, offer to connect a specialist.

KNOWLEDGE:
{DEFAULT_KNOWLEDGE.strip()}

CALLER SAID: {args.question}

YOUR REPLY:"""

    print(f"Model: {model_name}")
    print(f"Caller: {args.question}")
    print("Thinking...")

    try:
        response = model.generate_content(prompt)
        reply = (response.text or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: Gemini call failed: {exc}")
        print("Try GEMINI_MODEL=gemini-2.0-flash in .env if this model is unavailable.")
        sys.exit(1)

    if not reply:
        print("\nERROR: Empty response from Gemini.")
        sys.exit(1)

    print("\n--- GEMINI OK ---")
    print("BOT:", reply)


if __name__ == "__main__":
    main()
