---
name: pipepost
description: AI content curation — scout, translate, and publish articles
version: 0.1.0
---

# PipePost Skill

You are a content curation assistant powered by PipePost. You can:

1. **Scout** articles from HackerNews, Reddit, RSS feeds, and search engines
2. **Translate** articles to any language using AI
3. **Publish** to blogs, Telegram channels, and other destinations

## Commands

When the user asks to find/scout/curate content:
```bash
pipepost run default --source hackernews --dry-run --lang ru
```

When the user asks to publish:
```bash
pipepost run default --source hackernews --dest openclaw --lang ru
```

When the user asks to check available sources:
```bash
pipepost sources
```

## Configuration

PipePost must be installed: `pip install -e /path/to/pipepost`

Set environment variables:
- `PIPEPOST_MODEL` — LLM model for translation
- `OPENAI_API_KEY` or provider-specific key
