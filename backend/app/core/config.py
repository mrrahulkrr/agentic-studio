import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.1-flash-lite")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

# Three quality tiers for generate_text() call sites, approved to replace a
# single CHAT_MODEL for every call site that goes through
# llm.py::generate_for_tier (see llm.py). CHAT_MODEL itself is untouched and
# stays generate_text()'s own fallback for any caller that doesn't specify a
# tier.
#   FAST     — routing/classification: cheap, high-volume, low individual
#              stakes (document classification, retrieval reranking).
#   STANDARD — narrative/report generation: everyday, user-facing prose.
#   QUALITY  — final judgment / citation-bearing output: called rarely, but
#              needs the best quality the free tier actually offers.
FAST_MODEL = os.getenv("FAST_MODEL", "gemini-3.5-flash-lite")
STANDARD_MODEL = os.getenv("STANDARD_MODEL", "gemini-3.5-flash")
QUALITY_MODEL = os.getenv("QUALITY_MODEL", "gemini-3.7-flash")

TIER_MODELS = {"FAST": FAST_MODEL, "STANDARD": STANDARD_MODEL, "QUALITY": QUALITY_MODEL}

TIER_LABELS = {
    "FAST": "Quick checks",
    "STANDARD": "Everyday reports",
    "QUALITY": "Final judgment",
}

# Every model a user may pick as a per-request override for a tier (the
# rate-limit fallback dialog), with the plain-language description shown
# alongside it. Anything not listed here is rejected by main.py's
# /run-agent rather than passed through to the Gemini API — see
# _validate_model_overrides(). gemini-3.1-pro-preview has no free tier via
# API key and gemini-3.1-flash-lite's free-tier status could not be
# confirmed against Google's own conflicting documentation, so neither is
# offered here. The 2.5-series entries are confirmed free today but
# reported sunsetting mid-October 2026 (exact date unconfirmed) — kept as
# short-term fallbacks only, flagged as such in their own descriptions.
TIER_CANDIDATES = {
    "FAST": [
        {
            "model": FAST_MODEL,
            "description": (
                "Fastest and cheapest — best when you're running many quick "
                "checks, like sorting an uploaded document or scoring search "
                "results."
            ),
        },
        {
            "model": "gemini-2.5-flash-lite",
            "description": (
                "An older, equally fast option — free today, but Google has "
                "flagged the whole 2.5 model family for shutdown around "
                "mid-October 2026, so treat this as a temporary fallback, "
                "not a long-term choice."
            ),
        },
    ],
    "STANDARD": [
        {
            "model": STANDARD_MODEL,
            "description": (
                "Balanced speed and quality — the right choice for everyday "
                "reports and write-ups you'll read yourself."
            ),
        },
        {
            "model": "gemini-3.6-flash",
            "description": (
                "A newer alternative, reportedly a bit more efficient at "
                "planning multi-step content than 3.5 Flash — worth trying "
                "if you want slightly sharper write-ups without moving to "
                "the slowest tier."
            ),
        },
        {
            "model": "gemini-2.5-flash",
            "description": (
                "An older mid-tier option — free today, but part of the 2.5 "
                "family Google has flagged for shutdown around mid-October "
                "2026; use only as a temporary fallback."
            ),
        },
    ],
    "QUALITY": [
        {
            "model": QUALITY_MODEL,
            "description": (
                "The most capable free option available — slower, but best "
                "for the one decision in a run you most want to trust, like "
                "the final greenlight verdict."
            ),
        },
        {
            "model": "gemini-2.5-pro",
            "description": (
                "Previously Google's top reasoning model — still free today, "
                "but scheduled for shutdown around mid-October 2026 per "
                "multiple reports; don't build a habit around it this close "
                "to its retirement."
            ),
        },
    ],
}

MAX_UPLOAD_FILE_SIZE_MB = 10

AGENT4_BASE_URL = os.getenv("AGENT4_BASE_URL", "http://localhost:8001")
SUPPORTED_COUNTRIES = [
    c.strip().upper()
    for c in os.getenv("SUPPORTED_COUNTRIES", "US,MX,GB,JP,DE").split(",")
    if c.strip()
]

CALENDAR_MODE = os.getenv("CALENDAR_MODE", "service_account")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
API_SECRET_KEY = os.getenv("API_SECRET_KEY")

# Signs the login session cookie (see app/core/auth.py). Falls back to
# API_SECRET_KEY so there isn't a second required secret to provision --
# set JWT_SECRET_KEY explicitly if the two should ever rotate independently.
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or API_SECRET_KEY