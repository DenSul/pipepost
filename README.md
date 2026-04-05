```
         _                          _
 _ __ (_)_ __   ___ _ __   ___  ___| |_
| '_ \| | '_ \ / _ \ '_ \ / _ \/ __| __|
| |_) | | |_) |  __/ |_) | (_) \__ \ |_
| .__/|_| .__/ \___| .__/ \___/|___/\__|
|_|     |_|        |_|
```

[![CI](https://github.com/densul/pipepost/actions/workflows/ci.yml/badge.svg)](https://github.com/densul/pipepost/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pipepost.svg)](https://pypi.org/project/pipepost/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-396%20passed-brightgreen.svg)](https://github.com/densul/pipepost)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen.svg)](https://github.com/densul/pipepost)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

# PipePost

**Open-source AI content curation pipeline** -- scout, translate, and publish articles from any domain automatically.

```
  HackerNews ─┐                                              ┌─ Blog (webhook)
  Reddit     ─┤   ┌───────┐   ┌──────────┐   ┌──────────┐   ├─ Telegram channel
  RSS/Atom   ─┼──>│ Scout ├──>│Translate ├──>│ Publish  ├──>├─ Markdown files
  DuckDuckGo ─┤   │ + Score│   │ + Adapt  │   │ + Fanout │   ├─ OpenClaw (23+ channels)
  Custom     ─┘   └───────┘   └──────────┘   └──────────┘   └─ Custom destination
                    AI ranks      AI translates    Publishes to
                    best articles  & adapts style   multiple targets
```

PipePost discovers articles from sources like HackerNews, Reddit, RSS feeds, and search engines, translates them to your target language using AI, and publishes to your blog or CMS. Works for any niche -- tech, business, health, lifestyle, and more.

<p align="center">
  <img src="docs/demo.gif" alt="PipePost demo — batch pipeline run" width="720">
</p>

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
- [Telegram Bot](#telegram-bot)
- [OpenClaw Integration](#openclaw-integration)
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
- 📝 **Multiple Destinations** — Webhook, Markdown, Telegram, OpenClaw (23+ channels)
- 🤖 **Telegram Bot** — Interactive curation: scout candidates, approve/reject via inline buttons
- 🎯 **Smart Scoring** — LLM-based candidate ranking by relevance, originality, and engagement
- ✍️ **Style Adaptation** — Adapt content for blog, Telegram, newsletter, or Twitter thread
- 📢 **Fanout Publish** — Publish to multiple destinations simultaneously
- 📦 **Batch Mode** — Process multiple articles in one run (`--batch -n 5`)
- 🔄 **Composable Flows** — Chain steps: dedup → scout → score → fetch → translate → adapt → publish
- 💾 **Deduplication** — SQLite-backed persistence prevents re-publishing across runs
- 📊 **Prometheus Metrics** — Pipeline runs, step durations, error counters (optional)
- ⚙️ **Config-Driven Flows** — Define entire pipelines in YAML without writing Python
- 🧩 **Plugin Architecture** — Add sources and destinations with a single file
- 🐳 **Docker Ready** — `docker compose up` and go

## Quick Start

```bash
# Install from PyPI
pip install pipepost

# Or from source
git clone https://github.com/DenSul/pipepost && cd pipepost
pip install -e .

# Configure
export PIPEPOST_MODEL=deepseek/deepseek-chat
export DEEPSEEK_API_KEY=your-key  # or OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.

# List available components
pipepost sources
pipepost destinations
pipepost flows

# Run a pipeline flow
pipepost run default --source hackernews --dest webhook --lang ru

# Preview without publishing (dry run)
pipepost run default --source hackernews --dry-run

# Batch mode — process multiple articles
pipepost run default --source hackernews --batch -n 5

# Use a config file
pipepost run --config pipepost.yaml --source hackernews

# Run interactive Telegram bot
export TELEGRAM_BOT_TOKEN=your-bot-token
pipepost bot --source hackernews --lang ru

# Check health
pipepost health
```

**Example batch output:**

```
$ pipepost run default --source hackernews --batch -n 3 --lang ru

Batch: processed 3 article(s)
  [1] Восемь лет желания, три месяца работы с ИИ | 2026-04-05-vosem-let-zhelaniya | ok
  [2] Финская сауна усиливает иммунный ответ    | 2026-04-05-finskaya-sauna       | ok
  [3] Утечка email-адресов в BrowserStack        | 2026-04-05-utechka-email        | ok
```

## Architecture

```mermaid
graph LR
    subgraph Sources
        HN[HackerNews]
        RD[Reddit]
        RSS[RSS/Atom]
        DDG[DuckDuckGo]
    end

    subgraph Pipeline
        Dedup[Dedup<br><i>SQLite</i>]
        Scout[Scout<br><i>fetch candidates</i>]
        Score[Score<br><i>LLM ranking</i>]
        Fetch[Fetch<br><i>download article</i>]
        Translate[Translate<br><i>LLM translation</i>]
        Adapt[Adapt<br><i>style: blog/tg/thread</i>]
        Validate[Validate<br><i>quality check</i>]
    end

    subgraph Destinations
        WH[Webhook / CMS]
        MD[Markdown]
        TG[Telegram]
        OC[OpenClaw<br><i>23+ channels</i>]
    end

    HN & RD & RSS & DDG --> Dedup --> Scout --> Score --> Fetch --> Translate --> Adapt --> Validate
    Validate --> WH & MD & TG & OC

    style Pipeline fill:#1a1a2e,stroke:#16213e,color:#e0e0e0
    style Sources fill:#0f3460,stroke:#16213e,color:#e0e0e0
    style Destinations fill:#533483,stroke:#16213e,color:#e0e0e0
```

Every step is independent and composable. Define your pipeline in YAML -- no Python needed:

```yaml
# pipepost.yaml — full pipeline config
sources:
  - name: hackernews
    min_score: 100

translate:
  model: deepseek/deepseek-chat
  target_lang: ru

destination:
  type: markdown
  output_dir: ./output

flow:
  steps: [dedup, scout, score, fetch, translate, validate, publish, post_publish]
  score:
    niche: tech
  storage:
    db_path: pipepost.db
```

```bash
pipepost run --config pipepost.yaml --source hackernews
```

Add or remove steps from the `flow.steps` list to customize your pipeline. Available steps: `dedup`, `scout`, `score`, `fetch`, `translate`, `adapt`, `validate`, `publish`, `fanout_publish`, `post_publish`.

<details>
<summary>Advanced: custom flows in Python</summary>

```python
from pipepost.core import Flow
from pipepost.steps import (
    AdaptStep, DeduplicationStep, FanoutPublishStep, FetchStep,
    PostPublishStep, ScoutStep, ScoringStep, TranslateStep, ValidateStep,
)
from pipepost.storage import SQLiteStorage

storage = SQLiteStorage(db_path="my_project.db")

my_flow = Flow(
    name="my-pipeline",
    steps=[
        DeduplicationStep(storage=storage),
        ScoutStep(max_candidates=20),
        ScoringStep(niche="tech", max_score_candidates=5),
        FetchStep(max_chars=15000),
        TranslateStep(model="deepseek/deepseek-chat", target_lang="ru"),
        AdaptStep(style="telegram"),
        ValidateStep(min_content_len=500),
        FanoutPublishStep(destination_names=["webhook", "telegram", "markdown"]),
        PostPublishStep(storage=storage),
    ],
)
```
</details>

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
| `telegram` | Post to Telegram channels/chats via Bot API |
| `openclaw` | Route through [OpenClaw](https://github.com/openclaw/openclaw) to 23+ messaging platforms |

## Steps

| Step | Description |
|------|-------------|
| `dedup` | Load published URLs from SQLite to prevent re-processing |
| `scout` | Fetch candidates from a source (HN, Reddit, RSS, search) |
| `score` | LLM-based candidate ranking by relevance, originality, engagement |
| `fetch` | Download article, extract content as markdown, get og:image |
| `translate` | Translate via LLM (LiteLLM — supports 100+ models) |
| `adapt` | Adapt content style: blog, telegram, newsletter, or thread |
| `validate` | Check translation quality (length, ratio, required fields) |
| `publish` | Send to a single configured destination |
| `fanout_publish` | Publish to multiple destinations concurrently |
| `post_publish` | Persist published URL to SQLite for future deduplication |

## Configuration

All configuration lives in `pipepost.yaml`. Priority: CLI flags > env vars > YAML > defaults.

```yaml
# pipepost.yaml — complete example
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

flow:
  steps: [dedup, scout, score, fetch, translate, validate, publish, post_publish]
  on_error: stop
  score:
    niche: tech
  publish:
    destination_name: webhook
  storage:
    db_path: pipepost.db
```

**Env var overrides:** `PIPEPOST_MODEL`, `PIPEPOST_LANG`, `PIPEPOST_DEST_URL`

See [examples/pipepost.yaml](examples/pipepost.yaml) for more examples.

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

## Telegram Bot

PipePost includes an interactive Telegram bot for human-in-the-loop content curation:

```bash
export TELEGRAM_BOT_TOKEN=your-bot-token
pipepost bot --source hackernews --lang ru
```

```mermaid
sequenceDiagram
    participant U as You (Telegram)
    participant B as PipePost Bot
    participant S as Source (HN/Reddit)
    participant L as LLM (DeepSeek/GPT)
    participant D as Destination

    U->>B: /scout
    B->>S: fetch_candidates(limit=5)
    S-->>B: 5 articles
    B->>U: Article 1: "..." [Publish] [Skip]
    B->>U: Article 2: "..." [Publish] [Skip]
    U->>B: tap [Publish] on Article 1
    B->>B: fetch full content
    B->>L: translate to Russian
    L-->>B: translated article
    B->>D: publish
    D-->>B: slug: my-article
    B->>U: Published: my-article
```

**How it works:**
1. Send `/scout` to the bot
2. Bot fetches candidates and shows them with inline buttons
3. Tap **Publish** — bot runs the full pipeline (fetch → translate → validate → publish)
4. Tap **Skip** — bot moves to the next candidate

**Telegram as a destination** (automated, no approval needed):

```yaml
destination:
  type: telegram
  bot_token: "your-bot-token"
  chat_id: "@your_channel"
```

## OpenClaw Integration

PipePost integrates with [OpenClaw](https://github.com/openclaw/openclaw) -- a self-hosted AI assistant platform with 23+ messaging channels.

```mermaid
graph LR
    PP[PipePost] -->|publish| OC[OpenClaw Gateway]
    OC --> TG[Telegram]
    OC --> SL[Slack]
    OC --> DC[Discord]
    OC --> WA[WhatsApp]
    OC --> SG[Signal]
    OC --> MS[Teams]
    OC --> ETC[...20+ more]

    style PP fill:#1a1a2e,stroke:#16213e,color:#e0e0e0
    style OC fill:#533483,stroke:#16213e,color:#e0e0e0
```

**As a destination** -- publish through OpenClaw to all connected channels:

```yaml
destination:
  type: openclaw
  gateway_url: "ws://127.0.0.1:18789"
  session_id: "my-session"
  channels: ["telegram", "slack", "discord"]
```

**As an OpenClaw skill** — see [examples/openclaw-skill/SKILL.md](examples/openclaw-skill/SKILL.md) for a ready-to-use skill that lets OpenClaw agents curate content via PipePost.

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
docker run -v ./pipepost.yaml:/app/config/pipepost.yaml pipepost run default
```

## Development

```bash
git clone https://github.com/DenSul/pipepost
cd pipepost
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,metrics]"

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
