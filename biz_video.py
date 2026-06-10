# =============================================================================
#  biz_video.py — Sarathi-AI Video Studio
#  Sarathi-AI · 2026
# =============================================================================
#
#  Generates themed short marketing reels/clips for insurance & wealth advisors
#  to post on WhatsApp Status, Instagram Reels, Facebook Stories, etc.
#
#  Themes: Health, Life, Term, Vehicle, Travel, Wealth, Retirement, ULIP,
#          NPS, SIP Youth, Emergency Fund, Custom (AI-generated scenes)
#  Format: Square 720×720 (default) or Vertical 720×1280 (reels/stories)
#  Tech:   Pillow (frame rendering) + direct ffmpeg subprocess (video assembly)
#  Note:   One PNG per scene stored in tmpdir; ffmpeg concat encodes in O(n)
#          memory — safe on 1 GB RAM servers.
#  Gate:   Team / Enterprise plan only
#
# =============================================================================
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import textwrap
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("sarathi.video")

# ─── Config ────────────────────────────────────────────────────────────────
VIDEO_DIR = os.getenv("VIDEO_DIR", "/opt/sarathi/generated_videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}   # job_id → {status, url, error, filename, created_at}

# Output resolution — 720px keeps file size small and looks great on phones
_SQUARE_WH  = (720, 720)
_REELS_WH   = (720, 1280)

# ─── Font Setup — script-aware (Latin + Devanagari + emoji) ───────────────
_LATIN_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
_DEVA_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
]
_LATIN_FONT: Optional[str] = next(
    (p for p in _LATIN_CANDIDATES if os.path.exists(p)), None
)
_DEVA_FONT: Optional[str] = next(
    (p for p in _DEVA_CANDIDATES if os.path.exists(p)), None
)
# Pre-warm font cache to avoid repeated truetype() calls per scene
_FONT_CACHE: dict[tuple, ImageFont.ImageFont] = {}


def _has_devanagari(text: str) -> bool:
    """Detect any Devanagari char (U+0900–U+097F) — Hindi, Marathi, Sanskrit, etc."""
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


def _font(size: int, text: str = "") -> ImageFont.ImageFont:
    """Return font appropriate for the script in `text` (Devanagari vs Latin)."""
    s = max(size, 10)
    use_deva = _DEVA_FONT and _has_devanagari(text)
    path = _DEVA_FONT if use_deva else _LATIN_FONT
    if not path:
        return ImageFont.load_default()
    key = (path, s)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ImageFont.truetype(path, s)
        _FONT_CACHE[key] = f
    return f


# Backward-compat: existing code still calls _font(size) without text arg
_FONT_PATH = _LATIN_FONT  # legacy module-level reference


# ─── Drawing Helpers ───────────────────────────────────────────────────────
def _gradient_array(w: int, h: int, top: tuple, bot: tuple) -> np.ndarray:
    """Vertical gradient as uint8 numpy array (H×W×3)."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        t = y / max(h - 1, 1)
        arr[y] = [int(top[i] + (bot[i] - top[i]) * t) for i in range(3)]
    return arr


def _hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y: int,
    size: int,
    color: str,
    w: int,
) -> int:
    """Draw text centered on width w at y. Returns line height."""
    fnt = _font(size, text)
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = max((w - tw) // 2, 8)
    # Shadow
    draw.text((x + 2, y + 3), text, font=fnt, fill=(0, 0, 0, 100))
    draw.text((x, y), text, font=fnt, fill=color)
    return th


def _measure_lines(draw: ImageDraw.ImageDraw, lines: list[dict], scale: float) -> int:
    total = 0
    for item in lines:
        fnt = _font(int(item["s"] * scale), item["t"])
        bbox = draw.textbbox((0, 0), item["t"], font=fnt)
        total += (bbox[3] - bbox[1]) + int(item.get("g", 16) * scale)
    return total


def _make_frame(scene: dict, w: int, h: int) -> np.ndarray:
    """Render a single scene as a numpy RGB image.
    Font sizes in theme definitions are calibrated for 1080×1080;
    they are scaled proportionally to the actual width.
    """
    scale = w / 1080   # font / gap scaling factor

    arr = _gradient_array(w, h, scene["grad_top"], scene["grad_bot"])
    img = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(img)

    # Card overlay
    pad = int(w * 0.05)
    card_top = h // 7
    card_bot = h - h // 7
    draw.rounded_rectangle(
        [(pad, card_top), (w - pad, card_bot)],
        radius=int(36 * scale),
        fill=(0, 0, 0, 60),
        outline=(255, 255, 255, 25),
        width=1,
    )

    # Auto-centre the text block within the card
    lines = scene["lines"]
    total_h = _measure_lines(draw, lines, scale)
    card_h = card_bot - card_top
    y = card_top + max((card_h - total_h) // 2, 20)

    for item in lines:
        size = int(item["s"] * scale)
        gap  = int(item.get("g", 16) * scale)
        color = item.get("c", "#ffffff")
        lh = _draw_centered(draw, item["t"], y, size, color, w)
        y += lh + gap

    return np.array(img)


def _make_cta_frame(
    advisor_name: str,
    advisor_phone: str,
    accent: str,
    w: int,
    h: int,
) -> np.ndarray:
    """Render the CTA / advisor branding scene."""
    scale = w / 1080
    rgb = _hex_rgb(accent)
    top = (10, 10, 15)
    bot = (min(255, rgb[0] // 3 + 12), min(255, rgb[1] // 3 + 12),
           min(255, rgb[2] // 3 + 15))
    arr = _gradient_array(w, h, top, bot)
    img = Image.fromarray(arr, "RGB")
    draw = ImageDraw.Draw(img)

    pad = int(w * 0.05)
    card_top = int(h * 0.12)
    card_bot = int(h * 0.88)
    draw.rounded_rectangle(
        [(pad, card_top), (w - pad, card_bot)],
        radius=int(40 * scale),
        fill=(0, 0, 0, 80),
        outline=(255, 255, 255, 30),
        width=1,
    )

    lines = [
        {"t": "📞 Book a FREE Consultation", "s": int(38 * scale), "c": accent,      "g": int(h * 0.035)},
        {"t": advisor_name,                  "s": int(60 * scale), "c": "#ffffff",   "g": int(h * 0.018)},
        {"t": f"📱 {advisor_phone}",         "s": int(44 * scale), "c": "#dddddd",   "g": int(h * 0.04)},
        {"t": "─────────────────────",       "s": int(26 * scale), "c": "#444444",   "g": int(h * 0.028)},
        {"t": "Insurance & Wealth Management", "s": int(30 * scale), "c": "#aaaaaa", "g": int(h * 0.012)},
        {"t": "Powered by Sarathi-AI 🤖",    "s": int(26 * scale), "c": "#666666",   "g": 0},
    ]

    total_h = sum(row["s"] + row["g"] for row in lines)
    card_h = card_bot - card_top
    y = card_top + max((card_h - total_h) // 2, 20)

    for item in lines:
        lh = _draw_centered(draw, item["t"], y, item["s"], item["c"], w)
        y += lh + item["g"]

    return np.array(img)


# ─── Theme Library ─────────────────────────────────────────────────────────
# Font sizes are authored at 1080px wide; _make_frame() scales them down.
THEMES: dict[str, dict] = {

    "health_insurance": {
        "id":          "health_insurance",
        "name":        "Health Insurance",
        "description": "Person drowning in medical bills — the shocking cost of no cover",
        "icon":        "🏥",
        "accent":      "#e74c3c",
        "scenes": [
            {
                "grad_top": (8, 8, 25), "grad_bot": (110, 12, 12),
                "duration": 3.5,
                "lines": [
                    {"t": "🏥",              "s": 100, "g": 18},
                    {"t": "One Illness.",    "s": 68,  "c": "#ffdddd", "g": 10},
                    {"t": "Everything Gone.", "s": 76, "c": "#ff6b6b", "g": 28},
                    {"t": "Are you protected?", "s": 38, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (12, 8, 32), "grad_bot": (90, 18, 10),
                "duration": 4.0,
                "lines": [
                    {"t": "Average hospital bill",         "s": 40, "c": "#bbbbdd", "g": 8},
                    {"t": "in India (2025):",              "s": 40, "c": "#bbbbdd", "g": 32},
                    {"t": "₹2 — ₹8 Lakhs",                "s": 88, "c": "#ff6b6b", "g": 24},
                    {"t": "per serious illness",           "s": 36, "c": "#999999", "g": 42},
                    {"t": "💸  Savings wiped in days",     "s": 36, "c": "#ff9966", "g": 10},
                    {"t": "🏦  High-interest loans to pay","s": 36, "c": "#ff9966", "g": 0},
                ],
            },
            {
                "grad_top": (30, 5, 5), "grad_bot": (12, 8, 30),
                "duration": 4.0,
                "lines": [
                    {"t": "Without Health Insurance:",     "s": 46, "c": "#ffcccc", "g": 36},
                    {"t": "❌  Life savings: GONE",         "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Forced to sell assets",      "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Children's future at risk",  "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Crushing family stress",     "s": 42, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "With Health Insurance:",            "s": 46, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Zero out-of-pocket expense",    "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Cashless treatment anywhere",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Entire family protected",       "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Plans from just ₹400/month",   "s": 44, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "life_insurance": {
        "id":          "life_insurance",
        "name":        "Life Insurance",
        "description": "Family's financial future destroyed without life cover",
        "icon":        "❤️",
        "accent":      "#e91e63",
        "scenes": [
            {
                "grad_top": (8, 5, 20), "grad_bot": (100, 10, 40),
                "duration": 4.0,
                "lines": [
                    {"t": "❤️",                           "s": 100, "g": 18},
                    {"t": "If you're gone tomorrow,",     "s": 52,  "c": "#ffccdd", "g": 10},
                    {"t": "will your family be OK?",      "s": 60,  "c": "#ff6b9d", "g": 24},
                    {"t": "Most families are NOT prepared.", "s": 34, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (15, 5, 25), "grad_bot": (80, 15, 35),
                "duration": 4.0,
                "lines": [
                    {"t": "The brutal reality:",          "s": 48, "c": "#ffccdd", "g": 30},
                    {"t": "68% of Indians",               "s": 84, "c": "#ff6b9d", "g": 12},
                    {"t": "have NO life insurance",        "s": 44, "c": "#ffaacc", "g": 36},
                    {"t": "👨‍👩‍👧  Family EMIs stop — who pays?",  "s": 34, "c": "#ff9999", "g": 10},
                    {"t": "🏫  Children's school fees?  Gone.", "s": 34, "c": "#ff9999", "g": 0},
                ],
            },
            {
                "grad_top": (25, 5, 5), "grad_bot": (10, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without Life Insurance:",          "s": 46, "c": "#ffcccc", "g": 36},
                    {"t": "❌  Spouse struggles alone",        "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Children's dreams shattered",   "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Home loan becomes a burden",    "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  No financial safety net",       "s": 42, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 25, 10), "grad_bot": (8, 65, 20),
                "duration": 4.0,
                "lines": [
                    {"t": "With Life Insurance:",                   "s": 46, "c": "#ccffdd", "g": 36},
                    {"t": "✅  ₹1 Crore @ ₹990/month (age 30)",    "s": 38, "c": "#55ff88", "g": 12},
                    {"t": "✅  Family income replaced",             "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  All loans & EMIs covered",           "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Children's future secured",          "s": 40, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "vehicle_insurance": {
        "id":          "vehicle_insurance",
        "name":        "Vehicle Insurance",
        "description": "Accidents, fines, legal trouble — the real cost of driving uninsured",
        "icon":        "🚗",
        "accent":      "#f39c12",
        "scenes": [
            {
                "grad_top": (12, 10, 5), "grad_bot": (100, 60, 5),
                "duration": 3.5,
                "lines": [
                    {"t": "🚗💥",                        "s": 100, "g": 18},
                    {"t": "One accident.",               "s": 68,  "c": "#ffe0aa", "g": 10},
                    {"t": "₹5 Lakh repair bill.",        "s": 76,  "c": "#f39c12", "g": 24},
                    {"t": "No insurance = YOUR problem.", "s": 36, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (15, 12, 5), "grad_bot": (85, 50, 8),
                "duration": 4.0,
                "lines": [
                    {"t": "India: 1 road accident",          "s": 44, "c": "#ffe0aa", "g": 8},
                    {"t": "every 3 minutes",                 "s": 72, "c": "#f39c12", "g": 32},
                    {"t": "Average repair cost",             "s": 38, "c": "#ffcc88", "g": 8},
                    {"t": "₹80,000 — ₹5 Lakhs",             "s": 56, "c": "#ffaa55", "g": 28},
                    {"t": "⚖️  Third-party penalty: ₹2,000+","s": 34, "c": "#ff9944", "g": 0},
                ],
            },
            {
                "grad_top": (28, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without Vehicle Insurance:",       "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Pay full repair out of pocket", "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  Third-party legal liability",   "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  ₹5,000 fine + licence seized",  "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  Zero protection for you",       "s": 40, "c": "#ff6622", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "With Vehicle Insurance:",          "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Full repair cost covered",      "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Third-party liability sorted",  "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Roadside assistance 24/7",      "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  From just ₹2,500/year",         "s": 44, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "wealth_management": {
        "id":          "wealth_management",
        "name":        "Wealth Management (SIP/MF)",
        "description": "Shocking gap between savings account and SIP over 20 years",
        "icon":        "📈",
        "accent":      "#27ae60",
        "scenes": [
            {
                "grad_top": (5, 20, 8), "grad_bot": (8, 80, 25),
                "duration": 3.5,
                "lines": [
                    {"t": "📈",                            "s": 100, "g": 18},
                    {"t": "Saving money all your life?",  "s": 52,  "c": "#ccffdd", "g": 12},
                    {"t": "But in the WRONG place?",      "s": 60,  "c": "#27ae60", "g": 24},
                    {"t": "You could be losing crores.",  "s": 36,  "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (8, 22, 10), "grad_bot": (12, 70, 20),
                "duration": 4.5,
                "lines": [
                    {"t": "₹10,000/month × 20 years",   "s": 44, "c": "#ccffdd", "g": 30},
                    {"t": "🏦  Savings account (3%):",   "s": 38, "c": "#ffaa55", "g": 8},
                    {"t": "₹32 Lakhs",                   "s": 66, "c": "#ff8833", "g": 28},
                    {"t": "📈  SIP in Nifty 50 (13%):",  "s": 38, "c": "#88ff99", "g": 8},
                    {"t": "₹1.05 Crores",                "s": 72, "c": "#27ae60", "g": 0},
                ],
            },
            {
                "grad_top": (25, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "The cost of NOT investing:",       "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Inflation erodes 6-7% yearly", "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  FDs barely beat inflation",    "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  Retirement savings fall short","s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  Missing compounding magic",    "s": 40, "c": "#ff6622", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "Smart investing with SIP / MF:",    "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  12-15% avg returns (Nifty 50)", "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Start with just ₹500/month",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Tax-saving ELSS options",       "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Wealth that beats inflation",   "s": 40, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "travel_insurance": {
        "id":          "travel_insurance",
        "name":        "Travel Insurance",
        "description": "Medical emergency abroad without travel insurance = financial catastrophe",
        "icon":        "✈️",
        "accent":      "#3498db",
        "scenes": [
            {
                "grad_top": (5, 10, 35), "grad_bot": (8, 30, 100),
                "duration": 3.5,
                "lines": [
                    {"t": "✈️",                              "s": 100, "g": 18},
                    {"t": "Medical emergency abroad",        "s": 52,  "c": "#cceeff", "g": 10},
                    {"t": "without travel insurance?",       "s": 56,  "c": "#3498db", "g": 24},
                    {"t": "Dream trip → financial nightmare.", "s": 32, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (8, 12, 38), "grad_bot": (10, 28, 90),
                "duration": 4.0,
                "lines": [
                    {"t": "Hospital in USA / Europe:",  "s": 44, "c": "#cceeff", "g": 28},
                    {"t": "$50,000 — $2,00,000",        "s": 72, "c": "#ff6b6b", "g": 18},
                    {"t": "for 1 week of treatment",    "s": 38, "c": "#99aadd", "g": 38},
                    {"t": "🚁  Emergency evacuation: ₹20L+", "s": 34, "c": "#ff9966", "g": 10},
                    {"t": "✈️  Flight cancel loss: ₹80K+",   "s": 34, "c": "#ff9966", "g": 0},
                ],
            },
            {
                "grad_top": (28, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without Travel Insurance:",       "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Pay hospital bills yourself",  "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  Lost luggage — no refund",    "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  Trip cancel = full loss",     "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  Stranded abroad, no help",    "s": 40, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "With Travel Insurance:",              "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Worldwide medical bills covered",  "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Emergency evacuation included",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Lost baggage compensation",       "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  For just ₹400 per trip!",         "s": 44, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "term_insurance": {
        "id":          "term_insurance",
        "name":        "Term Insurance",
        "description": "₹1 Crore cover for less than your daily chai — why everyone needs it",
        "icon":        "🛡️",
        "accent":      "#9b59b6",
        "scenes": [
            {
                "grad_top": (12, 5, 28), "grad_bot": (55, 10, 100),
                "duration": 3.5,
                "lines": [
                    {"t": "🛡️",                      "s": 100, "g": 18},
                    {"t": "₹1 Crore life cover.",    "s": 64,  "c": "#e0ccff", "g": 10},
                    {"t": "For ₹33 per day.",         "s": 76,  "c": "#9b59b6", "g": 24},
                    {"t": "Less than your morning chai. ☕", "s": 34, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (15, 8, 32), "grad_bot": (55, 12, 90),
                "duration": 4.0,
                "lines": [
                    {"t": "If you earn ₹50,000/month,", "s": 40, "c": "#ccbbff", "g": 12},
                    {"t": "your family needs",           "s": 44, "c": "#ccbbff", "g": 10},
                    {"t": "₹60L — ₹1.5 Crore",          "s": 74, "c": "#cc88ff", "g": 14},
                    {"t": "to survive without you",      "s": 40, "c": "#9999bb", "g": 10},
                    {"t": "for 10 years.",               "s": 44, "c": "#9999bb", "g": 0},
                ],
            },
            {
                "grad_top": (28, 5, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without Term Insurance:",          "s": 44, "c": "#ffcccc", "g": 36},
                    {"t": "❌  Family income vanishes",        "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Home loan can't be paid",       "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Children drop out of school",   "s": 42, "c": "#ff4444", "g": 12},
                    {"t": "❌  Spouse's future destroyed",     "s": 42, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "With Term Insurance:",                    "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  ₹1Cr cover @ ₹990/month (age 30)",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  100% payout guaranteed",              "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  No medical tests under 45",           "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Buy younger = pay far less",          "s": 40, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "retirement_planning": {
        "id":          "retirement_planning",
        "name":        "Retirement Planning",
        "description": "Start at 30 vs 40 — the shocking difference in retirement corpus",
        "icon":        "🌅",
        "accent":      "#f59e0b",
        "scenes": [
            {
                "grad_top": (15, 12, 5), "grad_bot": (90, 55, 8),
                "duration": 3.5,
                "lines": [
                    {"t": "🌅",                              "s": 100, "g": 18},
                    {"t": "Retire with dignity.",            "s": 60,  "c": "#fff3cc", "g": 10},
                    {"t": "Or struggle at 60?",              "s": 68,  "c": "#f59e0b", "g": 24},
                    {"t": "The choice is made TODAY.",       "s": 36,  "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (18, 14, 5), "grad_bot": (80, 48, 6),
                "duration": 4.5,
                "lines": [
                    {"t": "₹10,000/month SIP",             "s": 48, "c": "#fff3cc", "g": 20},
                    {"t": "Start at 30 → retire at 60:",   "s": 38, "c": "#fde68a", "g": 8},
                    {"t": "₹3.5 Crores",                   "s": 82, "c": "#f59e0b", "g": 28},
                    {"t": "Start at 40 → retire at 60:",   "s": 38, "c": "#fbbf24", "g": 8},
                    {"t": "₹75 Lakhs",                     "s": 66, "c": "#ff8800", "g": 0},
                ],
            },
            {
                "grad_top": (28, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without a retirement plan:",      "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Dependent on children",        "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  Medical costs wipe savings",   "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  No passive income at 60",      "s": 40, "c": "#ff4444", "g": 12},
                    {"t": "❌  Forced to work past 65",       "s": 40, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "With smart retirement planning:",      "s": 42, "c": "#ccffdd", "g": 36},
                    {"t": "✅  ₹50,000+/month passive income",    "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Medical emergencies covered",      "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Full financial independence",      "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Start with just ₹2,000/month",    "s": 40, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "ulip_vs_mf": {
        "id":          "ulip_vs_mf",
        "name":        "ULIP vs Mutual Fund",
        "description": "Know the real difference before you invest — which one wins for you",
        "icon":        "⚖️",
        "accent":      "#06b6d4",
        "scenes": [
            {
                "grad_top": (5, 18, 28), "grad_bot": (8, 55, 90),
                "duration": 3.5,
                "lines": [
                    {"t": "⚖️",                               "s": 100, "g": 18},
                    {"t": "ULIP or Mutual Fund?",             "s": 60,  "c": "#cff7ff", "g": 10},
                    {"t": "Most people choose wrong.",        "s": 56,  "c": "#06b6d4", "g": 24},
                    {"t": "Here's what your advisor should tell you.", "s": 30, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (6, 20, 30), "grad_bot": (10, 60, 88),
                "duration": 5.0,
                "lines": [
                    {"t": "₹5,000/month for 20 years:",      "s": 44, "c": "#cff7ff", "g": 24},
                    {"t": "🔵  ULIP (avg 8-10% post charges):", "s": 36, "c": "#67e8f9", "g": 8},
                    {"t": "₹28 — ₹37 Lakhs",                 "s": 64, "c": "#22d3ee", "g": 22},
                    {"t": "📈  MF + Term (avg 12-14%):",      "s": 36, "c": "#86efac", "g": 8},
                    {"t": "₹50 — ₹65 Lakhs",                 "s": 68, "c": "#4ade80", "g": 0},
                ],
            },
            {
                "grad_top": (5, 15, 28), "grad_bot": (8, 40, 80),
                "duration": 4.0,
                "lines": [
                    {"t": "ULIP — when it works:",            "s": 44, "c": "#cff7ff", "g": 36},
                    {"t": "✅  Insurance + investment combined","s": 38, "c": "#67e8f9", "g": 12},
                    {"t": "✅  Tax benefit under 80C + 10(D)", "s": 38, "c": "#67e8f9", "g": 12},
                    {"t": "✅  Best for long-term (15+ years)","s": 38, "c": "#67e8f9", "g": 12},
                    {"t": "⚠️   High charges in early years",  "s": 36, "c": "#fbbf24", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "Right strategy for most people:",  "s": 40, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Term insurance (pure cover)",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Mutual Fund SIP (pure growth)", "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Lower costs, higher returns",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "Talk to me — I'll show you numbers.", "s": 36, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "nps_pension": {
        "id":          "nps_pension",
        "name":        "NPS Pension Plan",
        "description": "Government-backed pension — guaranteed monthly income after 60",
        "icon":        "🏛️",
        "accent":      "#64748b",
        "scenes": [
            {
                "grad_top": (8, 10, 18), "grad_bot": (30, 40, 65),
                "duration": 3.5,
                "lines": [
                    {"t": "🏛️",                              "s": 100, "g": 18},
                    {"t": "Government pension.",             "s": 64,  "c": "#e2e8f0", "g": 10},
                    {"t": "Tax savings + retirement.",       "s": 56,  "c": "#94a3b8", "g": 24},
                    {"t": "Most salaried Indians miss this.", "s": 34, "c": "#777777", "g": 0},
                ],
            },
            {
                "grad_top": (10, 12, 22), "grad_bot": (35, 45, 70),
                "duration": 4.5,
                "lines": [
                    {"t": "NPS: National Pension Scheme",    "s": 44, "c": "#e2e8f0", "g": 20},
                    {"t": "₹5,000/month from age 30:",       "s": 40, "c": "#cbd5e1", "g": 10},
                    {"t": "Corpus at 60: ₹1.5 — 2 Cr",      "s": 66, "c": "#94a3b8", "g": 18},
                    {"t": "Monthly pension: ₹60,000+",       "s": 54, "c": "#f8fafc", "g": 14},
                    {"t": "Tax saved: ₹15,000/yr (80CCD)",   "s": 38, "c": "#64748b", "g": 0},
                ],
            },
            {
                "grad_top": (8, 10, 18), "grad_bot": (30, 40, 65),
                "duration": 4.0,
                "lines": [
                    {"t": "NPS benefits:",                    "s": 48, "c": "#e2e8f0", "g": 36},
                    {"t": "✅  Extra ₹50K deduction (80CCD2)","s": 38, "c": "#94a3b8", "g": 12},
                    {"t": "✅  Government co-contributes",    "s": 38, "c": "#94a3b8", "g": 12},
                    {"t": "✅  Market + debt mix (auto rebal)","s": 38, "c": "#94a3b8", "g": 12},
                    {"t": "✅  Regulated by PFRDA",            "s": 38, "c": "#94a3b8", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "Who should open NPS today?",       "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Salaried employees (Tier 1)",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Self-employed (extra 80CCD)",   "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Anyone below 40 wanting pension","s": 38, "c": "#55ff88", "g": 12},
                    {"t": "I'll help you open it in 15 mins.", "s": 36, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "sip_for_youth": {
        "id":          "sip_for_youth",
        "name":        "SIP for Young Earners",
        "description": "Start at 22 with ₹2,000/month — retire a crorepati",
        "icon":        "🚀",
        "accent":      "#10b981",
        "scenes": [
            {
                "grad_top": (5, 22, 12), "grad_bot": (8, 75, 30),
                "duration": 3.5,
                "lines": [
                    {"t": "🚀",                               "s": 100, "g": 18},
                    {"t": "Your first salary.",               "s": 60,  "c": "#d1fae5", "g": 10},
                    {"t": "Your first SIP.",                  "s": 72,  "c": "#10b981", "g": 24},
                    {"t": "The smartest move at 22.",         "s": 36,  "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (6, 24, 14), "grad_bot": (10, 78, 28),
                "duration": 4.5,
                "lines": [
                    {"t": "₹2,000/month at age 22:",          "s": 48, "c": "#d1fae5", "g": 22},
                    {"t": "At 32 → ₹4.6 Lakhs",              "s": 52, "c": "#6ee7b7", "g": 10},
                    {"t": "At 42 → ₹19 Lakhs",               "s": 60, "c": "#34d399", "g": 10},
                    {"t": "At 52 → ₹64 Lakhs",               "s": 68, "c": "#10b981", "g": 10},
                    {"t": "At 60 → ₹1.4 CRORE 🎉",           "s": 72, "c": "#059669", "g": 0},
                ],
            },
            {
                "grad_top": (28, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Waiting is the only risk:",        "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Start at 30 → ₹70 Lakhs less", "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  EMI-first mindset = no wealth", "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  Inflation eats idle money",     "s": 40, "c": "#ff6622", "g": 12},
                    {"t": "❌  No compounding = no crores",    "s": 40, "c": "#ff6622", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "Start SIP in 10 minutes:",         "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Min ₹500/month (Nifty 50)",    "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Zero entry/exit load",          "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Auto-debit (forget & grow)",    "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  I'll set it up for FREE",       "s": 44, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },

    "emergency_fund": {
        "id":          "emergency_fund",
        "name":        "Emergency Fund",
        "description": "6 months expenses in a liquid fund — the foundation of financial security",
        "icon":        "🛟",
        "accent":      "#f97316",
        "scenes": [
            {
                "grad_top": (22, 10, 5), "grad_bot": (85, 38, 8),
                "duration": 3.5,
                "lines": [
                    {"t": "🛟",                               "s": 100, "g": 18},
                    {"t": "Job loss. Medical emergency.",     "s": 52,  "c": "#ffedd5", "g": 10},
                    {"t": "Do you have 6 months saved?",     "s": 56,  "c": "#f97316", "g": 24},
                    {"t": "Most Indians don't. Do the math.", "s": 34, "c": "#aaaaaa", "g": 0},
                ],
            },
            {
                "grad_top": (24, 12, 5), "grad_bot": (88, 40, 8),
                "duration": 4.0,
                "lines": [
                    {"t": "Monthly expenses: ₹40,000",        "s": 44, "c": "#ffedd5", "g": 22},
                    {"t": "Emergency fund needed:",           "s": 40, "c": "#fed7aa", "g": 10},
                    {"t": "₹2.4 Lakhs (6 months)",           "s": 72, "c": "#fb923c", "g": 22},
                    {"t": "Where to keep it?",               "s": 40, "c": "#fdba74", "g": 10},
                    {"t": "Liquid Mutual Fund (4-5% return)", "s": 40, "c": "#f97316", "g": 0},
                ],
            },
            {
                "grad_top": (28, 8, 5), "grad_bot": (12, 8, 28),
                "duration": 4.0,
                "lines": [
                    {"t": "Without an emergency fund:",       "s": 44, "c": "#ffddcc", "g": 36},
                    {"t": "❌  Take high-interest personal loan","s": 38, "c": "#ff4444", "g": 12},
                    {"t": "❌  Sell investments at a loss",    "s": 38, "c": "#ff4444", "g": 12},
                    {"t": "❌  Family financial stress",       "s": 38, "c": "#ff4444", "g": 12},
                    {"t": "❌  Break long-term goals",         "s": 38, "c": "#ff4444", "g": 0},
                ],
            },
            {
                "grad_top": (5, 28, 10), "grad_bot": (8, 70, 22),
                "duration": 4.0,
                "lines": [
                    {"t": "Build it in 6 months:",            "s": 44, "c": "#ccffdd", "g": 36},
                    {"t": "✅  Save ₹40,000/month × 6",       "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Park in liquid fund (instant)", "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Earns 4-5% while waiting",     "s": 40, "c": "#55ff88", "g": 12},
                    {"t": "✅  Peace of mind: priceless",     "s": 40, "c": "#aaffcc", "g": 0},
                ],
            },
        ],
    },
}


# ─── Public API Helpers ────────────────────────────────────────────────────
def get_all_themes() -> list[dict]:
    return [
        {
            "id":          t["id"],
            "name":        t["name"],
            "description": t["description"],
            "icon":        t["icon"],
            "accent":      t["accent"],
        }
        for t in THEMES.values()
    ]


# ─── Custom AI Video Generation ────────────────────────────────────────────
_CUSTOM_VIDEO_PROMPT = """
You are generating scenes for a short marketing video for an Indian insurance/wealth advisor.
Topic: {topic}
Firm: {firm_name}

IMPORTANT: Write EVERY headline and subline ENTIRELY in {lang_label}.
- For Hindi/Marathi: use native Devanagari script (not Hinglish in Latin letters).
- For English: use simple, punchy phrasing — no jargon.

Generate exactly 4 video scenes as a JSON array. Each scene has:
- "headline": MAX 25 characters — the big bold line, very few words
- "sublines": list of 2-3 supporting lines, EACH MAX 35 characters
- "tone": one of ["shock", "contrast", "benefit", "cta"]
- "accent_color": hex color matching the tone (shock=red, contrast=amber, benefit=green, cta=purple)

Scene 1 = emotional hook (shock/problem)
Scene 2 = data/facts (contrast)
Scene 3 = without solution (problems)
Scene 4 = with solution (benefits + CTA)

Keep lines SHORT — viewers see each scene for only ~5 seconds. Long lines won't be read.

Reply ONLY with the JSON array. No markdown, no explanation.
Example for English:
[
  {{"headline": "One Illness.", "sublines": ["Everything gone", "Are you protected?"], "tone": "shock", "accent_color": "#ef4444"}},
  ...
]
"""

_LANG_LABELS = {"en": "English", "hi": "Hindi (हिंदी)", "mr": "Marathi (मराठी)"}


async def generate_custom_scenes(topic: str, lang: str = "en", firm_name: str = "") -> list[dict]:
    """Use Gemini to generate video scenes for any custom topic."""
    try:
        import biz_ai as ai
        prompt = _CUSTOM_VIDEO_PROMPT.format(
            topic=topic, lang_label=_LANG_LABELS.get(lang, "English"),
            firm_name=firm_name or "Sarathi",
        )
        raw = await ai._ask_gemini(prompt)
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scenes_data = json.loads(raw.strip())
        return scenes_data
    except Exception as e:
        logger.error("Custom scene generation failed: %s", e)
        return []


def _scenes_from_ai_data(scenes_data: list[dict], w: int, h: int) -> list[tuple]:
    """Convert AI-generated scene data into render-ready (scene_dict, is_cta) tuples."""
    tone_gradients = {
        "shock":    {"top": (28, 5, 5),   "bot": (90, 12, 12)},
        "contrast": {"top": (20, 15, 5),  "bot": (80, 50, 8)},
        "benefit":  {"top": (5, 28, 10),  "bot": (8, 70, 22)},
        "cta":      {"top": (12, 5, 28),  "bot": (50, 10, 90)},
    }
    tone_text_colors = {
        "shock":    ("#ffcccc", "#ff6666"),
        "contrast": ("#fff3cc", "#f59e0b"),
        "benefit":  ("#ccffdd", "#55ff88"),
        "cta":      ("#e0ccff", "#9b59b6"),
    }
    result = []
    for sd in scenes_data[:4]:
        tone = sd.get("tone", "benefit")
        grad = tone_gradients.get(tone, tone_gradients["benefit"])
        head_c, sub_c = tone_text_colors.get(tone, ("#ffffff", "#aaaaaa"))

        head_txt = (sd.get("headline") or "").strip()
        sublines = [s.strip() for s in sd.get("sublines", []) if s and s.strip()]

        # Auto-shrink headline size if long (Hindi/Marathi text is denser)
        head_len = len(head_txt)
        head_size = 76 if head_len <= 14 else (64 if head_len <= 22 else 52)

        lines = [{"t": head_txt, "s": head_size, "c": head_c, "g": 24}]
        for sub in sublines:
            sub_len = len(sub)
            sub_size = 40 if sub_len <= 30 else (34 if sub_len <= 40 else 30)
            lines.append({"t": sub, "s": sub_size, "c": sub_c, "g": 14})
        if lines:
            lines[-1]["g"] = 0

        # Duration: 4.5s base + 0.5s per subline so viewers can read each one.
        # Devanagari text needs slightly longer screen time.
        base_dur = 4.5 + 0.4 * len(sublines)
        if any(_has_devanagari(item["t"]) for item in lines):
            base_dur += 0.8
        scene_dur = round(min(base_dur, 7.0), 2)

        scene = {
            "grad_top": grad["top"],
            "grad_bot": grad["bot"],
            "duration": scene_dur,
            "lines": lines,
        }
        result.append((scene, False))
    return result


async def start_custom_video_job(
    topic: str,
    advisor_name: str,
    advisor_phone: str,
    fmt: str = "square",
    lang: str = "en",
    firm_name: str = "",
) -> str:
    """Generate a video for a completely custom topic using AI. Returns job_id."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status":     "generating",
        "url":        None,
        "filename":   None,
        "error":      None,
        "theme":      f"custom:{topic[:40]}",
        "fmt":        fmt,
        "created_at": datetime.utcnow().isoformat(),
    }

    loop = asyncio.get_event_loop()

    async def _async_run() -> None:
        try:
            scenes_data = await generate_custom_scenes(topic, lang, firm_name)
            if not scenes_data:
                raise RuntimeError("AI returned no scenes for this topic")

            w, h = _REELS_WH if fmt == "reels" else _SQUARE_WH
            # Determine accent from first scene
            accent = scenes_data[0].get("accent_color", "#3b82f6") if scenes_data else "#3b82f6"

            scene_tuples = _scenes_from_ai_data(scenes_data, w, h)

            def _render() -> str:
                fname = f"custom_{uuid.uuid4().hex[:8]}.mp4"
                out_path = os.path.join(VIDEO_DIR, fname)
                with tempfile.TemporaryDirectory() as tmpdir:
                    concat_lines: list[str] = []
                    all_scenes = scene_tuples + [
                        (None, True)  # CTA frame always last
                    ]
                    for idx, (scene, is_cta) in enumerate(all_scenes):
                        if is_cta:
                            frame = _make_cta_frame(advisor_name, advisor_phone, accent, w, h)
                            dur = 4.5
                        else:
                            frame = _make_frame(scene, w, h)
                            dur = float(scene.get("duration", 4.0))
                        png_path = os.path.join(tmpdir, f"s{idx:02d}.png")
                        Image.fromarray(frame).save(png_path)
                        del frame
                        concat_lines.append(f"file '{png_path}'")
                        concat_lines.append(f"duration {dur:.2f}")
                    concat_lines.append(f"file '{png_path}'")
                    concat_txt = os.path.join(tmpdir, "concat.txt")
                    with open(concat_txt, "w") as f:
                        f.write("\n".join(concat_lines) + "\n")
                    cmd = [
                        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", concat_txt,
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v", "libx264", "-preset", "ultrafast",
                        "-crf", "26", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", "-an", out_path,
                    ]
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                    if r.returncode != 0:
                        raise RuntimeError(f"ffmpeg failed: {r.stderr[-500:]}")
                return out_path

            path = await loop.run_in_executor(_executor, _render)
            fname = os.path.basename(path)
            _jobs[job_id].update(status="done", url=f"/api/video/file/{fname}", filename=fname)
        except Exception as exc:
            logger.error("Custom video job %s failed: %s", job_id, exc, exc_info=True)
            _jobs[job_id].update(status="failed", error=str(exc))

    asyncio.ensure_future(_async_run())
    return job_id


# ─── Video Builder — memory-safe direct ffmpeg approach ────────────────────
def _build_video_sync(
    theme_id: str,
    advisor_name: str,
    advisor_phone: str,
    fmt: str = "square",
) -> str:
    """
    Render one PNG per scene, then encode with ffmpeg concat demuxer.
    Peak RAM: ~3 MB (one 720×720 frame at a time). Safe on 1 GB servers.
    """
    theme = THEMES[theme_id]
    w, h = _REELS_WH if fmt == "reels" else _SQUARE_WH

    fname = f"{theme_id}_{uuid.uuid4().hex[:8]}.mp4"
    out_path = os.path.join(VIDEO_DIR, fname)

    with tempfile.TemporaryDirectory() as tmpdir:
        concat_lines: list[str] = []

        scenes = [(s, False) for s in theme["scenes"]] + [(None, True)]

        for idx, (scene, is_cta) in enumerate(scenes):
            if is_cta:
                frame = _make_cta_frame(
                    advisor_name, advisor_phone, theme["accent"], w, h
                )
                dur = 4.5
            else:
                frame = _make_frame(scene, w, h)
                dur = float(scene.get("duration", 4.0))

            # Write PNG (no lossy compression, but small compared to raw RGB)
            png_path = os.path.join(tmpdir, f"s{idx:02d}.png")
            Image.fromarray(frame).save(png_path)
            del frame  # free immediately

            concat_lines.append(f"file '{png_path}'")
            concat_lines.append(f"duration {dur:.2f}")

        # ffmpeg needs the last file entry repeated (quirk with concat demuxer)
        concat_lines.append(f"file '{png_path}'")

        concat_txt = os.path.join(tmpdir, "concat.txt")
        with open(concat_txt, "w") as f:
            f.write("\n".join(concat_lines) + "\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_txt,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",   # ensure even dims
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "26",        # quality (0=lossless, 28=default)
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",               # no audio
            out_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180
        )
        if result.returncode != 0:
            logger.error("ffmpeg stderr: %s", result.stderr[-2000:])
            raise RuntimeError(
                f"ffmpeg failed (rc={result.returncode}): "
                f"{result.stderr[-500:]}"
            )

    logger.info("Generated %s (%d bytes)", out_path, os.path.getsize(out_path))
    return out_path


# ─── Async Job System ──────────────────────────────────────────────────────
async def start_video_job(
    theme_id: str,
    advisor_name: str,
    advisor_phone: str,
    fmt: str = "square",
) -> str:
    """Start async video generation. Returns job_id immediately."""
    if theme_id not in THEMES:
        raise ValueError(f"Unknown theme: {theme_id!r}")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status":     "generating",
        "url":        None,
        "filename":   None,
        "error":      None,
        "theme":      theme_id,
        "fmt":        fmt,
        "created_at": datetime.utcnow().isoformat(),
    }

    loop = asyncio.get_event_loop()

    def _run() -> None:
        try:
            path = _build_video_sync(theme_id, advisor_name, advisor_phone, fmt)
            fname = os.path.basename(path)
            _jobs[job_id].update(
                status="done",
                url=f"/api/video/file/{fname}",
                filename=fname,
            )
        except Exception as exc:
            logger.error("Video job %s failed: %s", job_id, exc, exc_info=True)
            _jobs[job_id].update(status="failed", error=str(exc))

    loop.run_in_executor(_executor, _run)
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def cleanup_old_jobs(max_age_hours: int = 24) -> None:
    """Remove stale jobs and their video files."""
    now = datetime.utcnow()
    stale = []
    for jid, job in list(_jobs.items()):
        try:
            age_h = (now - datetime.fromisoformat(job["created_at"])).total_seconds() / 3600
            if age_h > max_age_hours:
                stale.append(jid)
                if job.get("filename"):
                    fp = os.path.join(VIDEO_DIR, job["filename"])
                    if os.path.exists(fp):
                        os.remove(fp)
        except Exception:
            pass
    for jid in stale:
        _jobs.pop(jid, None)
    if stale:
        logger.info("Cleaned up %d stale video jobs", len(stale))

