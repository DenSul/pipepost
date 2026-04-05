"""PipePost CLI — run content curation pipelines."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

import click

from pipepost.core.registry import (
    discover_all,
    get_flow,
    list_destinations,
    list_flows,
    list_sources,
)


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging to stderr."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """PipePost — Open-source AI content curation pipeline."""
    _setup_logging(verbose)
    discover_all()


@main.command("sources")
def cmd_sources() -> None:
    """List available content sources."""
    sources = list_sources()
    if not sources:
        click.echo("No sources registered.")
        return
    click.echo("Available sources:")
    for name in sources:
        click.echo(f"  • {name}")


@main.command("destinations")
def cmd_destinations() -> None:
    """List available publish destinations."""
    dests = list_destinations()
    if not dests:
        click.echo("No destinations registered.")
        return
    click.echo("Available destinations:")
    for name in dests:
        click.echo(f"  • {name}")


@main.command("flows")
def cmd_flows() -> None:
    """List available pipeline flows."""
    flows = list_flows()
    if not flows:
        click.echo("No flows registered.")
        return
    click.echo("Available flows:")
    for name in flows:
        click.echo(f"  • {name}")


@main.command("run")
@click.argument("flow_name", default="default")
@click.option("--source", "-s", help="Source name")
@click.option("--dest", "-d", default="default", help="Destination name")
@click.option("--lang", "-l", default="ru", help="Target language")
@click.option("--config", "-c", "config_path", default=None, help="Path to config file")
@click.option("--dry-run", is_flag=True, help="Preview pipeline results without publishing")
@click.option("--batch", is_flag=True, help="Process multiple articles in one run")
@click.option("--max-articles", "-n", default=3, help="Max articles to process in batch mode")
@click.option(
    "--metrics-port", type=int, default=None, help="Expose Prometheus metrics on this port"
)
def cmd_run(
    flow_name: str,
    source: str | None,
    dest: str,
    lang: str,
    config_path: str | None,
    dry_run: bool,
    batch: bool,
    max_articles: int,
    metrics_port: int | None,
) -> None:
    """Run a pipeline flow."""
    if metrics_port is not None:
        from pipepost.metrics import metrics as pipeline_metrics

        pipeline_metrics.start_http_server(metrics_port)

    if batch:
        _run_batch_mode(
            source=source or "",
            dest=dest,
            lang=lang,
            dry_run=dry_run,
            max_articles=max_articles,
        )
        return

    flow = _resolve_flow(flow_name, config_path)

    from pipepost.core.context import FlowContext

    metadata: dict[str, object] = {"destination": dest}
    if dry_run:
        metadata["dry_run"] = True

    ctx = FlowContext(
        source_name=source or "",
        target_lang=lang,
        metadata=metadata,
    )

    result = asyncio.run(flow.run(ctx))

    if dry_run:
        click.echo("Dry run complete — preview of pipeline results:")
        click.echo(f"  Candidates found: {len(result.candidates)}")
        if result.selected:
            click.echo(f"  Selected article: {result.selected.title}")
            click.echo(f"  Selected URL: {result.selected.url}")
        if result.translated:
            click.echo(f"  Translated title: {result.translated.title_translated}")
            if result.translated.tags:
                click.echo(f"  Tags: {', '.join(result.translated.tags)}")
        click.echo(f"  Destination: {dest}")
        return

    if result.published and result.published.success:
        click.echo(f"Published: {result.published.slug}")
    elif result.errors:
        click.echo(f"Errors: {'; '.join(result.errors)}", err=True)
        sys.exit(1)
    else:
        click.echo("Flow completed with no result.")


if TYPE_CHECKING:
    from pipepost.core.flow import Flow


def _resolve_flow(flow_name: str, config_path: str | None) -> Flow:
    """Build flow from config file or fall back to registry."""
    if config_path:
        from pipepost.config import build_flow_from_config
        from pipepost.config.loader import load_config

        config = load_config(config_path)
        return build_flow_from_config(config)

    try:
        return get_flow(flow_name)
    except KeyError:
        available = list_flows()
        click.echo(f"Unknown flow: {flow_name}. Available: {', '.join(available)}", err=True)
        sys.exit(1)


def _run_batch_mode(
    source: str,
    dest: str,
    lang: str,
    dry_run: bool,
    max_articles: int,
) -> None:
    """Execute batch mode and print per-article summary."""
    from pipepost.batch import run_batch

    results = asyncio.run(
        run_batch(
            source_name=source,
            target_lang=lang,
            max_articles=max_articles,
            destination_name=dest,
            dry_run=dry_run,
        )
    )

    if not results:
        click.echo("Batch: no articles processed.")
        return

    any_success = False
    click.echo(f"Batch: processed {len(results)} article(s)")
    for i, ctx in enumerate(results, 1):
        title = ""
        if ctx.translated:
            title = ctx.translated.title_translated
        elif ctx.selected:
            title = ctx.selected.title

        slug = ctx.published.slug if ctx.published else ""
        status = "ok" if (ctx.published and ctx.published.success) else "failed"
        if dry_run and ctx.translated and not ctx.has_errors:
            status = "dry-run"
            any_success = True
        elif ctx.published and ctx.published.success:
            any_success = True

        click.echo(f"  [{i}] {title or '(unknown)'} | {slug or '-'} | {status}")
        if ctx.errors:
            for err in ctx.errors:
                click.echo(f"      error: {err}")

    if not any_success:
        sys.exit(1)


@main.command("bot")
@click.option("--token", envvar="TELEGRAM_BOT_TOKEN", required=True, help="Telegram bot token")
@click.option("--source", "-s", default="", help="Default source name")
@click.option("--lang", "-l", default="ru", help="Target language")
def cmd_bot(token: str, source: str, lang: str) -> None:
    """Run interactive Telegram curation bot."""
    from pipepost.bot.curator import CuratorBot

    bot = CuratorBot(bot_token=token, source_name=source, target_lang=lang)
    asyncio.run(bot.start())


@main.command("health")
def cmd_health() -> None:
    """Check pipeline health."""
    sources = list_sources()
    dests = list_destinations()
    flows = list_flows()
    click.echo(f"Sources: {', '.join(sources) if sources else 'none'}")
    click.echo(f"Destinations: {', '.join(dests) if dests else 'none'}")
    click.echo(f"Flows: {', '.join(flows) if flows else 'none'}")
    click.echo("✅ Pipeline healthy")


if __name__ == "__main__":
    main()
