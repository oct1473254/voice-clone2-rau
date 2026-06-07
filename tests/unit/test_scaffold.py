"""Step 1 smoke test: package and CLI surface are importable, --help works."""
import subprocess
import sys

import hamlet_ai
from hamlet_ai import cli


def test_package_has_version():
    assert hamlet_ai.__version__ == "0.1.0"


def test_cli_parser_recognizes_known_subcommands():
    parser = cli.build_parser()
    args = parser.parse_args(["gui"])
    assert args.command == "gui"
    args = parser.parse_args(["voice-clone"])
    assert args.command == "voice-clone"
    args = parser.parse_args(["script-gen"])
    assert args.command == "script-gen"


def test_cli_no_args_prints_help_and_exits_zero(capsys):
    rc = cli.main([])
    captured = capsys.readouterr()
    assert rc == 0
    assert "hamlet-ai" in captured.out
    assert "voice-clone" in captured.out
    assert "script-gen" in captured.out


def test_cli_help_via_subprocess():
    result = subprocess.run(
        [sys.executable, "-m", "hamlet_ai", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "hamlet-ai" in result.stdout
