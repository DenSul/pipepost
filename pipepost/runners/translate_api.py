"""Translate runner for AI Craft API — HN, Trends, Anime (batched)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

import httpx
import litellm


logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api"
BATCH_SIZE = 10


def _extract_json(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


def _llm_config() -> tuple[str, str | None, str | None]:
    """Return (model, api_base, api_key) from env."""
    model = os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")
    return model, api_base, api_key


async def _log_cron(client: httpx.AsyncClient, name: str, status: str, details: str) -> None:
    """POST cron log entry."""
    try:
        await client.post(
            f"{API_BASE_URL}/cron-log",
            json={"name": name, "status": status, "details": details},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Failed to log cron: %s", exc)


# ---------------------------------------------------------------------------
# HackerNews
# ---------------------------------------------------------------------------


async def _translate_hn_batch(
    stories: list[dict],
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict[str, str]:
    """Translate HN titles batch. Returns {id: titleRu}."""
    items = [f"{i + 1}. id={s['id']}, title={s['title']}" for i, s in enumerate(stories)]
    prompt = (
        "Translate these HackerNews story titles to Russian. "
        "Keep them concise and natural.\n\n"
        + "\n".join(items)
        + '\n\nReply with a JSON array:\n[{"id": "...", "titleRu": "..."}, ...]'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            api_base=api_base,
            api_key=api_key,
        )
        parsed = json.loads(_extract_json(resp.choices[0].message.content or ""))
        if isinstance(parsed, list):
            return {str(e["id"]): e["titleRu"] for e in parsed if e.get("id") and e.get("titleRu")}
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("HN batch parse failed: %s", exc)
    except Exception as exc:
        logger.error("HN batch LLM call failed: %s", exc)
    return {}


async def _translate_hn_single(
    story: dict,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> str | None:
    """Fallback: translate a single HN title."""
    prompt = (
        "Translate this HackerNews story title to Russian. "
        f"Keep it concise and natural.\n\nTitle: {story['title']}\n\n"
        'Reply in JSON: {"titleRu": "..."}'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            api_base=api_base,
            api_key=api_key,
        )
        data = json.loads(_extract_json(resp.choices[0].message.content or ""))
        return data.get("titleRu")
    except Exception as exc:
        logger.warning("HN single translate failed for %s: %s", story["id"], exc)
        return None


async def translate_hackernews() -> int:
    """Translate untranslated HN stories. Returns count."""
    model, api_base, api_key = _llm_config()
    logger.info("=== translate-hn started (model: %s) ===", model)

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE_URL}/widgets/hackernews", timeout=30)
        resp.raise_for_status()
        stories = resp.json().get("stories", [])
        untranslated = [s for s in stories if not s.get("titleRu")]

        if not untranslated:
            logger.info("All HN stories already translated.")
            await _log_cron(client, "translate-hn", "success", "Nothing to translate")
            print("✅ translate-hn: nothing to translate")
            return 0

        logger.info("Found %d untranslated HN stories", len(untranslated))
        translations: list[dict] = []

        for i in range(0, len(untranslated), BATCH_SIZE):
            batch = untranslated[i : i + BATCH_SIZE]
            results = await _translate_hn_batch(batch, model, api_base, api_key)

            for s in batch:
                title_ru = results.get(str(s["id"]))
                if not title_ru:
                    title_ru = await _translate_hn_single(s, model, api_base, api_key)
                if title_ru:
                    translations.append({"id": s["id"], "titleRu": title_ru})

        if translations:
            patch = await client.patch(
                f"{API_BASE_URL}/widgets/hackernews/translate",
                json={"translations": translations},
                timeout=30,
            )
            patch.raise_for_status()

        await _log_cron(
            client,
            "translate-hn",
            "success",
            f"Translated {len(translations)}/{len(untranslated)} stories",
        )
        logger.info("=== translate-hn finished ===")
        print(f"✅ translate-hn: translated {len(translations)}/{len(untranslated)} stories")
        return len(translations)


# ---------------------------------------------------------------------------
# GitHub Trends
# ---------------------------------------------------------------------------


async def _translate_trends_batch(
    trends: list[dict],
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict[str, dict]:
    """Translate trends batch. Returns {id: {descriptionRu, trendAnalysis}}."""
    items = [
        f"{i + 1}. id={t['id']}, repo={t['repoName']}, "
        f"desc={t.get('description', 'N/A')}, starsToday={t.get('starsToday', 0)}"
        for i, t in enumerate(trends)
    ]
    prompt = (
        "Translate these GitHub repo descriptions to Russian (2-3 sentences each) "
        "and explain why each is trending (1 sentence).\n\n"
        + "\n".join(items)
        + "\n\nReply with a JSON array:\n"
        '[{"id": "...", "descriptionRu": "...", "trendAnalysis": "..."}, ...]'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            api_base=api_base,
            api_key=api_key,
        )
        parsed = json.loads(_extract_json(resp.choices[0].message.content or ""))
        if isinstance(parsed, list):
            return {
                str(e["id"]): {
                    "descriptionRu": e.get("descriptionRu", ""),
                    "trendAnalysis": e.get("trendAnalysis", ""),
                }
                for e in parsed
                if e.get("id") and e.get("descriptionRu")
            }
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Trends batch parse failed: %s", exc)
    except Exception as exc:
        logger.error("Trends batch LLM call failed: %s", exc)
    return {}


async def _translate_trends_single(
    trend: dict,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict | None:
    """Fallback: translate a single trend."""
    prompt = (
        "Translate this GitHub repo description to Russian (2-3 sentences) "
        "and explain why it's trending (1 sentence).\n\n"
        f"Repo: {trend['repoName']}\n"
        f"Description: {trend.get('description', 'N/A')}\n"
        f"Stars today: {trend.get('starsToday', 0)}\n\n"
        'Reply in JSON: {"descriptionRu": "...", "trendAnalysis": "..."}'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            api_base=api_base,
            api_key=api_key,
        )
        data = json.loads(_extract_json(resp.choices[0].message.content or ""))
        if data.get("descriptionRu"):
            return data
    except Exception as exc:
        logger.warning("Trends single translate failed for %s: %s", trend["repoName"], exc)
    return None


async def translate_trends() -> int:
    """Translate untranslated GitHub trends. Returns count."""
    model, api_base, api_key = _llm_config()
    logger.info("=== translate-trends started (model: %s) ===", model)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/github-trends",
            params={"limit": 25},
            timeout=30,
        )
        resp.raise_for_status()
        trends = resp.json().get("data", [])
        untranslated = [t for t in trends if not t.get("descriptionRu")]

        if not untranslated:
            logger.info("All trends already translated.")
            await _log_cron(client, "translate-trends", "success", "Nothing to translate")
            print("✅ translate-trends: nothing to translate")
            return 0

        logger.info("Found %d untranslated trends", len(untranslated))
        updates: list[dict] = []

        for i in range(0, len(untranslated), BATCH_SIZE):
            batch = untranslated[i : i + BATCH_SIZE]
            results = await _translate_trends_batch(batch, model, api_base, api_key)

            for t in batch:
                item = results.get(str(t["id"]))
                if not item:
                    item = await _translate_trends_single(t, model, api_base, api_key)
                if item:
                    updates.append(
                        {
                            "id": t["id"],
                            "descriptionRu": item.get("descriptionRu", ""),
                            "trendAnalysis": item.get("trendAnalysis", ""),
                        }
                    )

        if updates:
            patch = await client.patch(
                f"{API_BASE_URL}/github-trends/bulk",
                json={"updates": updates},
                timeout=30,
            )
            patch.raise_for_status()

        await _log_cron(
            client,
            "translate-trends",
            "success",
            f"Translated {len(updates)}/{len(untranslated)} trends",
        )
        logger.info("=== translate-trends finished ===")
        print(f"✅ translate-trends: translated {len(updates)}/{len(untranslated)} trends")
        return len(updates)


# ---------------------------------------------------------------------------
# Anime
# ---------------------------------------------------------------------------


async def _translate_anime_batch(
    anime_list: list[dict],
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict[str, dict]:
    """Translate anime batch. Returns {id: {titleRu, synopsisRu}}."""
    items = [
        f"{i + 1}. id={a['id']}, title={a['title']}, synopsis={(a.get('synopsis') or '')[:500]}"
        for i, a in enumerate(anime_list)
    ]
    prompt = (
        "Translate these anime titles and synopses to Russian.\n"
        "titleRu: creative Russian translation. synopsisRu: 2-4 sentence summary.\n\n"
        + "\n".join(items)
        + "\n\nReply with a JSON array:\n"
        '[{"id": "...", "titleRu": "...", "synopsisRu": "..."}, ...]'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            api_base=api_base,
            api_key=api_key,
        )
        parsed = json.loads(_extract_json(resp.choices[0].message.content or ""))
        if isinstance(parsed, list):
            return {
                str(e["id"]): {
                    "titleRu": e.get("titleRu", ""),
                    "synopsisRu": e.get("synopsisRu", ""),
                }
                for e in parsed
                if e.get("id") and e.get("synopsisRu")
            }
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Anime batch parse failed: %s", exc)
    except Exception as exc:
        logger.error("Anime batch LLM call failed: %s", exc)
    return {}


async def _translate_anime_single(
    anime: dict,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict | None:
    """Fallback: translate a single anime."""
    synopsis = (anime.get("synopsis") or "")[:500]
    prompt = (
        "Translate this anime title and synopsis to Russian.\n\n"
        f"Title: {anime['title']}\nSynopsis: {synopsis}\n\n"
        'Reply in JSON: {"titleRu": "...", "synopsisRu": "..."}'
    )
    try:
        resp = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            api_base=api_base,
            api_key=api_key,
        )
        data = json.loads(_extract_json(resp.choices[0].message.content or ""))
        if data.get("synopsisRu"):
            return data
    except Exception as exc:
        logger.warning("Anime single translate failed for %s: %s", anime["title"], exc)
    return None


async def translate_anime() -> int:
    """Translate untranslated anime releases. Returns count."""
    model, api_base, api_key = _llm_config()
    logger.info("=== translate-anime started (model: %s) ===", model)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/releases/anime",
            params={"limit": 25},
            timeout=30,
        )
        resp.raise_for_status()
        anime_list = resp.json().get("data", [])
        untranslated = [a for a in anime_list if not a.get("synopsisRu")]

        if not untranslated:
            logger.info("All anime already translated.")
            await _log_cron(client, "translate-anime", "success", "Nothing to translate")
            print("✅ translate-anime: nothing to translate")
            return 0

        logger.info("Found %d untranslated anime", len(untranslated))
        updates: list[dict] = []

        for i in range(0, len(untranslated), BATCH_SIZE):
            batch = untranslated[i : i + BATCH_SIZE]
            results = await _translate_anime_batch(batch, model, api_base, api_key)

            for a in batch:
                item = results.get(str(a["id"]))
                if not item:
                    item = await _translate_anime_single(a, model, api_base, api_key)
                if item:
                    updates.append(
                        {
                            "id": a["id"],
                            "titleRu": item.get("titleRu", ""),
                            "synopsisRu": item.get("synopsisRu", ""),
                        }
                    )

        if updates:
            patch = await client.patch(
                f"{API_BASE_URL}/releases/anime/bulk-translate",
                json={"updates": updates},
                timeout=30,
            )
            patch.raise_for_status()

        await _log_cron(
            client,
            "translate-anime",
            "success",
            f"Translated {len(updates)}/{len(untranslated)} anime",
        )
        logger.info("=== translate-anime finished ===")
        print(f"✅ translate-anime: translated {len(updates)}/{len(untranslated)} anime")
        return len(updates)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_TARGETS = {
    "hn": translate_hackernews,
    "trends": translate_trends,
    "anime": translate_anime,
}


def run(target: str = "hn") -> None:
    """Sync entry point for CLI integration."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except ImportError:
        pass

    fn = _TARGETS.get(target)
    if not fn:
        available = ", ".join(_TARGETS)
        raise ValueError(f"Unknown target: {target}. Available: {available}")

    asyncio.run(fn())
