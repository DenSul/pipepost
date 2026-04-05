#!/usr/bin/env python3
"""Generate an animated GIF terminal demo for README.

Usage:
    python examples/generate_demo_gif.py
    # Output: docs/demo.gif
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Terminal dimensions
WIDTH = 820
LINE_H = 22
PAD_X = 18
PAD_Y = 48
BG = (40, 42, 54)  # Dracula background
DOTS = [(255, 85, 85), (241, 250, 140), (80, 250, 123)]

# Colors
WHITE = (248, 248, 242)
GRAY = (98, 114, 164)
PURPLE = (189, 147, 249)
GREEN = (80, 250, 123)
YELLOW = (241, 250, 140)
CYAN = (139, 233, 253)
RED = (255, 85, 85)

# Frames: list of (lines_so_far, duration_ms)
# Each line: (color, text)
SCRIPT: list[tuple[tuple[int, int, int], str]] = [
    (CYAN, "$ pipepost run default --source hackernews --batch -n 3 --lang ru"),
    (WHITE, ""),
    (PURPLE, "  \U0001f4be  Dedup  loading published URLs"),
    (GRAY, "     12 URLs in database"),
    (WHITE, ""),
    (PURPLE, "  \U0001f4e1  Scout  HackerNews top stories"),
    (GRAY, "     5 candidates in 1.2s"),
    (WHITE, "     >  453  The threat is comfortable drift toward not understanding"),
    (WHITE, "     >  274  A Claude Code skill that makes Claude talk like a caveman"),
    (WHITE, "     >  215  Someone at BrowserStack is leaking users' email address"),
    (WHITE, ""),
    (PURPLE, "  \U0001f4e5  Fetch  downloading articles"),
    (GRAY, "     [1] The threat is comfortable drift... (8,421 chars)"),
    (GRAY, "     [2] A Claude Code skill... (4,134 chars)"),
    (GRAY, "     [3] Someone at BrowserStack... (3,890 chars)"),
    (GRAY, "     Formatting: headings=True code=True links=True images=True"),
    (WHITE, ""),
    (PURPLE, "  \U0001f30d  Translate  via deepseek-reasoner"),
    (GRAY, "     Translating 3 articles..."),
    (GREEN, '     [1] "Угроза \u2014 комфортный дрейф к непониманию"'),
    (GREEN, '     [2] "Навык Claude Code: говори как пещерный человек"'),
    (GREEN, '     [3] "Утечка email-адресов в BrowserStack"'),
    (GRAY, "     Done in 14.2s"),
    (WHITE, ""),
    (PURPLE, "  \u2705  Validate  quality checks"),
    (GRAY, "     3/3 passed (ratio > 80%, length > 200 chars)"),
    (WHITE, ""),
    (PURPLE, "  \U0001f4dd  Publish  saving markdown files"),
    (GREEN, "     [1] 2026-04-05-ugroza-komfortnyy-dreyf   ok"),
    (GREEN, "     [2] 2026-04-05-navyk-claude-code          ok"),
    (GREEN, "     [3] 2026-04-05-utechka-email-adresov      ok"),
    (WHITE, ""),
    (GREEN, "  ════════════════════════════════════════════════════════"),
    (GREEN, "  Pipeline complete! 3 articles published in 18.4s"),
    (GREEN, "  ════════════════════════════════════════════════════════"),
]

# Timing: how many lines to show per frame, and duration
KEYFRAMES: list[tuple[int, int]] = [
    # (lines_visible, duration_ms)
    (1, 600),  # command typed
    (4, 500),  # dedup
    (10, 800),  # scout
    (16, 700),  # fetch
    (19, 1200),  # translate start
    (23, 1000),  # translate results
    (26, 500),  # validate
    (31, 600),  # publish
    (35, 3000),  # done (hold)
]


def _try_load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a monospace font."""
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, AttributeError):
            continue
    return ImageFont.load_default()


def _render_frame(
    lines_visible: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    total_height: int,
) -> Image.Image:
    """Render a single frame of the terminal."""
    visible_lines = SCRIPT[:lines_visible]
    img = Image.new("RGB", (WIDTH, total_height), BG)
    draw = ImageDraw.Draw(img)

    # Title bar
    draw.rounded_rectangle([0, 0, WIDTH, 36], radius=8, fill=(33, 34, 44))
    for i, color in enumerate(DOTS):
        draw.ellipse([14 + i * 22, 10, 26 + i * 22, 22], fill=color)

    # Title text
    title = "pipepost demo"
    bbox = draw.textbbox((0, 0), title, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2, 10), title, fill=GRAY, font=font)

    # Lines
    for i, (color, text) in enumerate(visible_lines):
        y = PAD_Y + i * LINE_H
        # Replace emoji with text markers for font compatibility
        clean = text
        for emoji, repl in [
            ("\U0001f4be", "[DB]"),
            ("\U0001f4e1", "[>>]"),
            ("\U0001f4e5", "[DL]"),
            ("\U0001f30d", "[TR]"),
            ("\u2705", "[OK]"),
            ("\U0001f4dd", "[WR]"),
        ]:
            clean = clean.replace(emoji, repl)
        draw.text((PAD_X, y), clean, fill=color, font=font)

    return img


def main() -> None:
    font = _try_load_font(15)
    total_lines = len(SCRIPT)
    total_height = PAD_Y + total_lines * LINE_H + 16
    frames: list[Image.Image] = []
    durations: list[int] = []

    for lines_visible, duration in KEYFRAMES:
        frame = _render_frame(lines_visible, font, total_height)
        frames.append(frame)
        durations.append(duration)

    out = Path("docs/demo.gif")
    out.parent.mkdir(exist_ok=True)
    frames[0].save(
        out,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = out.stat().st_size / 1024
    print(f"Saved {out} ({size_kb:.0f} KB, {len(frames)} frames, {WIDTH}x{total_height})")


if __name__ == "__main__":
    main()
