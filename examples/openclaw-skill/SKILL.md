---
name: pipepost
description: AI content curation — scout, translate, and publish articles from HackerNews, Reddit, RSS, and search engines
version: 0.1.0
---

# PipePost — Content Curation Skill

You have access to PipePost, a CLI tool for scouting, translating, and publishing articles.

## When to use

Use PipePost when the user asks about:
- Finding/scouting/curating articles or news
- Translating articles to another language
- Publishing content to a blog, Telegram, or other destination
- Checking what sources or destinations are available

## Available commands

### Preview articles (dry run, no publishing)
```bash
pipepost run default --source hackernews --dry-run --lang ru
```

### Publish a single article
```bash
pipepost run default --source hackernews --lang ru
```

### Publish multiple articles (batch mode)
```bash
pipepost run default --source hackernews --batch -n 3 --lang ru
```

### List sources
```bash
pipepost sources
```

### List destinations
```bash
pipepost destinations
```

### Health check
```bash
pipepost health
```

## Source options

Replace `--source hackernews` with any of:
- `--source hackernews` — top HN stories
- `--source reddit` — top Reddit posts (configured subreddits)
- `--source rss` — RSS/Atom feeds
- `--source search` — DuckDuckGo keyword search

## Language options

Replace `--lang ru` with any language code: `ru`, `es`, `de`, `fr`, `zh`, `ja`, `ko`, etc.

## Examples of user requests and what to run

| User says | Command |
|-----------|---------|
| "find me tech news" | `pipepost run default --source hackernews --dry-run --lang ru` |
| "scout AI articles from Reddit" | `pipepost run default --source reddit --dry-run --lang ru` |
| "publish top 3 HN articles" | `pipepost run default --source hackernews --batch -n 3 --lang ru` |
| "translate this to Spanish" | `pipepost run default --source hackernews --lang es` |
| "what sources do we have?" | `pipepost sources` |

## Important

- Always do `--dry-run` first if the user just wants to see what's available
- Use `--batch -n N` when the user asks for multiple articles
- The tool outputs translated articles as markdown files in `./output/`
