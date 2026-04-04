# 🚀 PipePost

**Open-source AI content curation pipeline** — Scout, translate, and publish tech articles automatically.

PipePost discovers articles from sources like HackerNews, Reddit, and RSS feeds, translates them to your target language using AI, and publishes to your blog or CMS.

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
  - name: tech-news
    type: search
    queries:
      - "latest AI research papers"
      - "golang best practices 2026"

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

## Development

```bash
git clone https://github.com/DenSul/pipepost
cd pipepost
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Lint
ruff check pipepost/

# Test
pytest tests/
```

## License

[AGPL-3.0](LICENSE) — Free to use, modify, and self-host. If you offer PipePost as a hosted service, you must open-source your modifications.

## Author

Denis Sultanov — [@DenSul](https://github.com/DenSul)
