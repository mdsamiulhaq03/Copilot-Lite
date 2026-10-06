"""Try the router from the terminal: see which agent a question goes to.

Run from the backend/ folder:
    python -m scripts.route "The worker crashed last night"   # one question
    python -m scripts.route --samples                         # a set of example questions
    python -m scripts.route                                   # ask questions one by one

Only questions with a debug keyword cost a Groq call.
"""

from __future__ import annotations

import argparse
import logging
import sys

from langchain_core.language_models import BaseChatModel

from app.agents.router import has_debug_keyword, route
from app.core.config import ConfigError, load_settings
from app.core.llm import load_llm

# Plain questions, real problem reports, and knowledge questions that only
# mention a debug word (the Groq check should send those to the Generic Agent).
SAMPLES = [
    "What is EPIC-8?",
    "How does the BDT Engine work?",
    "What does the error handling module do?",
    "How do I login to the dashboard?",
    "My baseline job failed with a timeout, why?",
    "The worker crashed last night",
    "Check the error logs for tenant 42",
]


def show(llm: BaseChatModel, question: str) -> None:
    keyword = has_debug_keyword(question)
    how = "keyword hit, Groq checked" if keyword else "no keyword, no Groq call"
    print(f"{route(llm, question):<8} | {how:<25} | {question}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show which agent a question goes to.")
    parser.add_argument("question", nargs="?", help="leave out to ask questions one by one")
    parser.add_argument("--samples", action="store_true", help="run the example questions")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    try:
        llm = load_llm(load_settings())
    except ConfigError as error:
        print(f"ERROR {error}")
        sys.exit(1)

    if args.samples:
        for question in SAMPLES:
            show(llm, question)
        return
    if args.question:
        show(llm, args.question)
        return
    while question := input("\nQuestion (press Enter to quit): ").strip():
        show(llm, question)


if __name__ == "__main__":
    main()
