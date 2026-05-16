"""Tests for CLI click command registration."""

from click.testing import CliRunner

from tokstash.cli import cli


class TestCliRegistration:
    """Click CLI command registration."""

    def test_help_output(self) -> None:
        """--help shows expected commands."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "download" in result.output
        assert "monitor" in result.output

    def test_download_help(self) -> None:
        """download --help shows options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["download", "--help"])
        assert result.exit_code == 0
        assert "USERNAME" in result.output
        assert "--output" in result.output
        assert "--segment" in result.output

    def test_monitor_help(self) -> None:
        """monitor --help shows options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["monitor", "--help"])
        assert result.exit_code == 0
        assert "--retry" in result.output

    def test_download_requires_username(self) -> None:
        """download fails without USERNAME argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["download"])
        assert result.exit_code != 0
        assert "Usage:" in result.output
