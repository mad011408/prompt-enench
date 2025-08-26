#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# Ensure package import when running from source
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
	sys.path.insert(0, str(CURRENT_DIR))

from utils.config_manager import ConfigManager
from core.brain import Brain
from terminal.shell import TerminalShell


def make_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		prog="terminal-nexus",
		description="Ultra-Advanced Terminal AI Agent (Gemini-only)",
	)
	parser.add_argument(
		"command",
		nargs="?",
		choices=["repl"],
		help="Command to run. Use 'repl' for interactive shell.",
	)
	parser.add_argument(
		"--config",
		dest="config_path",
		default=str(CURRENT_DIR / "config" / "nexus_config.yaml"),
		help="Path to configuration YAML",
	)
	return parser


def main(argv=None) -> int:
	argv = argv if argv is not None else sys.argv[1:]
	parser = make_parser()
	args = parser.parse_args(argv)

	config = ConfigManager.load(args.config_path)
	brain = Brain(config=config)

	if args.command == "repl" or args.command is None:
		shell = TerminalShell(brain=brain)
		return shell.run()

	return 0


if __name__ == "__main__":
	sys.exit(main())