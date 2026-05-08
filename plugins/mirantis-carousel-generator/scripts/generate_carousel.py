#!/usr/bin/env python3
"""
Instagram carousel generator — opinionated gallery aesthetic.

Design spec (fixed):
  - Typeface: Lora (titles, SemiBold) + Noto Sans (body, Regular/Medium)
  - Palette: cream bg, near-black ink, warm gray for metadata, muted terracotta accent
  - Canvas: 1080×1080 (square) or 1080×1350 (portrait) — configurable per run
  - Three archetypes: cover, content, closing
  - Signatures: slide numbers (01/07 style) + thin accent rule

Usage:
    python generate_carousel.py spec.json --out ./out --size square
    python generate_carousel.py spec.json --out ./out --size portrait
    python generate_carousel.py spec.json --out ./out --size both

Input JSON format:
    {
      "title": "Карусель Art",         // used on cover
      "subtitle": "optional kicker",   // optional, appears above title on cover
      "author": "alexander sacha gelf",       // optional, appears at bottom of cover
      "slides": [
        {"type": "cover"},             // uses title/subtitle/author from top
        {"type": "content", "heading": "...", "body": "..."},
        {"type": "content", "heading": "...", "body": "..."},
        {"type": "closing", "body": "Spasibo!", "cta": "@handle"}
      ]
    }
"""

import argparse
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ----- Design spec (do not modify casually; this is the brand) -----

PALETTE = {
    "bg":        "#F4EFE6",  # warm cream
    "ink":       "#1C1A17",  # near-black with brown undertone
    "meta":      "#6B6560",  # warm gray (slide numbers, metadata)
    "accent":    "#8B4A3B",  # muted terracotta
}

SIZES = {
    "square":   (1080, 1080),
    "portrait": (1080, 1350),
}

# Font axes for Lora variable font
LORA_SEMIBOLD = 600
LORA_REGULAR  = 400

FONTS_DIR = Path(__file__).parent.parent / "assets"

def load_fonts(size_key):
    """Load fonts sized proportionally to canvas. Returns dict of named fonts."""
    W, H = SIZES[size_key]
    base = H / 1080.0  # scale factor keyed off height

    def lora(pt, weight=LORA_SEMIBOLD, italic=False):
        path = FONTS_DIR / ("Lora-Italic-Variable.ttf" if italic else "Lora-Variable.ttf")
        f = ImageFont.truetype(str(path), int(pt * base))
        f.set_variation_by_axes([weight])
        return f

    def noto(pt, weight="Regular"):
        path = FONTS_DIR / f"NotoSans-{weight}.ttf"
        return ImageFont.truetype(str(path), int(pt * base))

    return {
        "cover_kicker":    noto(22, "Medium"),
        "cover_title":     lora(92, LORA_SEMIBOLD),
        "cover_subtitle":  lora(36, LORA_REGULAR, italic=True),
        "cover_author":    noto(22, "Regular"),
        "content_heading": lora(56, LORA_SEMIBOLD),
        "content_body":    noto(30, "Regular"),
        "closing_body":    lora(50, LORA_SEMIBOLD),
        "closing_cta":     noto(26, "Medium"),
        "slide_number":    noto(20, "Medium"),
        "page_label":      noto(20, "Regular"),
    }

# ----- Layout primitives -----

MARGIN_RATIO = 0.093          # ~100px on a 1080 canvas, generous gallery-style margins
RULE_WIDTH_PX = 3
ACCENT_RULE_LENGTH_RATIO = 0.08  # unified rule length across all archetypes

# Noto Sans (latin-greek-cyrillic subset) lacks some symbol glyphs.
# Substitute them with editorial equivalents before rendering, so CTAs
# don't produce tofu boxes. These substitutions also read better in the
# gallery aesthetic than arrows/chevrons would.
GLYPH_SUBSTITUTIONS = {
    "→": "·",
    "←": "·",
    "↑": "·",
    "↓": "·",
    "⇒": "·",
    "▶": "·",
}

def sanitize_text(text):
    """Replace glyphs that our font subset can't render with editorial equivalents."""
    if not text:
        return text
    for bad, good in GLYPH_SUBSTITUTIONS.items():
        text = text.replace(bad, good)
    return text

def draw_slide_number(draw, W, H, idx, total, fonts):
    """Top-right: 01/07 style."""
    margin = int(W * MARGIN_RATIO)
    text = f"{idx:02d} / {total:02d}"
    bbox = draw.textbbox((0, 0), text, font=fonts["slide_number"])
    tw = bbox[2] - bbox[0]
    draw.text((W - margin - tw, margin), text, font=fonts["slide_number"], fill=PALETTE["meta"])

def draw_accent_rule(draw, W, H, y_ratio=None, x_start_ratio=None, centered=False):
    """Thin accent rule — the recurring design motif. Uses unified length."""
    margin = int(W * MARGIN_RATIO)
    length = int(W * ACCENT_RULE_LENGTH_RATIO)
    y = int(H * y_ratio) if y_ratio is not None else margin + int(H * 0.04)
    if centered:
        x_start = (W - length) // 2
    else:
        x_start = int(W * x_start_ratio) if x_start_ratio is not None else margin
    draw.rectangle([x_start, y, x_start + length, y + RULE_WIDTH_PX], fill=PALETTE["accent"])

def wrap_text(text, font, max_width, draw):
    """Greedy word-wrap using actual text measurement. Returns list of lines."""
    words = text.split()
    lines = []
    current = []
    for word in words:
        trial = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines

def draw_wrapped(draw, text, font, x, y, max_width, fill, line_spacing=1.3):
    """Draw wrapped text from (x, y). Returns the final y-coordinate after drawing."""
    lines = wrap_text(text, font, max_width, draw)
    # Use font metrics for consistent line height
    ascent, descent = font.getmetrics()
    line_height = int((ascent + descent) * line_spacing)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y

# ----- Slide archetypes -----

def render_cover(img, draw, fonts, spec, idx, total):
    W, H = img.size
    margin = int(W * MARGIN_RATIO)
    content_width = W - 2 * margin

    # Slide number top-right
    draw_slide_number(draw, W, H, idx, total, fonts)

    # Accent rule top-left (signature element)
    draw_accent_rule(draw, W, H, y_ratio=0.093, x_start_ratio=MARGIN_RATIO)

    # Pull title/subtitle/kicker from spec, sanitized for bad glyphs
    title    = sanitize_text(spec.get("title", ""))
    subtitle = sanitize_text(spec.get("subtitle"))
    kicker   = sanitize_text(spec.get("kicker"))
    author   = sanitize_text(spec.get("author"))

    # Measure block height: [kicker] -> title -> [subtitle]
    title_lines = wrap_text(title, fonts["cover_title"], content_width, draw)
    t_ascent, t_descent = fonts["cover_title"].getmetrics()
    title_line_h = int((t_ascent + t_descent) * 1.15)
    title_block_h = title_line_h * len(title_lines)

    kicker_h = 0
    if kicker:
        k_ascent, k_descent = fonts["cover_kicker"].getmetrics()
        kicker_h = int((k_ascent + k_descent) * 1.3) + int(H * 0.025)

    subtitle_h = 0
    subtitle_lines = []
    if subtitle:
        subtitle_lines = wrap_text(subtitle, fonts["cover_subtitle"], content_width, draw)
        s_ascent, s_descent = fonts["cover_subtitle"].getmetrics()
        subtitle_line_h = int((s_ascent + s_descent) * 1.3)
        subtitle_h = subtitle_line_h * len(subtitle_lines) + int(H * 0.03)

    total_block_h = kicker_h + title_block_h + subtitle_h
    # Shift slightly above optical center — text always appears centered when
    # it's a touch high. Also compensates for the author line weighing the bottom.
    y = int((H - total_block_h) / 2 - H * 0.04)

    # Kicker (optional)
    if kicker:
        draw.text((margin, y), kicker.upper(), font=fonts["cover_kicker"], fill=PALETTE["accent"])
        y += kicker_h

    # Title
    for line in title_lines:
        draw.text((margin, y), line, font=fonts["cover_title"], fill=PALETTE["ink"])
        y += title_line_h

    # Subtitle (optional)
    if subtitle:
        y += int(H * 0.03)
        s_ascent, s_descent = fonts["cover_subtitle"].getmetrics()
        subtitle_line_h = int((s_ascent + s_descent) * 1.3)
        for line in subtitle_lines:
            draw.text((margin, y), line, font=fonts["cover_subtitle"], fill=PALETTE["meta"])
            y += subtitle_line_h

    # Author at bottom
    if author:
        draw.text((margin, H - margin - 26), author, font=fonts["cover_author"], fill=PALETTE["meta"])

def render_content(img, draw, fonts, slide, idx, total):
    W, H = img.size
    margin = int(W * MARGIN_RATIO)
    content_width = W - 2 * margin

    draw_slide_number(draw, W, H, idx, total, fonts)
    draw_accent_rule(draw, W, H, y_ratio=0.093, x_start_ratio=MARGIN_RATIO)

    heading = sanitize_text(slide.get("heading", ""))
    body    = sanitize_text(slide.get("body", ""))

    # Gallery-label composition: anchor the whole block so the body's last line
    # sits at ~85% from top. Everything above it is intentional airy whitespace.
    # We measure bottom-up to position correctly.

    # Measure body
    body_line_h = 0
    body_lines = []
    if body:
        body_lines = wrap_text(body, fonts["content_body"], content_width, draw)
        b_ascent, b_descent = fonts["content_body"].getmetrics()
        body_line_h = int((b_ascent + b_descent) * 1.45)
    body_h = body_line_h * len(body_lines)

    # Measure heading
    heading_lines = []
    heading_line_h = 0
    if heading:
        heading_lines = wrap_text(heading, fonts["content_heading"], content_width, draw)
        h_ascent, h_descent = fonts["content_heading"].getmetrics()
        heading_line_h = int((h_ascent + h_descent) * 1.15)
    heading_h = heading_line_h * len(heading_lines)

    gap_between = int(H * 0.04) if (heading and body) else 0
    total_block_h = heading_h + gap_between + body_h

    # Anchor: bottom edge of block sits at 85% of canvas height
    bottom_anchor = int(H * 0.85)
    y = bottom_anchor - total_block_h

    # Heading
    for line in heading_lines:
        draw.text((margin, y), line, font=fonts["content_heading"], fill=PALETTE["ink"])
        y += heading_line_h

    if heading and body:
        y += gap_between

    # Body
    for line in body_lines:
        draw.text((margin, y), line, font=fonts["content_body"], fill=PALETTE["ink"])
        y += body_line_h

def render_closing(img, draw, fonts, slide, idx, total):
    W, H = img.size
    margin = int(W * MARGIN_RATIO)
    content_width = W - 2 * margin

    draw_slide_number(draw, W, H, idx, total, fonts)

    body = sanitize_text(slide.get("body", ""))
    cta  = sanitize_text(slide.get("cta", ""))

    # Compose centered block: [rule] — small gap — [body] — larger gap — [cta]
    # The rule is a visual punctuation mark above the body, not a separator
    # equal to the body-cta gap. Tight coupling above, breathe below.

    body_lines = wrap_text(body, fonts["closing_body"], content_width, draw) if body else []
    b_ascent, b_descent = fonts["closing_body"].getmetrics()
    body_line_h = int((b_ascent + b_descent) * 1.25)
    body_h = body_line_h * len(body_lines)

    cta_h = 0
    if cta:
        c_ascent, c_descent = fonts["closing_cta"].getmetrics()
        cta_h = int((c_ascent + c_descent) * 1.3)

    rule_to_body_gap = int(H * 0.025)   # tight — rule sits as typographic mark
    body_to_cta_gap  = int(H * 0.05)    # roomier — visible separation
    rule_h = RULE_WIDTH_PX

    total_h = rule_h + rule_to_body_gap + body_h
    if cta:
        total_h += body_to_cta_gap + cta_h

    # Shift slightly above optical center
    y = int((H - total_h) / 2 - H * 0.02)

    # Centered rule
    rule_length = int(W * ACCENT_RULE_LENGTH_RATIO)
    rule_x = (W - rule_length) // 2
    draw.rectangle([rule_x, y, rule_x + rule_length, y + rule_h], fill=PALETTE["accent"])
    y += rule_h + rule_to_body_gap

    # Body (centered)
    for line in body_lines:
        bbox = draw.textbbox((0, 0), line, font=fonts["closing_body"])
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) // 2, y), line, font=fonts["closing_body"], fill=PALETTE["ink"])
        y += body_line_h

    # CTA (centered, smaller, in accent)
    if cta:
        y += body_to_cta_gap
        bbox = draw.textbbox((0, 0), cta, font=fonts["closing_cta"])
        cw = bbox[2] - bbox[0]
        draw.text(((W - cw) // 2, y), cta, font=fonts["closing_cta"], fill=PALETTE["accent"])

# ----- Orchestrator -----

RENDERERS = {
    "cover":   render_cover,
    "content": render_content,
    "closing": render_closing,
}

def render_deck(spec, size_key, out_dir):
    W, H = SIZES[size_key]
    fonts = load_fonts(size_key)
    slides = spec.get("slides", [])
    total = len(slides)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for i, slide in enumerate(slides, start=1):
        img = Image.new("RGB", (W, H), PALETTE["bg"])
        draw = ImageDraw.Draw(img)
        stype = slide.get("type", "content")
        renderer = RENDERERS.get(stype)
        if renderer is None:
            print(f"Unknown slide type: {stype}", file=sys.stderr)
            continue
        if stype == "cover":
            renderer(img, draw, fonts, spec, i, total)
        else:
            renderer(img, draw, fonts, slide, i, total)

        out_path = out_dir / f"slide_{i:02d}_{stype}_{size_key}.png"
        img.save(out_path, "PNG", optimize=True)
        paths.append(out_path)
        print(f"  wrote {out_path}")
    return paths

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_file", help="Path to JSON spec")
    ap.add_argument("--out", default="./out", help="Output directory")
    ap.add_argument("--size", choices=["square", "portrait", "both"], default="square")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec_file).read_text(encoding="utf-8"))
    sizes = ["square", "portrait"] if args.size == "both" else [args.size]
    for size_key in sizes:
        print(f"[{size_key}]")
        render_deck(spec, size_key, args.out)

if __name__ == "__main__":
    main()
