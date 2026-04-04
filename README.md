# 🚀 PipePost

**Open-source AI content curation pipeline** — Scout, translate, and publish tech articles automatically.

PipePost discovers articles from sources like HackerNews, Reddit, and RSS feeds, translates them to your target language using AI, and publishes to your blog or CMS.

## Features

- 📡 **Multiple Sources** — HackerNews, Reddit, RSS/Atom, DuckDuckGo search
- 🌍 **AI Translation** — Full paragraph-by-paragraph translation via any LLM (DeepSeek, Claude, GPT, etc.)
- 📝 **Multiple Destinations** — Webhook (WordPress, Ghost, custom), Markdown files
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

# Run
pipepost run curate --source hackernews --dest webhook
```

## Architecture

```
Source → Scout → Fetch → Translate → Validate → Publish → Destination
  │                                                            │
  HN, Reddit, RSS                              WordPress, Ghost, Webhook, .md
```

Every step is independent and composable. Create custom flows by chaining steps.

## Sources

| Source | Type | Description |
|--------|------|-------------|
| `hackernews` | API | Top stories from HN |
| `reddit` | API | Top posts from subreddits |
| `rss` | RSS/Atom | Any RSS or Atom feed |
| `search` | DuckDuckGo | Keyword-based search |

## Destinations

| Destination | Description |
|-------------|-------------|
| `webhook` | POST to any URL (WordPress REST, Ghost, custom) |
| `markdown` | Save as .md files |

## Configuration

```yaml
# pipepost.yaml
sources:
  - name: hackernews
    min_score: 100
  - name: my-blog
    type: rss
    url: https://example.com/feed.xml

destination:
  type: webhook
  url: https://myblog.com/api/posts

translate:
  model: deepseek/deepseek-chat
  target_lang: ru
  min_ratio: 0.8
```

## Adding a Custom Source

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
        return [Candidate(url="...", title="...", source_name=self.name)]

register_source("my-source", MySource())
```

## CLI

```bash
pipepost sources         # List available sources
pipepost destinations    # List available destinations
pipepost run <flow>      # Run a pipeline flow
pipepost health          # Check pipeline health
```

## License

AGPL-3.0 — See [LICENSE](LICENSE)

## Author

Denis Sultanov — [@DenSul](https://github.com/DenSul)
