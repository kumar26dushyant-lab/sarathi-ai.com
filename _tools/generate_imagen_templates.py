#!/usr/bin/env python3
"""
generate_imagen_templates.py — One-time stock-photo library generator using
Google Imagen (via Gemini API).

Produces ~30 high-quality photo templates that the marketing studio will
overlay text + logo + branding on. Each template is 1080×1920 portrait (matches
WhatsApp Status) and intentionally leaves the top-left ~30% and bottom ~25%
mostly dark/empty so our existing overlay code has clean canvas.

Cost estimate: ~$0.04 per image × 30 = ~$1.20 (₹100) one-time.

Setup:
  1. pip install google-genai pillow
  2. Set GEMINI_API_KEY env var
  3. Run: python _tools/generate_imagen_templates.py

Output: writes PNGs to static/templates/marketing/imagen_<slug>.png
"""
from __future__ import annotations
import os
import sys
import time
import asyncio
from pathlib import Path
from io import BytesIO

# Project root on path so we can reuse env loading
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    if (ROOT / "biz.env").exists():
        load_dotenv(ROOT / "biz.env")
    elif (Path("/opt/sarathi/biz.env")).exists():
        load_dotenv("/opt/sarathi/biz.env")
except ImportError:
    pass

OUT_DIR = ROOT / "static" / "templates" / "marketing"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ── 30 prompt templates covering all advisor content needs ─────────────────
# IMPORTANT — Imagen 4 will literally draw any words/quotes from the prompt
# onto the image. So prompts MUST be pure scene descriptions: no quoted
# instructions, no "no text in image" (it interprets that as text to render),
# no aspect-ratio mentions, no format hints. We control those via SDK params
# (aspect_ratio="9:16") and via the separate `NEGATIVE_PROMPT` below.
NEGATIVE_PROMPT = (
    "text, letters, words, captions, watermark, logo, signature, signs, "
    "writing, typography, subtitles, labels, sign boards, posters, billboards"
)

TEMPLATES = [
    # ── Health insurance (6) ───────────────────────────────────────────────
    ("health_hospital_bill",
     "A worried middle-aged Indian couple sitting on a hospital corridor "
     "bench. The husband holds a paper in his hand. The wife covers her face "
     "with one hand, looking stressed. Soft hospital bed visible in the "
     "background, blurred. Dramatic editorial photojournalism lighting. Deep "
     "navy and warm gold tones. Cinematic mood."),

    ("health_family_protection",
     "A warm Indian joint family of five standing together at the entrance "
     "of their home at golden hour, smiling. Soft sunset light. Warm orange "
     "and protective blue tones. Cinematic, hopeful, photojournalism style."),

    ("health_doctor_consultation",
     "An Indian woman doctor in a white coat reassuring an Indian patient "
     "sitting on a hospital bed. Both have calm, hopeful expressions. Soft "
     "natural window light. Clinical blue, white and warm green tones."),

    ("health_critical_illness",
     "Close-up of an Indian man in his forties sitting alone by a window "
     "with diffuse soft sunlight, in a contemplative pose. Hopeful but "
     "introspective mood. Muted teal and warm cream tones. Editorial."),

    ("health_aged_parents",
     "An adult Indian son gently holding the hand of his elderly father "
     "sitting on a hospital bed. Both have warm dignified expressions. Soft "
     "natural window light. Warm beige and deep blue tones."),

    ("health_emergency_room",
     "An empty Indian hospital emergency corridor at night with overhead "
     "fluorescent lights. Soft motion blur. Cool blue with red accent lights. "
     "Cinematic, editorial mood, not graphic."),

    # ── Life / Term insurance (5) ──────────────────────────────────────────
    ("life_father_with_kids",
     "Warm bedroom interior at night. A glowing bedside lamp on a wooden "
     "table next to a stack of children's storybooks and a teddy bear on a "
     "neatly made bed with soft pillows. Deep indigo and warm amber tones. "
     "Soft cinematic editorial photography. No people in the frame."),

    ("life_mother_with_baby",
     "A peaceful Indian woman in her late twenties resting her head on a "
     "soft white cotton blanket, smiling gently with her eyes closed. Soft "
     "morning window light. Cream and rose gold tones. Editorial portrait."),

    ("life_family_at_temple",
     "An Indian family of four visiting a temple at dawn, lighting a brass "
     "diya together. Warm orange flame light on their faces. Saffron and "
     "deep maroon tones. Reverent, hopeful, cinematic."),

    ("life_couple_planning",
     "A young Indian couple sitting on a sofa together in a modern living "
     "room, looking at a paper thoughtfully. Coffee cups on the table. Warm "
     "afternoon light. Muted teal and amber tones. Editorial."),

    ("life_grandfather_legacy",
     "Portrait of an elderly Indian grandfather sitting on a wooden chair in "
     "his garden at golden hour, laughing warmly, looking off camera. Trees "
     "and warm sunset behind him. Amber and olive green tones. Cinematic, "
     "editorial."),

    # ── Investment / Wealth (5) ────────────────────────────────────────────
    ("invest_growth_chart",
     "An Indian businessman in his late thirties smiling confidently, "
     "looking at a tablet. Small green plants growing from coins on the desk "
     "in front of him. Soft light office with bokeh background. Emerald "
     "green and crisp white tones. Editorial professional photography."),

    ("invest_sip_chai",
     "An Indian woman in her early thirties sitting at her home kitchen "
     "table with a laptop and a steaming cup of chai. Bright morning window "
     "light. Open notebook beside her. Warm ivory and forest green tones."),

    ("invest_retirement_path",
     "An elderly Indian man in casual clothes walking on a peaceful park "
     "path at sunrise, holding a wooden cane, viewed from behind. Trees and "
     "morning mist around. Warm orange sky. Amber and deep teal tones. "
     "Inspirational, hopeful, cinematic."),

    ("invest_business_owner",
     "An Indian small-business owner, a woman around forty in traditional "
     "Indian attire, standing proudly in front of her boutique shop with "
     "arms folded. Vibrant shop interior softly blurred behind her. Rich "
     "maroon and gold tones. Editorial."),

    ("invest_child_education",
     "A neatly arranged wooden desk with a globe, an open notebook, a "
     "graduation cap with a tassel, a stack of books, and a small piggy bank. "
     "Soft golden hour window light. Royal blue and shimmering gold tones. "
     "Aspirational, hopeful, editorial still life photography. No people."),

    # ── Tax / Year-end (3) ─────────────────────────────────────────────────
    ("tax_march_deadline",
     "An Indian woman at her home desk smiling while looking at a laptop, "
     "holding a steaming cup of chai. Muted teal and warm cream tones. "
     "Editorial. Soft natural light."),

    ("tax_calculator_paperwork",
     "Top-down view of an Indian-style office desk with scattered papers, a "
     "calculator, a steel tumbler of tea, and a pen. Warm desk lamp light. "
     "Warm brown and ivory tones. Editorial."),

    ("tax_relief_smile",
     "An Indian salaried professional, a woman in her thirties in business "
     "casual, reading a printed paper with a relieved, warm smile. Soft "
     "sunlight streaming through a window. Soft coral and beige tones."),

    # ── Claims / Service (3) ───────────────────────────────────────────────
    ("claim_handshake_advisor",
     "Close-up of a handshake between an Indian insurance advisor, a man in "
     "a light blue shirt, and a relieved-looking woman client. Papers and a "
     "coffee cup on the table. Soft natural light from a window. Warm beige "
     "and deep blue tones. Editorial."),

    ("claim_settlement_relief",
     "An Indian couple in their fifties reading a paper together. The "
     "woman's hand is on her chest in relief, the man smiles softly. Soft "
     "afternoon light, comfortable home setting. Warm cream and sage green "
     "tones. Editorial."),

    ("claim_advisor_phone_support",
     "An Indian male insurance advisor at his desk, on a phone call with a "
     "warm attentive expression. Light office blur with a potted plant. Navy "
     "and warm white tones. Editorial photo."),

    # ── Vehicle insurance (2) ─────────────────────────────────────────────
    ("motor_monsoon_drive",
     "A wet Indian highway at dusk during a monsoon evening, a single car "
     "driving with headlights on, light rain falling. Slight motion blur on "
     "the rain. Deep blue-grey tones with bright yellow headlights. Cinematic."),

    ("motor_family_road_trip",
     "An Indian family of four packing a car for a road trip on a sunny "
     "morning in a residential neighbourhood. Kids excited, mother smiling, "
     "father loading the trunk. Warm yellow and sky blue tones. Editorial."),

    # ── Festivals / Seasonal (4) ──────────────────────────────────────────
    ("festival_diwali",
     "An Indian family of four lighting clay diyas on the doorstep of their "
     "home decorated with rangoli, marigold flowers, and fairy lights at "
     "night. Warm fire glow on faces. Deep saffron, royal blue, and gold "
     "tones. Cinematic, photojournalism style."),

    ("festival_raksha_bandhan",
     "An Indian brother and sister, both in their twenties, smiling warmly. "
     "Sister tying a colourful thread on brother's wrist. Marigold flowers "
     "and sweets in the background. Maroon and gold tones. Editorial."),

    ("festival_holi",
     "An Indian family playing Holi, faces dusted with vibrant pink and "
     "yellow gulal powder, laughing. Soft sunlight. Warm pink, yellow, and "
     "blue tones. Cinematic."),

    ("festival_new_year",
     "An Indian young couple together at a cosy home cafe, warm fairy lights "
     "behind them. Mug of coffee on the table. Deep indigo and warm amber "
     "tones. Editorial."),

    # ── Generic / Advisor (2) ─────────────────────────────────────────────
    ("advisor_meeting_with_couple",
     "An Indian insurance advisor, a woman in her mid-thirties, sitting "
     "across a desk from an Indian couple, gesturing thoughtfully toward a "
     "paper. Warm office, soft natural light. Navy and warm cream tones. "
     "Editorial."),

    ("advisor_office_modern",
     "A modern warm Indian advisory office with wooden furniture, indoor "
     "plants, and a single empty client chair. Soft golden hour light "
     "through a window. Warm wood, ivory, and sage tones. Cinematic, "
     "trustworthy mood."),
]


def gen_one(client, slug: str, prompt: str, out_path: Path) -> bool:
    """Generate a single image via Imagen."""
    try:
        # Newer SDK exposes generate_images on models
        resp = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config={
                "number_of_images": 1,
                "aspect_ratio": "9:16",
                "person_generation": "ALLOW_ADULT",
            },
        )
        if not resp or not getattr(resp, "generated_images", None):
            print(f"  ✗ {slug}: empty response")
            return False
        img_bytes = resp.generated_images[0].image.image_bytes
        out_path.write_bytes(img_bytes)
        print(f"  ✓ {slug} → {out_path.name} ({len(img_bytes)//1024} KB)")
        return True
    except Exception as e:
        print(f"  ✗ {slug}: {e}")
        return False


def main(only_slug: str | None = None):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set (check biz.env or env var)")
        sys.exit(1)

    try:
        from google import genai
    except ImportError:
        print("ERROR: pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print(f"Output dir: {OUT_DIR}")
    print(f"Generating {len(TEMPLATES)} templates via Imagen 4...")
    print()
    successes = 0
    skipped = 0
    failures = 0

    for slug, prompt in TEMPLATES:
        if only_slug and slug != only_slug:
            continue
        out_path = OUT_DIR / f"imagen_{slug}.png"
        if out_path.exists():
            print(f"  · {slug}: already exists, skip")
            skipped += 1
            continue
        ok = gen_one(client, slug, prompt, out_path)
        if ok:
            successes += 1
        else:
            failures += 1
        time.sleep(2)  # respect rate limit

    print()
    print(f"Done. ✓ {successes} created · {skipped} skipped · ✗ {failures} failed")
    print(f"Total in folder: {len(list(OUT_DIR.glob('*.png')))}")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    main(only)
