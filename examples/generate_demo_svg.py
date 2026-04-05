#!/usr/bin/env python3
"""Generate an animated SVG terminal demo for README.

Creates a fake terminal recording as SVG with CSS animations.
No external tools needed — pure Python output.

Usage:
    python examples/generate_demo_svg.py > docs/demo.svg
"""

from __future__ import annotations

import html


def _escape(text: str) -> str:
    return html.escape(text)


# Each frame: (delay_ms, lines_to_add)
# Simulates a real pipepost run with realistic output
FRAMES: list[tuple[int, list[tuple[str, str]]]] = [
    # Frame 0: command
    (0, [
        ("#8be9fd", "$ pipepost run default --source hackernews --batch -n 3 --lang ru"),
    ]),
    # Frame 1: dedup
    (800, [
        ("#bd93f9", ""),
        ("#bd93f9", "  💾  Dedup  loading published URLs"),
        ("#6272a4", "     12 URLs in database"),
    ]),
    # Frame 2: scout
    (600, [
        ("#bd93f9", ""),
        ("#bd93f9", "  📡  Scout  HackerNews top stories"),
        ("#6272a4", "     5 candidates in 1.2s"),
        ("#f8f8f2", "     > \x1b[33m  453\x1b[0m  The threat is comfortable drift toward not understanding"),
        ("#f8f8f2", "     > \x1b[33m  274\x1b[0m  A Claude Code skill that makes Claude talk like a caveman"),
        ("#f8f8f2", "     > \x1b[33m  215\x1b[0m  Someone at BrowserStack is leaking users' email address"),
    ]),
    # Frame 3: fetch
    (500, [
        ("#bd93f9", ""),
        ("#bd93f9", "  📥  Fetch  downloading articles"),
        ("#6272a4", "     [1] The threat is comfortable drift... (8,421 chars)"),
        ("#6272a4", "     [2] A Claude Code skill... (4,134 chars)"),
        ("#6272a4", "     [3] Someone at BrowserStack... (3,890 chars)"),
        ("#6272a4", "     Formatting: headings=True code=True links=True images=True"),
    ]),
    # Frame 4: translate
    (500, [
        ("#bd93f9", ""),
        ("#bd93f9", "  🌍  Translate  via deepseek-reasoner"),
        ("#6272a4", "     Translating 3 articles..."),
    ]),
    # Frame 5: translate done
    (3000, [
        ("#50fa7b", '     [1] "Угроза — комфортный дрейф к непониманию"'),
        ("#50fa7b", '     [2] "Навык Claude Code: говори как пещерный человек"'),
        ("#50fa7b", '     [3] "Утечка email-адресов в BrowserStack"'),
        ("#6272a4", "     Done in 14.2s"),
    ]),
    # Frame 6: validate
    (400, [
        ("#bd93f9", ""),
        ("#bd93f9", "  ✅  Validate  quality checks"),
        ("#6272a4", "     3/3 passed (ratio > 80%, length > 200 chars)"),
    ]),
    # Frame 7: publish
    (400, [
        ("#bd93f9", ""),
        ("#bd93f9", "  📝  Publish  saving markdown files"),
        ("#50fa7b", "     [1] 2026-04-05-ugroza-komfortnyy-dreyf  ✓"),
        ("#50fa7b", "     [2] 2026-04-05-navyk-claude-code        ✓"),
        ("#50fa7b", "     [3] 2026-04-05-utechka-email-adresov    ✓"),
    ]),
    # Frame 8: done
    (500, [
        ("#50fa7b", ""),
        ("#50fa7b", "  ══════════════════════════════════════════════════"),
        ("#50fa7b", "  Pipeline complete! 3 articles published in 18.4s"),
        ("#50fa7b", "  ══════════════════════════════════════════════════"),
        ("#6272a4", ""),
    ]),
]

FONT_SIZE = 14
LINE_HEIGHT = 20
CHAR_WIDTH = 8.4
PADDING_X = 16
PADDING_Y = 50
TERMINAL_WIDTH = 720
BG_COLOR = "#282a36"
TITLE_COLOR = "#f8f8f2"
DOT_COLORS = ["#ff5555", "#f1fa8c", "#50fa7b"]


def generate_svg() -> str:
    # Calculate total lines and timing
    all_lines: list[tuple[int, str, str]] = []  # (appear_at_ms, color, text)
    current_time = 0
    for delay, lines in FRAMES:
        current_time += delay
        for color, text in lines:
            all_lines.append((current_time, color, text))
            current_time += 80  # stagger lines within a frame

    total_lines = len(all_lines)
    height = PADDING_Y + total_lines * LINE_HEIGHT + 20

    # Build SVG
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TERMINAL_WIDTH} {height}" '
        f'width="{TERMINAL_WIDTH}" height="{height}">',
        "<style>",
        f'  @font-face {{ font-family: "mono"; src: local("SF Mono"), local("Menlo"), '
        f'local("Consolas"), local("DejaVu Sans Mono"); }}',
        f"  .terminal {{ font-family: mono, monospace; font-size: {FONT_SIZE}px; }}",
        f"  .line {{ opacity: 0; animation: fadeIn 0.15s ease-in forwards; }}",
        "  @keyframes fadeIn { to { opacity: 1; } }",
        "</style>",
        # Background
        f'<rect width="{TERMINAL_WIDTH}" height="{height}" rx="8" fill="{BG_COLOR}"/>',
        # Title bar dots
    ]

    for i, color in enumerate(DOT_COLORS):
        cx = 20 + i * 20
        svg_lines.append(f'<circle cx="{cx}" cy="16" r="6" fill="{color}"/>')

    # Title
    svg_lines.append(
        f'<text x="{TERMINAL_WIDTH // 2}" y="20" text-anchor="middle" '
        f'fill="{TITLE_COLOR}" font-family="mono, monospace" font-size="12">'
        f"pipepost demo</text>"
    )

    # Content lines
    svg_lines.append(f'<g class="terminal">')
    for i, (appear_ms, color, text) in enumerate(all_lines):
        y = PADDING_Y + i * LINE_HEIGHT
        delay_s = appear_ms / 1000
        escaped = _escape(text)
        svg_lines.append(
            f'  <text x="{PADDING_X}" y="{y}" fill="{color}" '
            f'class="line" style="animation-delay: {delay_s:.2f}s">'
            f"{escaped}</text>"
        )
    svg_lines.append("</g>")
    svg_lines.append("</svg>")

    return "\n".join(svg_lines)


if __name__ == "__main__":
    print(generate_svg())
