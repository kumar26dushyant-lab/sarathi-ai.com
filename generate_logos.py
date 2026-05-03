"""Generate 4 Sarathi-AI logo PNG variants (EN/HI × light/dark) with transparent backgrounds."""
from PIL import Image, ImageDraw, ImageFont
import math, os

OUT = "static/logos"
os.makedirs(OUT, exist_ok=True)

# ── Colors ──────────────────────────────────────────────────
TEAL = (13, 148, 136)
TEAL_LIGHT = (20, 184, 166)
GOLD = (245, 158, 11)
GOLD_DARK = (217, 119, 6)
WHITE = (255, 255, 255)
DARK_BG_TEXT = (241, 245, 249)  # light gray for dark variant
LIGHT_BRAND = (49, 46, 129)    # indigo-900 for light mode brand name
DARK_BRAND = (241, 245, 249)   # near-white for dark mode brand name
LIGHT_TAGLINE = (100, 116, 139)  # gray-500 for light mode
DARK_TAGLINE = (148, 163, 184)   # gray-400 for dark mode

# ── Fonts ───────────────────────────────────────────────────
NIRMALA = "C:/Windows/Fonts/Nirmala.ttc"

def get_font(size, bold=False, hindi=False):
    if hindi:
        return ImageFont.truetype(NIRMALA, size, index=1 if bold else 0)
    return ImageFont.truetype("arialbd.ttf" if bold else "arial.ttf", size)

# ── Tree/Circuit Icon Drawing ───────────────────────────────
def draw_tree_icon(draw, cx, cy, scale=1.0):
    """Draw a circuit-tree hybrid icon centered at (cx, cy)."""
    s = scale

    # Trunk
    trunk_top = cy - int(30*s)
    trunk_bottom = cy + int(45*s)
    trunk_w = int(5*s)
    draw.rounded_rectangle(
        [cx - trunk_w, trunk_top, cx + trunk_w, trunk_bottom],
        radius=int(3*s), fill=TEAL)

    # Root lines (circuit style)
    for dx, length in [(-18, 18), (18, 18), (-10, 12), (10, 12)]:
        x1 = cx + int(dx*s)
        x2 = cx + int(dx*s) + (int(length*s) if dx > 0 else -int(length*s))
        y = trunk_bottom - int(3*s)
        draw.line([(x1, y), (x2, y + int(10*s))], fill=TEAL, width=max(2, int(2*s)))
        # Circuit dot at end
        r = max(2, int(3*s))
        draw.ellipse([x2-r, y+int(10*s)-r, x2+r, y+int(10*s)+r], fill=GOLD)

    # Canopy circles (overlapping, like a tree crown)
    canopy_r = int(22*s)
    canopy_positions = [
        (cx, cy - int(50*s)),        # top center
        (cx - int(20*s), cy - int(35*s)),  # left
        (cx + int(20*s), cy - int(35*s)),  # right
        (cx - int(10*s), cy - int(48*s)),  # top-left
        (cx + int(10*s), cy - int(48*s)),  # top-right
    ]
    for (px, py) in canopy_positions:
        draw.ellipse([px-canopy_r, py-canopy_r, px+canopy_r, py+canopy_r], fill=TEAL)

    # Branch circuit lines in canopy
    branch_lines = [
        (cx, cy - int(30*s), cx - int(14*s), cy - int(50*s)),
        (cx, cy - int(30*s), cx + int(14*s), cy - int(50*s)),
        (cx - int(14*s), cy - int(50*s), cx - int(24*s), cy - int(42*s)),
        (cx + int(14*s), cy - int(50*s), cx + int(24*s), cy - int(42*s)),
        (cx, cy - int(50*s), cx, cy - int(65*s)),
    ]
    for (x1, y1, x2, y2) in branch_lines:
        draw.line([(x1, y1), (x2, y2)], fill=TEAL_LIGHT, width=max(2, int(2*s)))

    # Gold dots (circuit nodes) on canopy
    node_positions = [
        (cx, cy - int(65*s)),
        (cx - int(24*s), cy - int(42*s)),
        (cx + int(24*s), cy - int(42*s)),
        (cx - int(14*s), cy - int(50*s)),
        (cx + int(14*s), cy - int(50*s)),
        (cx, cy - int(50*s)),
    ]
    nr = max(3, int(4*s))
    for (nx, ny) in node_positions:
        draw.ellipse([nx-nr, ny-nr, nx+nr, ny+nr], fill=GOLD)

    # Central glowing dot at top
    gr = max(4, int(6*s))
    draw.ellipse([cx-gr, cy-int(65*s)-gr, cx+gr, cy-int(65*s)+gr], fill=GOLD)
    draw.ellipse([cx-gr+2, cy-int(65*s)-gr+2, cx+gr-2, cy-int(65*s)+gr-2], fill=GOLD_DARK)


def generate_logo(lang='en', theme='light'):
    """Generate a single logo variant."""
    W, H = 800, 360
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))  # transparent
    draw = ImageDraw.Draw(img)

    is_dark = theme == 'dark'
    is_hindi = lang == 'hi'

    # ── Draw tree icon on left ──
    icon_cx, icon_cy = 130, 180
    draw_tree_icon(draw, icon_cx, icon_cy, scale=2.0)

    # ── Text area ──
    text_x = 270
    brand_color = DARK_BRAND if is_dark else LIGHT_BRAND
    tagline_color = DARK_TAGLINE if is_dark else LIGHT_TAGLINE
    ai_color = TEAL

    # Brand name: "SARATHI" in brand color + "-AI" in teal
    if is_hindi:
        brand_font = get_font(62, bold=True, hindi=True)
        ai_font = get_font(62, bold=True, hindi=False)
        brand_text = "सारथी"
        ai_text = "-AI"
    else:
        brand_font = get_font(58, bold=True)
        ai_font = get_font(58, bold=True)
        brand_text = "SARATHI"
        ai_text = "-AI"

    brand_y = 70
    # Draw brand name
    bbox = draw.textbbox((text_x, brand_y), brand_text, font=brand_font)
    draw.text((text_x, brand_y), brand_text, fill=brand_color, font=brand_font)
    ai_x = bbox[2] + 2
    draw.text((ai_x, brand_y), ai_text, fill=ai_color, font=ai_font)

    # Tagline 1: "BUSINESS TECHNOLOGIES" / "बिज़नेस टेक्नोलॉजीज़"
    if is_hindi:
        sub_font = get_font(24, bold=False, hindi=True)
        sub_text = "बिज़नेस टेक्नोलॉजीज़"
    else:
        sub_font = get_font(22, bold=False)
        sub_text = "BUSINESS TECHNOLOGIES"

    sub_y = brand_y + 72
    draw.text((text_x, sub_y), sub_text, fill=tagline_color, font=sub_font)

    # Divider line
    div_y = sub_y + 36
    draw.line([(text_x, div_y), (text_x + 340, div_y)], fill=GOLD, width=2)

    # Tagline 2: "YOUR AI BUSINESS NAVIGATOR" / "आपका AI बिज़नेस नेविगेटर"
    if is_hindi:
        tag_font = get_font(20, bold=True, hindi=True)
        tag_text = "आपका AI बिज़नेस नेविगेटर"
    else:
        tag_font = get_font(17, bold=True)
        tag_text = "YOUR AI BUSINESS NAVIGATOR"

    tag_y = div_y + 14
    draw.text((text_x, tag_y), tag_text, fill=GOLD, font=tag_font)

    # ── Small "Powered by AI" badge ──
    badge_y = tag_y + 36
    badge_font = get_font(13, bold=False)
    badge_text = "🤖 AI-Powered CRM for Financial Advisors" if not is_hindi else "🤖 फाइनेंशियल एडवाइज़र्स के लिए AI-पावर्ड CRM"
    if is_hindi:
        badge_font = get_font(14, bold=False, hindi=True)
    draw.text((text_x, badge_y), badge_text, fill=tagline_color, font=badge_font)

    # ── Save ──
    fname = f"sarathi_logo_{lang}_{theme}.png"
    fpath = os.path.join(OUT, fname)
    img.save(fpath, 'PNG')
    size_kb = os.path.getsize(fpath) // 1024
    print(f"✅ {fname}: {img.size[0]}x{img.size[1]}, {size_kb} KB")
    return fpath


# ── Also generate a compact square icon version ──
def generate_icon():
    """Generate a square icon (just the tree, no text)."""
    S = 256
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_tree_icon(draw, S//2, S//2 + 20, scale=2.5)
    fpath = os.path.join(OUT, "sarathi_icon.png")
    img.save(fpath, 'PNG')
    size_kb = os.path.getsize(fpath) // 1024
    print(f"✅ sarathi_icon.png: {S}x{S}, {size_kb} KB")


if __name__ == '__main__':
    for lang in ('en', 'hi'):
        for theme in ('light', 'dark'):
            generate_logo(lang, theme)
    generate_icon()
    print(f"\nAll logos saved to {OUT}/")
