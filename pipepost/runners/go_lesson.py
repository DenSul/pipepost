"""Go Lesson standalone runner — generates Go programming lessons via LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

import httpx
import litellm

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000/api"

PROGRESSION = [
    "Variables and Types",
    "Functions",
    "Control Flow (if/switch/for)",
    "Arrays and Slices",
    "Maps",
    "Structs",
    "Methods",
    "Interfaces",
    "Error Handling",
    "Goroutines",
    "Channels",
    "Select Statement",
    "Sync Package (Mutex, WaitGroup)",
    "Context Package",
    "Testing",
    "HTTP Server",
    "JSON Handling",
    "File I/O",
    "Database (sql package)",
    "Generics",
    "Design Patterns in Go",
]

_PROGRESSION_LIST = "\n".join(f"   {i + 1}. {t}" for i, t in enumerate(PROGRESSION))


# ── Helpers ───────────────────────────────────────────────────────────


async def _fetch_existing_lessons(client: httpx.AsyncClient) -> list[str]:
    """Fetch titles of existing Go lessons from the API."""
    try:
        r = await client.get(f"{API_BASE_URL}/go-lessons", params={"limit": 50}, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(items, list):
            return [item.get("title", "") for item in items if item.get("title")]
        return []
    except Exception as exc:
        logger.warning("Failed to fetch existing lessons: %s", exc)
        return []


def _determine_next_topic(existing_titles: list[str]) -> str | None:
    """Pick the first topic from PROGRESSION not covered by existing titles."""
    existing_lower = [t.lower() for t in existing_titles]
    for topic in PROGRESSION:
        topic_lower = topic.lower()
        if any(topic_lower in title for title in existing_lower):
            continue
        return topic
    return None


def _extract_outermost_json(text: str) -> str | None:
    """Extract the outermost JSON object using brace matching."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _parse_lesson_output(raw: str) -> dict[str, Any] | None:
    """Parse LLM output into a lesson dict."""
    candidate = _extract_outermost_json(raw)
    if candidate:
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and data.get("title"):
                return data
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed: %s", exc)

    logger.error("Failed to parse lesson output. First 500 chars: %s", raw[:500])
    return None


async def _log_cron(
    client: httpx.AsyncClient, status: str, message: str
) -> None:
    """Log a cron result to the API."""
    try:
        await client.post(
            f"{API_BASE_URL}/cron-log",
            json={"job": "go-lesson", "status": status, "message": message},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Failed to log cron: %s", exc)


# ── LLM generation ───────────────────────────────────────────────────


def _build_prompt(next_topic: str, existing_titles: list[str]) -> str:
    existing_text = (
        "\n".join(f"- {t}" for t in existing_titles)
        if existing_titles
        else "(none yet)"
    )

    return (
        "Create 1 Go programming lesson.\n\n"
        "Topic progression (in order):\n"
        f"{_PROGRESSION_LIST}\n\n"
        f"Already covered lessons:\n{existing_text}\n\n"
        f"NEXT TOPIC TO WRITE: **{next_topic}**\n\n"
        "Write a full lesson including:\n"
        "- Theoretical explanation of the concept\n"
        "- 2-3 complete, runnable Go code examples\n"
        "- Common mistakes and pitfalls\n"
        "- A practice exercise for the reader\n\n"
        "Output a JSON object:\n"
        '{"title": "Go Lesson: Topic Name", '
        '"content": "Full lesson in English (markdown)", '
        '"titleRu": "Урок Go: Название темы", '
        '"contentRu": "Full lesson in Russian (markdown)", '
        '"tags": ["go", "programming", ...], '
        '"difficulty": "beginner|intermediate|advanced"}\n\n'
        "Code examples must be in Go. Technical terms stay in English."
    )


async def _generate_lesson(next_topic: str, existing_titles: list[str]) -> str:
    """Call LLM via litellm to generate a lesson."""
    model = os.getenv("PIPEPOST_MODEL", "openai/deepseek-reasoner")
    api_base = os.getenv("OPENAI_API_BASE")
    api_key = os.getenv("OPENAI_API_KEY")

    prompt = _build_prompt(next_topic, existing_titles)

    response = await litellm.acompletion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an experienced Go developer and educator. "
                    "You follow a structured curriculum from basics to advanced topics. "
                    "Your lessons are practical, include runnable code examples, "
                    "highlight common pitfalls, and always end with a practice exercise. "
                    "Always respond with valid JSON only — no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        api_base=api_base,
        api_key=api_key,
        timeout=300,
    )

    return response.choices[0].message.content or ""


# ── Main entry point ──────────────────────────────────────────────────


async def _run_async() -> None:
    """Async core of the Go Lesson runner."""
    logger.info("=== Go Lesson runner started ===")

    async with httpx.AsyncClient() as client:
        # 1. Fetch existing lessons
        existing_titles = await _fetch_existing_lessons(client)
        logger.info("Found %d existing lessons", len(existing_titles))

        # 2. Determine next topic
        next_topic = _determine_next_topic(existing_titles)
        if not next_topic:
            msg = "All topics covered"
            logger.info(msg)
            await _log_cron(client, "success", msg)
            print(f"✅ go-lesson: {msg}")
            return

        logger.info("Next topic: %s", next_topic)

        # 3. Generate via LLM
        raw_output = await _generate_lesson(next_topic, existing_titles)
        logger.info("LLM finished for topic: %s", next_topic)

        # 4. Parse output
        lesson_data = _parse_lesson_output(raw_output)
        if not lesson_data:
            await _log_cron(client, "error", "Failed to parse LLM output")
            print("❌ go-lesson: failed to parse output")
            return

        # Inject required fields
        topic_idx = PROGRESSION.index(next_topic) if next_topic in PROGRESSION else 0
        lesson_number = topic_idx + 1
        lesson_data.setdefault("lessonNumber", lesson_number)
        lesson_data.setdefault("topic", next_topic)
        lesson_data.setdefault(
            "difficulty",
            "beginner" if lesson_number <= 9 else ("intermediate" if lesson_number <= 16 else "advanced"),
        )

        # 5. Publish
        try:
            r = await client.post(
                f"{API_BASE_URL}/go-lessons",
                json=lesson_data,
                timeout=15,
            )
            r.raise_for_status()
            pub_result = r.json()
            lesson_id = pub_result.get("id", "ok")
            logger.info("Published Go lesson: %s (id: %s)", next_topic, lesson_id)
            await _log_cron(
                client, "success", f"Published '{next_topic}' (id: {lesson_id})"
            )
            print(f"✅ go-lesson: published '{next_topic}'")
        except Exception as exc:
            logger.error("Publish failed: %s", exc)
            await _log_cron(client, "error", f"Publish failed: {exc}")
            print(f"❌ go-lesson: publish failed — {exc}")

    logger.info("=== Go Lesson runner finished ===")


def run() -> None:
    """Synchronous entry point for the Go Lesson runner."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    asyncio.run(_run_async())
