"""The Groq chat model, set up in one place, plus friendly error messages.

The agents, the router and the question rewriter all use this same model.

Retries: the Groq client already retries by itself on a rate limit (429),
a timeout or a Groq server error (5xx). It waits as long as Groq's
"retry-after" header says (up to 60 s), otherwise 0.5 s, 1 s, 2 s...
We only set how many times. Errors that are still there after the
retries reach the user as a plain message from friendly_error().
"""

from __future__ import annotations

import logging
import re

import groq
from langchain_groq import ChatGroq

from app.core.config import Settings, check_groq_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 60

RATE_LIMITED = (
    "Groq's free usage limit was reached (8,000 tokens per minute). "
    "Please wait about a minute and ask again."
)
DAILY_LIMIT = (
    "Groq's free daily limit was reached (200,000 tokens per day). "
    "Please try again in {wait}."
)
TOO_LARGE = (
    "This question needed more text than Groq's free limit allows at once. "
    "Please try a shorter or more specific question."
)
NO_RESPONSE = "Groq did not respond in time. Please check your internet connection and try again."
REPHRASE = "Sorry, I could not process that question. Please rephrase it and try again."
BAD_KEY = "Groq rejected the API key. Please check GROQ_API_KEY in your .env file."
GROQ_DOWN = "Groq is having problems right now. Please try again in a few minutes."
UNKNOWN = "Sorry, something went wrong while answering. Please try again."


def load_llm(settings: Settings) -> ChatGroq:
    """Connect to Groq with the model and key from the env vars.

    Stops at startup if either one is missing.
    """
    check_groq_settings(settings)
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        # 0 = the most predictable answers; we want facts from the docs, not creativity
        temperature=0,
        max_retries=MAX_RETRIES,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


# Groq's rate limit message says which limit was hit and how long to wait, e.g.
# "... on tokens per day (TPD): Limit 200000 ... Please try again in 4m9.264s."
WAIT_TIME = re.compile(r"try again in ((?:\d+h)?(?:\d+m)?[\d.]+s)")


def wait_time(error: Exception) -> str:
    """How long Groq says to wait, rounded to whole seconds ("4m9s"), or "a while"."""
    match = WAIT_TIME.search(str(error))
    return re.sub(r"\.\d+s$", "s", match.group(1)) if match else "a while"


def is_daily_limit(error: Exception) -> bool:
    return isinstance(error, groq.RateLimitError) and "tokens per day" in str(error)


def describe_error(error: BaseException) -> str:
    """One short line for the log instead of Groq's full error text or a traceback."""
    if isinstance(error, groq.RateLimitError):
        limit = "tokens per day" if is_daily_limit(error) else "tokens per minute"
        return f"Groq rate limit ({limit}), retry in {wait_time(error)}"
    if isinstance(error, groq.APIStatusError):
        return f"Groq error {error.status_code} ({type(error).__name__})"
    return f"{type(error).__name__}: {str(error)[:120]}"


def friendly_error(error: Exception) -> str:
    """Turn a Groq error into a message for the user. A short note goes to the log."""
    logger.warning(describe_error(error))

    if is_daily_limit(error):
        return DAILY_LIMIT.format(wait=wait_time(error))
    if isinstance(error, groq.RateLimitError):
        return RATE_LIMITED
    if isinstance(error, (groq.APITimeoutError, groq.APIConnectionError)):
        return NO_RESPONSE
    if isinstance(error, groq.AuthenticationError):
        return BAD_KEY
    if isinstance(error, groq.BadRequestError):
        # Groq checks the tool call the model writes. If the model writes a
        # broken one, Groq answers 400 "tool call validation failed".
        # Asking again in other words usually works.
        return REPHRASE
    if isinstance(error, groq.APIStatusError):
        if error.status_code == 413:
            # One request alone is over the per-minute limit, so waiting won't help
            return TOO_LARGE
        if error.status_code >= 500:
            return GROQ_DOWN
    return UNKNOWN
