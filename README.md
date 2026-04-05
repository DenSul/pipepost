```
         _                          _
 _ __ (_)_ __   ___ _ __   ___  ___| |_
| '_ \| | '_ \ / _ \ '_ \ / _ \/ __| __|
| |_) | | |_) |  __/ |_) | (_) \__ \ |_
| .__/|_| .__/ \___| .__/ \___/|___/\__|
|_|     |_|        |_|
```

[![CI](https://github.com/densul/pipepost/actions/workflows/ci.yml/badge.svg)](https://github.com/densul/pipepost/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

# PipePost

**Open-source AI content curation pipeline** -- scout, translate, and publish articles from any domain automatically.

PipePost discovers articles from sources like HackerNews, Reddit, RSS feeds, and search engines, translates them to your target language using AI, and publishes to your blog or CMS. Works for any niche -- tech, business, health, lifestyle, and more.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Use Cases](#use-cases)
- [Sources](#sources)
- [Destinations](#destinations)
- [Steps](#steps)
- [Configuration](#configuration)
- [Adding a Custom Source](#adding-a-custom-source)
- [Adding a Custom Destination](#adding-a-custom-destination)
- [Supported LLM Models](#supported-llm-models)
- [Docker](#docker)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Features

- 📡 **Multiple Sources** — HackerNews, Reddit, RSS/Atom, DuckDuckGo search
- 🌍 **AI Translation** — Full paragraph-by-paragraph translation via any LLM (DeepSeek, Claude, GPT, Qwen, etc.)
- 📝 **Multiple Destinations** — Webhook (WordPress, Ghost, custom API), Markdown files
- 🔄 **Composable Flows** — Chain steps: scout → fetch → translate → validate → publish
- 🧩 **Plugin Architecture** — Add sources and destinations with a single file
- ⚙️ **YAML Configuration** — Configure everything without code
- 🐳 **Docker Ready** — `docker compose up` and go

## Quick Start

```bash
# Install
pip install pipepost

# Configure
export PIPEPOST_MODEL=deepseek/deepseek-chat
export OPENAI_API_KEY=your-key

# List available components
pipepost sources
pipepost destinations
pipepost flows

# Run a curation flow
pipepost run curate --source hackernews --dest webhook

# Check health
pipepost health
```

## Architecture

```
Source → Scout → Fetch → Translate → Validate → Publish → Destination
  │                                                            │
  HN, Reddit, RSS, Search              Webhook, WordPress, Ghost, .md
```

Every step is independent and composable. Create custom flows by chaining steps:

```python
from pipepost.core import Flow
from pipepost.steps.fetch import FetchStep
from pipepost.steps.translate import TranslateStep
from pipepost.steps.validate import ValidateStep
from pipepost.steps.publish import PublishStep

my_flow = Flow(
    name="my-pipeline",
    steps=[
        FetchStep(max_chars=15000),
        TranslateStep(model="deepseek/deepseek-chat", target_lang="ru"),
        ValidateStep(min_content_len=500),
        PublishStep(destination_name="webhook"),
    ],
)
```

## Use Cases

### Cooking & Food
```yaml
sources:
  - name: food-news
    type: reddit
    subreddits: [cooking, recipes, AskCulinary]
  - name: food-search
    type: search
    queries:
      - "new restaurant trends 2026"
      - "seasonal recipes spring"
```

### Travel & Adventure
```yaml
sources:
  - name: travel-news
    type: search
    queries:
      - "best travel destinations 2026"
      - "budget travel tips Europe"
      - "digital nomad guides"
```

### Finance & Investing
```yaml
sources:
  - name: finance-news
    type: reddit
    subreddits: [personalfinance, investing]
  - name: finance-search
    type: search
    queries:
      - "stock market analysis today"
      - "personal finance strategies"
```

### Health & Science
```yaml
sources:
  - name: health-news
    type: search
    queries:
      - "health research breakthroughs"
      - "nutrition science news"
      - "mental health studies"
```

### Tech & Programming
```yaml
sources:
  - name: tech-news
    type: search
    queries:
      - "latest AI research papers"
      - "open source projects trending"
```

### Sports & Fitness
```yaml
sources:
  - name: sports-news
    type: reddit
    subreddits: [sports, fitness, running]
  - name: sports-search
    type: search
    queries:
      - "sports highlights this week"
      - "fitness training programs"
```

## Sources

| Source | Type | Description |
|--------|------|-------------|
| `hackernews` | API | Top stories from Hacker News (Firebase API) |
| `reddit` | API | Top posts from configurable subreddits |
| `rss` | RSS/Atom | Any RSS or Atom feed URL |
| `search` | DuckDuckGo | Keyword-based article search |

## Destinations

| Destination | Description |
|-------------|-------------|
| `webhook` | POST to any URL (WordPress REST API, Ghost, custom) |
| `markdown` | Save as `.md` files with YAML frontmatter |

## Steps

| Step | Description |
|------|-------------|
| `fetch` | Download article, extract content as markdown, get og:image |
| `translate` | Translate via LLM (LiteLLM — supports 100+ models) |
| `validate` | Check translation quality (length, ratio, required fields) |
| `publish` | Send to configured destination |

## Configuration

```yaml
# pipepost.yaml
sources:
  - name: hackernews
    min_score: 100
  - name: my-blog
    type: rss
    url: https://example.com/feed.xml
  - name: daily-search
    type: search
    queries:
      - "latest news in your niche"
      - "trending articles today"

destination:
  type: webhook
  url: https://myblog.com/api/posts/auto-publish
  headers:
    Authorization: "Bearer your-token"

translate:
  model: deepseek/deepseek-chat
  target_lang: ru
  min_ratio: 0.8
```

See [examples/pipepost.yaml](examples/pipepost.yaml) for a complete configuration example.

## Adding a Custom Source

Create a single file — PipePost auto-discovers it:

```python
# pipepost/sources/my_source.py
from pipepost.sources.base import Source
from pipepost.core.context import Candidate
from pipepost.core.registry import register_source


class MySource(Source):
    name = "my-source"
    source_type = "api"

    async def fetch_candidates(self, limit: int = 10) -> list[Candidate]:
        # Your logic here
        return [Candidate(url="https://...", title="...", source_name=self.name)]


register_source("my-source", MySource())
```

## Adding a Custom Destination

```python
# pipepost/destinations/my_cms.py
from pipepost.destinations.base import Destination
from pipepost.core.context import PublishResult, TranslatedArticle
from pipepost.core.registry import register_destination


class MyCMSDestination(Destination):
    name = "my-cms"

    async def publish(self, article: TranslatedArticle) -> PublishResult:
        # Your CMS API logic here
        return PublishResult(success=True, slug="article-slug")


register_destination("my-cms", MyCMSDestination())
```

## Supported LLM Models

PipePost uses [LiteLLM](https://github.com/BerriAI/litellm) for translation, supporting 100+ models:

- **DeepSeek** — `deepseek/deepseek-chat`, `deepseek/deepseek-reasoner`
- **OpenAI** — `gpt-4o`, `gpt-4o-mini`
- **Anthropic** — `claude-sonnet-4-20250514`, `claude-haiku-4-20250414`
- **Google** — `gemini/gemini-2.0-flash`
- **Local** — `ollama/llama3.1`, any Ollama model

Set via `PIPEPOST_MODEL` env var or in YAML config.

## Docker

```bash
# Build and run
docker compose up -d

# Or build manually
docker build -t pipepost .
docker run -v ./pipepost.yaml:/app/config/pipepost.yaml pipepost run curate
```

## Development

```bash
git clone https://github.com/DenSul/pipepost
cd pipepost
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Lint
ruff check pipepost/

# Type check
mypy --strict pipepost/

# Test
pytest tests/
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to get started.

In short: fork, branch, make your changes, run `ruff check`, `mypy --strict`, and `pytest`, then open a PR.

## License

[AGPL-3.0](LICENSE) -- Free to use, modify, and self-host. If you offer PipePost as a hosted service, you must open-source your modifications.

---

Built by [Denis Sultanov](https://github.com/DenSul)
