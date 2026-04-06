"""TIL (Today I Learned) runner — standalone async pipeline without CrewAI.

Fetches existing TILs and changelogs from the AI Craft backend,
generates a new TIL via LLM, publishes it, and logs the cron execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
import litellm


logger = logging.getLogger(__name__)

_API_BASE = "http://localhost:8000/api"

_SYSTEM_PROMPT = """\
You are a senior developer who writes TIL (Today I Learned) notes.
A TIL is a short, practical note about something interesting you learned.

Rules:
- Title MUST start with "TIL:"
- Content in English: 200-400 words, include a code example when relevant
- Content in Russian: 200-400 words, a translation of the English version
- Pick a topic from the changelogs or a related interesting dev fact
- Do NOT repeat topics from existing TILs
- Tags: 2-4 lowercase tags
- Difficulty: beginner, intermediate, or advanced
- Include source URL when possible

Respond with ONLY a valid JSON object (no markdown fences):
{
  "title": "TIL: ...",
  "content": "English content with code examples...",
  "titleRu": "TIL: ... (Russian)",
  "contentRu": "Russian content...",
  "tags": ["tag1", "tag2"],
  "source": "Source name",
  "sourceUrl": "https://...",
  "difficulty": "intermediate"
}
"""


async def _fetch_existing_tils(client: httpx.AsyncClient, limit: int = 20) -> list[dict]:
    """Fetch existing TIL titles from the backend."""
    try:
        resp = await client.get(f"{_API_BASE}/tils", params={"limit": limit})
        resp.raise_for_status()
        raw = resp.json()
        data = raw.get("data", raw) if isinstance(raw, dict) else raw
        return data if isinstance(data, list) else []
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch existing TILs: %s", exc)
        return []


async def _fetch_changelogs(client: httpx.AsyncClient, limit: int = 10) -> list[dict]:
    """Fetch recent changelogs for inspiration."""
    try:
        resp = await client.get(f"{_API_BASE}/changelogs", params={"limit": limit})
        resp.raise_for_status()
        raw = resp.json()
        data = raw.get("data", raw) if isinstance(raw, dict) else raw
        return data if isinstance(data, list) else []
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch changelogs: %s", exc)
        return []


def _build_user_prompt(existing_tils: list[dict], changelogs: list[dict]) -> str:
    """Build the user prompt with context about existing TILs and changelogs."""
    parts: list[str] = []

    if existing_tils:
        titles = [t.get("title", "") for t in existing_tils if t.get("title")]
        parts.append("EXISTING TILs (do NOT repeat these topics):")
        for title in titles:
            parts.append(f"  - {title}")
        parts.append("")

    if changelogs:
        parts.append("RECENT CHANGELOGS (use as inspiration):")
        for entry in changelogs:
            repo = entry.get("repo", "unknown")
            version = entry.get("version", "")
            body = (entry.get("body") or "")[:300]
            parts.append(f"  - {repo} {version}: {body}")
        parts.append("")

    parts.append(
        "Based on the changelogs above (or a related interesting dev topic), "
        "create 1 new TIL note. Make it practical and include a code example."
    )

    return "\n".join(parts)


async def _generate_til(
    existing_tils: list[dict],
    changelogs: list[dict],
) -> dict:
    """Generate a TIL using LLM via litellm."""
    model = os.getenv("PIPEPOST_MODEL", "openai/deepseek-reasoner")
    api_base = os.getenv("OPENAI_API_BASE", "")
    api_key = os.getenv("OPENAI_API_KEY", "")

    user_prompt = _build_user_prompt(existing_tils, changelogs)

    logger.info("Generating TIL with model=%s", model)

    response = await litellm.acompletion(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        api_base=api_base,
        api_key=api_key,
        temperature=0.8,
        max_tokens=4096,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [ln for ln in lines if not ln.startswith("```")]
        content = "\n".join(lines).strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("LLM returned invalid JSON: %s", content[:500])
        raise ValueError(f"Failed to parse LLM response as JSON: {exc}") from exc


async def _publish_til(client: httpx.AsyncClient, til_data: dict) -> dict:
    """Publish the TIL to the backend."""
    required = ["title", "content", "titleRu", "contentRu"]
    missing = [f for f in required if not til_data.get(f)]
    if missing:
        raise ValueError(f"Missing required TIL fields: {', '.join(missing)}")

    resp = await client.post(f"{_API_BASE}/tils", json=til_data, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def _log_cron(
    client: httpx.AsyncClient,
    name: str,
    status: str,
    details: str | None = None,
) -> None:
    """Log the cron execution result."""
    payload: dict[str, str] = {"name": name, "status": status}
    if details:
        payload["details"] = details
    try:
        resp = await client.post(f"{_API_BASE}/cron-log", json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Cron logged: %s %s", name, status)
    except httpx.HTTPError as exc:
        logger.warning("Failed to log cron: %s", exc)


async def run_til() -> None:
    """Main async entry point for the TIL runner."""
    logger.info("=== TIL runner started ===")

    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Fetch existing TILs for dedup
        existing_tils = await _fetch_existing_tils(client, limit=20)
        logger.info("Fetched %d existing TILs", len(existing_tils))

        # 2. Fetch changelogs for inspiration
        changelogs = await _fetch_changelogs(client, limit=10)
        logger.info("Fetched %d changelogs", len(changelogs))

        # 3. Generate TIL via LLM
        try:
            til_data = await _generate_til(existing_tils, changelogs)
            logger.info("Generated TIL: %s", til_data.get("title", "unknown"))
        except Exception as exc:
            logger.error("TIL generation failed: %s", exc)
            await _log_cron(client, "til-daily", "error", str(exc))
            raise

        # 4. Publish
        try:
            result = await _publish_til(client, til_data)
            til_id = result.get("id", "ok")
            logger.info("Published TIL, id=%s", til_id)
        except Exception as exc:
            logger.error("TIL publish failed: %s", exc)
            await _log_cron(client, "til-daily", "error", f"Publish failed: {exc}")
            raise

        # 5. Log success
        await _log_cron(
            client,
            "til-daily",
            "success",
            f"Published: {til_data.get('title', '')}",
        )

    logger.info("=== TIL runner finished ===")
    print(f"✅ TIL published: {til_data.get('title', '')}")


def run() -> None:
    """Sync entry point for CLI."""
    asyncio.run(run_til())
