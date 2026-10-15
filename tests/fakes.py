"""A scripted stand-in for anthropic.Anthropic, so the whole loop is testable without an API key."""
from __future__ import annotations

import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


def text(t: str):
    return SimpleNamespace(type="text", text=t)


def tool_use(tool_name: str, /, **input):
    return SimpleNamespace(type="tool_use", id=f"toolu_{next(_ids)}", name=tool_name, input=input)


class ScriptedClient:
    """scripts: {substring-of-system-prompt: [response_blocks_list, ...]}"""

    def __init__(self, scripts: dict[str, list[list]]):
        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        for marker, queue in self.scripts.items():
            if marker in kw["system"]:
                if not queue:
                    raise AssertionError(f"script for '{marker}' exhausted")
                content = queue.pop(0)
                return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=100, output_tokens=20))
        raise AssertionError("no script matched system prompt")
