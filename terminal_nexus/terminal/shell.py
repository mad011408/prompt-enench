from __future__ import annotations

import sys

from core.brain import Brain


class TerminalShell:
	def __init__(self, brain: Brain):
		self._brain = brain

	def run(self) -> int:
		print("Terminal Nexus (Gemini). Type 'exit' or Ctrl-D to quit.")
		try:
			while True:
				print("> ", end="", flush=True)
				line = sys.stdin.readline()
				if not line:
					print()
					break
				line = line.strip()
				if line.lower() in {"exit", "quit"}:
					break
				if not line:
					continue
				reply = self._brain.chat(line)
				print(reply)
		except KeyboardInterrupt:
			print()
			return 0
		return 0