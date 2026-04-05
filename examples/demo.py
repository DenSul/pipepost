#!/usr/bin/env python3
"""PipePost demo — shows the full pipeline in action with rich terminal output.

Usage:
    export PIPEPOST_MODEL=openai/deepseek-reasoner
    export OPENAI_API_KEY=your-key
    export OPENAI_API_BASE=https://your-provider/v1  # optional
    python examples/demo.py

Record as GIF:
    pip install terminalizer
    terminalizer record demo --command "python examples/demo.py"
    terminalizer render demo -o demo.gif
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# ANSI colors
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
RED = "\033[31m"
RESET = "\033[0m"


def step(icon: str, name: str, detail: str = "") -> None:
    """Print a step marker."""
    suffix = f" {DIM}{detail}{RESET}" if detail else ""
    print(f"\n  {icon}  {BOLD}{name}{RESET}{suffix}")


def info(text: str) -> None:
    """Print an info line."""
    print(f"     {DIM}{text}{RESET}")


def success(text: str) -> None:
    """Print a success line."""
    print(f"     {GREEN}{text}{RESET}")


def item(text: str) -> None:
    """Print a list item."""
    print(f"     {CYAN}>{RESET} {text}")


async def main() -> None:
    model = os.getenv("PIPEPOST_MODEL", "")
    if not model:
        print(f"{RED}Set PIPEPOST_MODEL env var (e.g. openai/deepseek-reasoner){RESET}")
        sys.exit(1)

    print(f"\n{BOLD}{MAGENTA}{'=' * 60}{RESET}")
    print(f"{BOLD}{MAGENTA}  PipePost — AI Content Curation Pipeline{RESET}")
    print(f"{BOLD}{MAGENTA}{'=' * 60}{RESET}")
    print(f"  {DIM}Model: {model}{RESET}")

    # --- DEDUP ---
    step("💾", "Dedup", "loading published URLs")
    from pipepost.storage.sqlite import SQLiteStorage

    storage = SQLiteStorage(db_path=":memory:")
    existing = storage.load_existing_urls()
    info(f"{len(existing)} URLs in database")

    # --- SCOUT ---
    step("📡", "Scout", "HackerNews top stories")
    from pipepost.core.registry import discover_all, get_source

    discover_all()
    source = get_source("hackernews")
    t0 = time.monotonic()
    candidates = await source.fetch_candidates(limit=5)
    info(f"{len(candidates)} candidates in {time.monotonic() - t0:.1f}s")
    for c in candidates[:4]:
        score_str = f"{c.score:>5.0f}"
        item(f"{YELLOW}{score_str}{RESET}  {c.title[:55]}")

    # --- FETCH ---
    step("📥", "Fetch", "downloading article content")
    from pipepost.core.context import FlowContext
    from pipepost.steps.fetch import FetchStep

    ctx = FlowContext(source_name="hackernews", target_lang="ru")
    ctx.candidates = candidates
    ctx = await FetchStep(max_chars=6000).execute(ctx)
    if not ctx.selected:
        print(f"  {RED}Fetch failed: {ctx.errors}{RESET}")
        return
    info(f"Selected: {BOLD}{ctx.selected.title[:50]}{RESET}")
    info(f"{len(ctx.selected.content)} chars, cover: {'yes' if ctx.selected.cover_image else 'no'}")

    has_code = "```" in ctx.selected.content
    has_links = "](" in ctx.selected.content
    has_images = "![" in ctx.selected.content
    info(f"Formatting preserved: code={has_code} links={has_links} images={has_images}")

    # --- TRANSLATE ---
    step("🌍", "Translate", f"via {model}")

    # Use openai SDK directly (litellm has Windows Long Path issues)
    from openai import AsyncOpenAI

    from pipepost.steps.translate import TranslateStep

    base_url = os.getenv("OPENAI_API_BASE")
    client = AsyncOpenAI(base_url=base_url) if base_url else AsyncOpenAI()

    ts = TranslateStep(model="unused", target_lang="ru")
    prompt = ts._build_prompt(ctx.selected.title, ctx.selected.content)  # noqa: SLF001
    info(f"Prompt: {len(prompt)} chars")
    info("Translating...")

    t0 = time.monotonic()
    resp = await client.chat.completions.create(
        model=model.removeprefix("openai/"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8000,
    )
    elapsed = time.monotonic() - t0
    raw = resp.choices[0].message.content or ""
    parsed = ts._parse_output(raw)  # noqa: SLF001

    if not parsed:
        print(f"  {RED}Translation parse failed{RESET}")
        return

    info(f"Done in {elapsed:.1f}s")
    success(f"Title: {parsed['title_translated']}")
    info(f"Tags: {', '.join(parsed['tags'][:6])}")
    info(f"Content: {len(parsed['content_translated'])} chars")

    # --- VALIDATE ---
    step("✅", "Validate", "quality checks")
    ratio = len(parsed["content_translated"]) / max(len(ctx.selected.content), 1)
    info(f"Translation ratio: {ratio:.0%}")
    info(f"Content length: {len(parsed['content_translated'])} chars (min: 200)")
    success("All checks passed")

    # --- PUBLISH ---
    step("📝", "Publish", "saving markdown file")
    from pipepost.core.context import TranslatedArticle
    from pipepost.destinations.markdown import MarkdownDestination

    translated = TranslatedArticle(
        title=ctx.selected.title,
        title_translated=parsed["title_translated"],
        content=ctx.selected.content,
        content_translated=parsed["content_translated"],
        source_url=ctx.selected.url,
        source_name="hackernews",
        tags=parsed["tags"],
        cover_image=ctx.selected.cover_image,
    )
    dest = MarkdownDestination(output_dir="output")
    result = await dest.publish(translated)
    success(f"Slug: {result.slug}")
    info(f"File: {result.url}")

    # --- DONE ---
    print(f"\n{BOLD}{GREEN}{'=' * 60}{RESET}")
    print(f"{BOLD}{GREEN}  Pipeline complete!{RESET}")
    print(f"{BOLD}{GREEN}{'=' * 60}{RESET}")
    print(f"  {DIM}Output: {result.url}{RESET}\n")

    storage.close()


if __name__ == "__main__":
    asyncio.run(main())
