"""PipePost CLI — run content curation pipelines."""

from __future__ import annotations

import asyncio
import logging
import sys

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
@click.argument("flow_name")
@click.option("--source", "-s", help="Source name")
@click.option("--dest", "-d", default="default", help="Destination name")
@click.option("--lang", "-l", default="ru", help="Target language")
@click.option("--dry-run", is_flag=True, help="Preview pipeline results without publishing")
@click.option(
    "--metrics-port", type=int, default=None, help="Expose Prometheus metrics on this port"
)
def cmd_run(
    flow_name: str,
    source: str | None,
    dest: str,
    lang: str,
    dry_run: bool,
    metrics_port: int | None,
) -> None:
    """Run a pipeline flow."""
    if metrics_port is not None:
        from pipepost.metrics import metrics as pipeline_metrics

        pipeline_metrics.start_http_server(metrics_port)

    try:
        flow = get_flow(flow_name)
    except KeyError:
        available = list_flows()
        click.echo(f"Unknown flow: {flow_name}. Available: {', '.join(available)}", err=True)
        sys.exit(1)

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
