"""Process import queue — fetch, translate and publish pending articles."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx
import litellm
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify


logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api"
USER_AGENT = "Mozilla/5.0 (compatible; PipePost/1.0)"
MAX_CONTENT_CHARS = 15_000


async def _get_pending(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """GET /api/import-queue?status=pending&limit=5."""
    resp = await client.get(
        f"{API_BASE_URL}/import-queue",
        params={"status": "pending", "limit": 5},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    return data if isinstance(data, list) else []


async def _patch_item(
    client: httpx.AsyncClient,
    item_id: str,
    body: dict[str, Any],
) -> None:
    """PATCH /api/import-queue/{id}."""
    try:
        resp = await client.patch(
            f"{API_BASE_URL}/import-queue/{item_id}",
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("PATCH queue item %s failed: %s", item_id, exc)


async def _publish_post(client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /api/posts/auto-publish."""
    resp = await client.post(
        f"{API_BASE_URL}/posts/auto-publish",
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    result: dict[str, Any] = resp.json()
    return result


async def _log_cron(
    client: httpx.AsyncClient,
    name: str,
    status: str,
    details: str,
) -> None:
    """POST /api/cron-log."""
    try:
        await client.post(
            f"{API_BASE_URL}/cron-log",
            json={"name": name, "status": status, "details": details},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Cron log failed: %s", exc)


def _fetch_and_parse(html: str) -> tuple[str, str | None]:
    """Extract markdown content and og:image from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # og:image
    cover: str | None = None
    for attr in ("property", "name"):
        tag = soup.find("meta", attrs={attr: "og:image"})
        if isinstance(tag, Tag):
            content_val = tag.get("content")
            if isinstance(content_val, str):
                cover = content_val
                break

    # Remove nav/header/footer/aside noise
    for el in soup.find_all(["nav", "header", "footer", "aside", "script", "style"]):
        el.decompose()

    # Try <article> first, fall back to <main>, then <body>
    main = soup.find("article") or soup.find("main") or soup.find("body")
    raw_html = str(main) if main else str(soup)

    md: str = markdownify(raw_html, heading_style="ATX", strip=["img"])
    # Collapse excessive whitespace
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md[:MAX_CONTENT_CHARS], cover


async def _fetch_article(client: httpx.AsyncClient, url: str) -> tuple[str, str | None]:
    """Fetch URL and return (markdown_content, cover_image_url)."""
    resp = await client.get(
        url,
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return _fetch_and_parse(resp.text)


def _parse_marker_response(raw: str, original_content: str) -> dict[str, Any] | None:
    """Parse ===SECTION=== marker-delimited LLM response."""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    parts = re.split(r"===([A-Z_]+)===", raw)
    sections: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        sections[parts[i]] = parts[i + 1].strip()

    if "CONTENT_RU" not in sections:
        return None

    tags_raw = sections.get("TAGS", "")
    tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    if not tags:
        tags = ["tech"]

    return {
        "title": sections.get("TITLE", ""),
        "titleRu": sections.get("TITLE_RU", ""),
        "content": original_content,
        "contentRu": sections["CONTENT_RU"],
        "tags": tags,
    }


async def _translate(
    content: str,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict[str, Any] | None:
    """Translate article content via LLM. Returns parsed dict or None."""
    content_len = len(content)
    min_translation = max(500, int(content_len * 0.8))

    prompt = (
        "Translate this article to Russian.\n\n"
        f"Article content:\n{content}\n\n"
        "Rules:\n"
        "1. Translate the FULL article paragraph by paragraph. NOT a summary.\n"
        f"2. Translation MUST be ≥{min_translation} chars (original is {content_len} chars).\n"
        "3. Keep all markdown, code blocks, links.\n"
        "4. Technical terms stay in English.\n"
        "5. Natural Russian.\n"
        "6. Choose 3-5 tags (lowercase, english).\n\n"
        "Output format:\n\n"
        "===TITLE===\nEnglish title\n"
        "===TITLE_RU===\nRussian title\n"
        "===CONTENT_RU===\nFull Russian translation in markdown\n"
        "===TAGS===\ntag1, tag2, tag3"
    )

    response = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16384,
        api_base=api_base,
        api_key=api_key,
    )
    text = response.choices[0].message.content or ""
    return _parse_marker_response(text, content)


async def _process_one(
    client: httpx.AsyncClient,
    item: dict[str, Any],
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> bool:
    """Process a single queue item: fetch → translate → publish."""
    url = item.get("url") or item.get("sourceUrl", "")
    item_id = str(item["id"])
    source_name = item.get("sourceName") or item.get("source", "")

    logger.info("Processing: %s", url)
    await _patch_item(client, item_id, {"status": "processing"})

    # 1. Fetch article
    try:
        content, cover = await _fetch_article(client, url)
    except Exception as exc:
        error = f"Fetch failed: {exc}"
        logger.warning(error)
        await _patch_item(client, item_id, {"status": "error", "error": error[:500]})
        return False

    if len(content) < 500:
        await _patch_item(
            client,
            item_id,
            {"status": "error", "error": "Article too short"},
        )
        return False

    # 2. Translate via LLM
    try:
        data = await _translate(content, model, api_base, api_key)
    except Exception as exc:
        error = f"Translation failed: {exc}"
        logger.warning(error)
        await _patch_item(client, item_id, {"status": "error", "error": error[:500]})
        return False

    if not data:
        await _patch_item(
            client,
            item_id,
            {"status": "error", "error": "Failed to parse LLM response"},
        )
        return False

    # 3. Publish
    payload: dict[str, Any] = {
        "title": data["title"],
        "titleRu": data["titleRu"],
        "content": data["content"],
        "contentRu": data["contentRu"],
        "sourceUrl": url,
        "sourceName": source_name,
        "coverImage": cover,
        "tags": data["tags"],
    }

    try:
        result = await _publish_post(client, payload)
        slug = result.get("slug", "")
        await _patch_item(client, item_id, {"status": "published", "slug": slug})
        logger.info("Published: %s → %s", data.get("titleRu", ""), slug)
        return True
    except Exception as exc:
        error = f"Publish failed: {exc}"
        logger.warning(error)
        await _patch_item(client, item_id, {"status": "error", "error": error[:500]})
        return False


async def _run_async() -> None:
    """Core async logic."""
    model = os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")

    logger.info("=== Process Queue runner started ===")
    logger.info("Model: %s, api_base: %s", model, api_base or "(default)")

    async with httpx.AsyncClient() as client:
        pending = await _get_pending(client)
        if not pending:
            logger.info("No pending items in queue.")
            await _log_cron(client, "process-queue", "success", "No pending items")
            print("✅ process-queue: nothing to process")
            return

        logger.info("Found %d pending items", len(pending))
        published = 0
        errors = 0

        for item in pending:
            if await _process_one(client, item, model, api_base, api_key):
                published += 1
            else:
                errors += 1

        details = f"Published {published}, errors {errors}"
        await _log_cron(client, "process-queue", "success", details)
        logger.info("=== Process Queue runner finished ===")
        print(f"✅ process-queue: {details}")


def run() -> None:
    """Sync entry point for CLI integration."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except ImportError:
        pass
    asyncio.run(_run_async())
