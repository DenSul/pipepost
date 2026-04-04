"""PipePost CLI — run content curation pipelines."""
from __future__ import annotations

import asyncio
import logging
import sys

import click

from pipepost.core.registry import discover_all, list_destinations, list_flows, list_sources


def _setup_logging(verbose: bool = False) -> None:
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


@main.command("run")
@click.argument("flow_name")
@click.option("--source", "-s", help="Source name")
@click.option("--dest", "-d", default="default", help="Destination name")
@click.option("--lang", "-l", default="ru", help="Target language")
def cmd_run(flow_name: str, source: str | None, dest: str, lang: str) -> None:
    """Run a pipeline flow."""
    from pipepost.core.context import FlowContext
    from pipepost.core.registry import get_flow

    try:
        flow = get_flow(flow_name)
    except KeyError:
        available = list_flows()
        click.echo(f"Unknown flow: {flow_name}. Available: {', '.join(available)}", err=True)
        sys.exit(1)

    ctx = FlowContext(
        source_name=source or "",
        target_lang=lang,
    )

    result = asyncio.run(flow.run(ctx))

    if result.published and result.published.success:
        click.echo(f"✅ Published: {result.published.slug}")
    elif result.errors:
        click.echo(f"❌ Errors: {'; '.join(result.errors)}", err=True)
        sys.exit(1)
    else:
        click.echo("⚠️ Flow completed with no result.")


@main.command("health")
def cmd_health() -> None:
    """Check pipeline health."""
    sources = ", ".join(list_sources()) or "none"
    dests = ", ".join(list_destinations()) or "none"
    flows = ", ".join(list_flows()) or "none"
    click.echo(f"Sources: {sources}")
    click.echo(f"Destinations: {dests}")
    click.echo(f"Flows: {flows}")
    click.echo("✅ Pipeline healthy")


if __name__ == "__main__":
    main()
