"""Tests for CLI commands using click.testing.CliRunner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from pipepost.cli import main
from pipepost.core.context import (
    Article,
    Candidate,
    FlowContext,
    PublishResult,
    TranslatedArticle,
)


class TestCLISources:
    def test_sources_lists_registered(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_sources", return_value=["hackernews", "reddit", "rss"]),
        ):
            result = runner.invoke(main, ["sources"])
        assert result.exit_code == 0
        assert "hackernews" in result.output
        assert "reddit" in result.output
        assert "rss" in result.output

    def test_sources_empty(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_sources", return_value=[]),
        ):
            result = runner.invoke(main, ["sources"])
        assert result.exit_code == 0
        assert "No sources registered" in result.output


class TestCLIDestinations:
    def test_destinations_lists_registered(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_destinations", return_value=["webhook", "markdown"]),
        ):
            result = runner.invoke(main, ["destinations"])
        assert result.exit_code == 0
        assert "webhook" in result.output
        assert "markdown" in result.output

    def test_destinations_empty(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_destinations", return_value=[]),
        ):
            result = runner.invoke(main, ["destinations"])
        assert result.exit_code == 0
        assert "No destinations registered" in result.output


class TestCLIFlows:
    def test_flows_lists_registered(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_flows", return_value=["default", "custom"]),
        ):
            result = runner.invoke(main, ["flows"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "custom" in result.output

    def test_flows_empty(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_flows", return_value=[]),
        ):
            result = runner.invoke(main, ["flows"])
        assert result.exit_code == 0
        assert "No flows registered" in result.output


class TestCLIRun:
    def test_run_unknown_flow_exits_1(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", side_effect=KeyError("not registered")),
            patch("pipepost.cli.list_flows", return_value=["default"]),
        ):
            result = runner.invoke(main, ["run", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown flow" in result.output

    def test_run_successful_publish(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        ctx_result = FlowContext()
        ctx_result.published = PublishResult(
            success=True, slug="my-article", url="/out/my-article.md"
        )
        mock_flow.run.return_value = ctx_result

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default"])
        assert result.exit_code == 0
        assert "Published" in result.output
        assert "my-article" in result.output

    def test_run_with_errors_exits_1(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        ctx_result = FlowContext()
        ctx_result.add_error("fetch failed")
        mock_flow.run.return_value = ctx_result

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default"])
        assert result.exit_code == 1
        assert "fetch failed" in result.output

    def test_run_no_result(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        mock_flow.run.return_value = FlowContext()

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default"])
        assert result.exit_code == 0
        assert "no result" in result.output.lower()

    def test_dry_run_flag_accepted(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        mock_flow.run.return_value = FlowContext()

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default", "--dry-run"])
        assert result.exit_code == 0

    def test_dry_run_shows_preview(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        ctx_result = FlowContext()
        ctx_result.candidates = [
            Candidate(url="https://example.com/1", title="Candidate 1"),
            Candidate(url="https://example.com/2", title="Candidate 2"),
        ]
        ctx_result.selected = Article(
            url="https://example.com/1",
            title="Selected Article",
            content="body",
        )
        ctx_result.translated = TranslatedArticle(
            title="Selected Article",
            title_translated="Выбранная статья",
            content="body",
            content_translated="тело",
            source_url="https://example.com/1",
            tags=["python", "async"],
        )
        mock_flow.run.return_value = ctx_result

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        assert "Selected Article" in result.output
        assert "https://example.com/1" in result.output
        assert "Выбранная статья" in result.output
        assert "python" in result.output
        assert "Candidates found: 2" in result.output
        assert "Destination: default" in result.output

    def test_run_passes_source_and_lang(self):
        runner = CliRunner()
        mock_flow = AsyncMock()
        ctx_result = FlowContext()
        ctx_result.published = PublishResult(success=True, slug="s")
        mock_flow.run.return_value = ctx_result

        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.get_flow", return_value=mock_flow),
        ):
            result = runner.invoke(main, ["run", "default", "-s", "hackernews", "-l", "es"])

        assert result.exit_code == 0
        # Verify the context was created with correct params
        call_ctx = mock_flow.run.call_args[0][0]
        assert call_ctx.source_name == "hackernews"
        assert call_ctx.target_lang == "es"


class TestCLIHealth:
    def test_health_output(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_sources", return_value=["hackernews"]),
            patch("pipepost.cli.list_destinations", return_value=["markdown"]),
            patch("pipepost.cli.list_flows", return_value=["default"]),
        ):
            result = runner.invoke(main, ["health"])
        assert result.exit_code == 0
        assert "hackernews" in result.output
        assert "markdown" in result.output
        assert "default" in result.output
        assert "healthy" in result.output.lower()

    def test_health_no_registrations(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_sources", return_value=[]),
            patch("pipepost.cli.list_destinations", return_value=[]),
            patch("pipepost.cli.list_flows", return_value=[]),
        ):
            result = runner.invoke(main, ["health"])
        assert result.exit_code == 0
        assert "none" in result.output


class TestCLIValidate:
    def test_validate_valid_config(self):
        from pipepost.config.loader import (
            FlowConfig,
            MarkdownDestinationConfig,
            PipePostConfig,
            SourceConfig,
            TranslateConfig,
        )

        mock_config = PipePostConfig(
            sources=[SourceConfig(name="test-rss", type="rss", url="https://example.com/feed.xml")],
            destination=MarkdownDestinationConfig(),
            translate=TranslateConfig(model="gpt-4", target_lang="ru"),
            flow=FlowConfig(steps=["dedup", "scout", "fetch", "translate", "validate", "publish"]),
        )
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.config.loader.load_config", return_value=mock_config),
            patch(
                "pipepost.cli.list_steps",
                return_value=[
                    "dedup",
                    "fetch",
                    "post_publish",
                    "publish",
                    "scout",
                    "translate",
                    "validate",
                ],
            ),
            patch("pipepost.cli.list_sources", return_value=[]),
        ):
            result = runner.invoke(main, ["validate", "-c", "dummy.yaml"])
        assert result.exit_code == 0
        assert "Config: valid" in result.output
        assert "All checks passed" in result.output
        assert "Sources: 1 configured" in result.output
        assert "markdown" in result.output

    def test_validate_unknown_step_exits_1(self):
        from pipepost.config.loader import FlowConfig, PipePostConfig

        mock_config = PipePostConfig(
            flow=FlowConfig(steps=["dedup", "nonexistent_step"]),
        )
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.config.loader.load_config", return_value=mock_config),
            patch("pipepost.cli.list_steps", return_value=["dedup", "fetch", "translate"]),
            patch("pipepost.cli.list_sources", return_value=[]),
        ):
            result = runner.invoke(main, ["validate", "-c", "dummy.yaml"])
        assert result.exit_code == 1
        assert "Unknown step: 'nonexistent_step'" in result.output

    def test_validate_missing_config_exits_1(self):
        runner = CliRunner()
        with patch("pipepost.cli.discover_all"):
            result = runner.invoke(main, ["validate", "-c", "/nonexistent/path.yaml"])
        assert result.exit_code == 1
        assert "Config error" in result.output

    def test_validate_warns_on_default_model(self):
        from pipepost.config.loader import FlowConfig, PipePostConfig, TranslateConfig

        mock_config = PipePostConfig(
            translate=TranslateConfig(model="deepseek/deepseek-chat"),
            flow=FlowConfig(steps=["dedup"]),
        )
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.config.loader.load_config", return_value=mock_config),
            patch("pipepost.cli.list_steps", return_value=["dedup"]),
            patch("pipepost.cli.list_sources", return_value=[]),
            patch.dict("os.environ", {"PIPEPOST_MODEL": ""}, clear=False),
        ):
            result = runner.invoke(main, ["validate", "-c", "dummy.yaml"])
        assert result.exit_code == 0
        assert "No custom model configured" in result.output


class TestCLIVerbose:
    def test_verbose_flag_accepted(self):
        runner = CliRunner()
        with (
            patch("pipepost.cli.discover_all"),
            patch("pipepost.cli.list_sources", return_value=[]),
        ):
            result = runner.invoke(main, ["-v", "sources"])
        assert result.exit_code == 0
