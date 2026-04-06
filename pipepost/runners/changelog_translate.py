"""Changelog translation runner — standalone async, no CrewAI."""

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
BATCH_SIZE = 5
FETCH_LIMIT = 50


def _extract_json(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


async def _fetch_untranslated(client: httpx.AsyncClient) -> list[dict]:
    """Fetch changelogs without bodyRu."""
    resp = await client.get(
        f"{API_BASE_URL}/changelogs",
        params={"limit": FETCH_LIMIT},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    data = raw.get("data", raw) if isinstance(raw, dict) else raw
    if not isinstance(data, list):
        return []
    return [
        {
            "id": item["id"],
            "repo": item.get("repo", "unknown"),
            "version": item.get("version", ""),
            "body": (item.get("body") or "")[:3000],
        }
        for item in data
        if not item.get("bodyRu")
    ]


async def _save_translation(client: httpx.AsyncClient, changelog_id: str, body_ru: str) -> bool:
    """PATCH Russian translation for a changelog entry."""
    try:
        resp = await client.patch(
            f"{API_BASE_URL}/changelogs/{changelog_id}",
            json={"bodyRu": body_ru},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Failed to save translation for %s: %s", changelog_id, exc)
        return False


async def _log_cron(client: httpx.AsyncClient, status: str, message: str) -> None:
    """POST cron log entry."""
    try:
        await client.post(
            f"{API_BASE_URL}/cron-log",
            json={
                "job": "changelog-translate",
                "status": status,
                "message": message,
            },
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Failed to log cron: %s", exc)


async def _translate_batch(
    changelogs: list[dict],
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> dict[str, str]:
    """Translate a batch via litellm. Returns {id: bodyRu}."""
    items = []
    for i, cl in enumerate(changelogs):
        items.append(
            f"{i + 1}. id={cl['id']}, repo={cl['repo']} {cl['version']}\n"
            f"   body: {cl['body'][:1500]}"
        )

    prompt = (
        "Translate these open-source changelogs to Russian.\n"
        "For each, create a concise summary: what changed and why it matters.\n"
        "Use markdown, 3-5 bullet points. Keep technical terms in English.\n\n"
        + "\n\n".join(items)
        + "\n\nReply with a JSON array:\n"
        '[{"id": "...", "bodyRu": "markdown summary in Russian"}, ...]'
    )

    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            api_base=api_base,
            api_key=api_key,
        )
        text = response.choices[0].message.content or ""
        parsed = json.loads(_extract_json(text))
        if isinstance(parsed, list):
            result: dict[str, str] = {}
            for entry in parsed:
                cid = str(entry.get("id", ""))
                body = entry.get("bodyRu", "")
                if cid and body:
                    result[cid] = body
            return result
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning("Batch parse failed: %s", exc)
    except Exception as exc:
        logger.error("LLM batch call failed: %s", exc)
    return {}


async def _translate_single(
    changelog: dict,
    model: str,
    api_base: str | None,
    api_key: str | None,
) -> str | None:
    """Translate a single changelog (fallback)."""
    prompt = (
        "Translate this changelog to Russian. "
        "Summarize what changed and why it matters. "
        "Markdown, 3-5 bullet points. Technical terms in English.\n\n"
        f"Repo: {changelog['repo']} {changelog['version']}\n"
        f"Body:\n{changelog['body'][:2000]}\n\n"
        "Reply with ONLY the Russian markdown summary."
    )
    try:
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            api_base=api_base,
            api_key=api_key,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = _extract_json(text)
        return text if len(text) > 20 else None
    except Exception as exc:
        logger.warning("Failed to translate %s: %s", changelog["id"], exc)
        return None


async def _run_async() -> None:
    """Core async logic."""
    model = os.getenv("PIPEPOST_MODEL", "deepseek/deepseek-chat")
    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")

    logger.info("=== Changelog Translate runner started ===")
    logger.info("Model: %s, api_base: %s", model, api_base or "(default)")

    async with httpx.AsyncClient() as client:
        changelogs = await _fetch_untranslated(client)
        if not changelogs:
            logger.info("No untranslated changelogs found.")
            await _log_cron(client, "success", "No untranslated changelogs")
            print("✅ changelog-translate: nothing to translate")
            return

        logger.info("Found %d untranslated changelogs", len(changelogs))
        translated = 0

        for i in range(0, len(changelogs), BATCH_SIZE):
            batch = changelogs[i : i + BATCH_SIZE]
            results = await _translate_batch(batch, model, api_base, api_key)

            for cl in batch:
                body_ru = results.get(str(cl["id"]))
                if not body_ru:
                    body_ru = await _translate_single(cl, model, api_base, api_key)

                if body_ru and await _save_translation(client, cl["id"], body_ru):
                    translated += 1
                    logger.info("Translated: %s %s", cl["repo"], cl["version"])

        await _log_cron(client, "success", f"Translated {translated}/{len(changelogs)} changelogs")
        logger.info("=== Changelog Translate runner finished ===")
        print(f"✅ changelog-translate: translated {translated}/{len(changelogs)} changelogs")


def run() -> None:
    """Sync entry point for CLI integration."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
    except ImportError:
        pass
    asyncio.run(_run_async())
