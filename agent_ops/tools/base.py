"""Tool abstraction: a Pydantic input model, a handler, and Anthropic-format schema generation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

MAX_TOOL_CHARS = 6000


class ToolError(Exception):
    """Raised for expected, model-recoverable failures. The message is shown to the model."""


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any], Any]
    untrusted: bool = False  # output contains externally sourced text (logs, rows, files)
    terminal: bool = False   # calling this ends the agent loop and carries its structured result
    writes: bool = False     # touches state outside the agent's own bookkeeping

    def schema(self) -> dict[str, Any]:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}

    def invoke(self, raw_input: dict[str, Any] | None) -> str:
        try:
            args = self.input_model.model_validate(raw_input or {})
        except ValidationError as exc:
            detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            raise ToolError(f"Invalid arguments for {self.name}: {detail}") from None
        result = self.handler(args)
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        if len(text) > MAX_TOOL_CHARS:
            text = text[:MAX_TOOL_CHARS] + f"... [truncated {len(text) - MAX_TOOL_CHARS} chars]"
        if self.untrusted:
            text = f'<untrusted_data source="{self.name}">\n{text}\n</untrusted_data>'
        return text
