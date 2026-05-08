---
name: mirantis-carousel-generator
description: "Generate Instagram carousel slides with a fixed gallery-aesthetic design — warm cream background, muted terracotta accent, Lora + Noto Sans typography, full Cyrillic support. Use this skill whenever the user wants to create Instagram carousels, IG slide decks, multi-slide Instagram posts, or educational post sequences including in Russian. Produces 1080×1080 square or 1080×1350 portrait PNG files from a simple JSON spec of title, author, and slide contents. Supports three slide archetypes — cover, content, closing. Trigger even if the user doesn't say 'carousel' — phrases like 'Instagram post series', 'slides for my Instagram', 'образовательный пост для Instagram', 'карусель для курса' all apply."
---

# Mirantis Carousel Generator

Generate Instagram carousel PNGs with a locked-in gallery aesthetic. The design decisions are intentionally fixed — this skill exists so carousels come out visually consistent every time without re-negotiating typography or palette.

## The design spec (fixed, do not override)

- **Background:** `#F4EFE6` (warm cream, paper-like)
- **Primary ink:** `#1C1A17` (near-black with a brown undertone)
- **Metadata gray:** `#6B6560` (slide numbers, author line)
- **Accent:** `#8B4A3B` (muted terracotta — used for thin rules and CTA emphasis only)
- **Title face:** Lora SemiBold (variable axis 600) — for cover titles, content headings, closing body
- **Body face:** Noto Sans Regular/Medium — for subtitles, content body, metadata
- **Both typefaces include full Cyrillic coverage** — Russian text renders natively
- **Canvas:** 1080×1080 square or 1080×1350 portrait
- **Signature elements:** slide numbers (`01 / 07` top-right) and a thin terracotta accent rule (top-left on cover and content slides, centered on closing)
- **Margins:** ~9.3% of width (generous, gallery-style asymmetric whitespace)

When the user requests changes to any of these, push back gently and explain the skill is opinionated by design — the whole point is consistency across carousels. If they truly want to override something (e.g. different accent color for a specific project), edit the `PALETTE` dict at the top of `scripts/generate_carousel.py` directly; don't fork the skill.

## Slide archetypes

Only three exist. Resist any urge to invent new types — if the content doesn't fit, rework it into one of these three.

1. **cover** — uses the top-level `title`, optional `kicker` (small uppercase accent text above title), optional `subtitle` (italic Lora), optional `author` (bottom-left). The cover slide itself has no per-slide content; just `{"type": "cover"}`.
2. **content** — has `heading` (Lora SemiBold, large) and `body` (Noto Sans, flowing paragraph). Use for lesson points, concepts, lists-as-prose.
3. **closing** — centered treatment with accent rule, `body` (Lora, could be thanks/takeaway), optional `cta` (Noto Sans Medium in accent color — handle, link, next steps).

## Workflow

When a user asks for a carousel:

### 1. Gather the content

If the user gives plain text (lesson titles, quotes, bullets), organize it into the archetype structure yourself. Don't make them write JSON.

A typical 5–7 slide carousel is: cover → 3–5 content → closing. Aim for ~40-80 words per content slide body — longer than that will look cramped or wrap ugly.

For **Russian / Cyrillic content**: preserve все the punctuation exactly as written, including «ёлочки» quotes, em-dashes, and guillemets. The fonts handle these correctly.

### 2. Write a spec JSON

Save it next to where outputs will go. Example:

```json
{
  "title": "Учимся писать Claude Skills",
  "kicker": "курс в школе «Мирантис»",
  "subtitle": "как создавать и анализировать скиллы в клоде",
  "author": "alexander sacha gelf",
  "slides": [
    {"type": "cover"},
    {"type": "content",
     "heading": "Зачем нам это надо?",
     "body": "Скиллы — это способ научить Клода работать по-вашему: со своими шаблонами, форматами и инструментами. Они превращают обычный чат в инструмент, заточенный под конкретную задачу. За шесть занятий вы научитесь собирать скиллы, которые экономят часы рутины и дают предсказуемый результат в ответ на одну команду."},
    {"type": "content",
     "heading": "Что входит в курс",
     "body": "Шесть встреч по два часа. Разбираем структуру SKILL.md, работу с ассетами и вспомогательными скриптами, локальное тестирование и отладку. Каждое занятие — практическое: к концу курса у вас на руках свой рабочий скилл, готовый к использованию в реальных задачах."},
    {"type": "closing",
     "body": "Начинаем 15 февраля",
     "cta": "@mirantis.school"}
  ]
}
```

### 3. Run the generator

```bash
python scripts/generate_carousel.py /path/to/spec.json --out /path/to/output --size square
```

`--size` accepts `square` (1080×1080), `portrait` (1080×1350), or `both` (generates both sets).

Default to `square` unless the user specifies otherwise. Use `both` when they're unsure — it's cheap to generate and lets them pick.

### 4. Review and present

View 1–2 of the rendered PNGs yourself to sanity-check (use the `view` tool on the output path — it renders images). Look specifically for: text overflowing margins, Cyrillic rendering artifacts, awkward wraps on headings (3-word headings that wrap to 2 lines with one orphan).

If a content body is wrapping badly, either shorten it or split into two slides. Don't shrink fonts — the fonts are tuned to the canvas.

Then present the output files to the user.

## Common pitfalls

- **Overlong headings.** Content headings look best at 2–5 words, max 2 lines. If the user gives a sentence-length heading, offer to rework it.
- **Body text that's really a list.** IG carousels read better as flowing prose than as bullet points. Rewrite lists into 2–3 sentences per slide rather than cramming bullets onto the canvas.
- **Mixed languages on one slide.** Both fonts handle Latin + Cyrillic, so this works fine technically, but it reads cleaner to keep one slide in one language.
- **Too many slides.** 5–7 is the sweet spot. More than 10 and engagement drops; fewer than 4 and it's not really a carousel.
- **Hex color requests from the user.** See design spec note above — if they really want it, edit the script's `PALETTE` dict directly.
- **Arrows in CTAs (`→`, `⇒`).** The Noto Sans latin-greek-cyrillic subset doesn't include arrow glyphs. The generator's `sanitize_text()` function auto-substitutes them with `·` (middle dot), which reads more editorial anyway. If you want a visible "next step" gesture, prefer `запись · @handle` or `more · owlway.art/link` in the CTA — the middle dot does the separator work. Don't try to work around this by adding an arrow-capable font; the editorial convention is better than the arrow.

## Files in this skill

- `scripts/generate_carousel.py` — the generator. All layout logic, typography, and palette live here.
- `assets/Lora-Variable.ttf`, `Lora-Italic-Variable.ttf` — title face, with Cyrillic.
- `assets/NotoSans-Regular.ttf`, `NotoSans-Medium.ttf`, `NotoSans-Bold.ttf` — body face, with Cyrillic.
- `references/spec-examples.md` — more JSON spec examples for different use cases.

## Dependencies

Just `Pillow`. On the user's Mac: `pip install Pillow` (or `pip3`). No system font installation needed — fonts are bundled in `assets/`.
