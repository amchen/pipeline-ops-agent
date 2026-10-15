"""A framework-free tool-use loop on the Anthropic SDK.

model call -> tool_use blocks -> execute -> tool_result blocks -> repeat, until a terminal tool is
called or a budget (steps / tokens) is exhausted."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import config
from .audit import AuditLog
from .tools.base import Tool, ToolError

MAX_IDENTICAL_CALLS = 3
MAX_NUDGES = 2


@dataclass
class Budget:
    max_steps: int = config.MAX_STEPS_PER_AGENT
    max_tokens: int = config.MAX_TOTAL_TOKENS_PER_AGENT


@dataclass
class AgentResult:
    agent: str
    output: dict[str, Any] | None
    stop_reason: str  # terminal_tool | max_steps | token_budget | no_terminal_tool
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class AgentLoop:
    def __init__(self, client: Any, name: str, system: str, tools: list[Tool], audit: AuditLog,
                 model: str | None = None, budget: Budget | None = None):
        self.client, self.name, self.system, self.audit = client, name, system, audit
        self.tools = {t.name: t for t in tools}
        self.model = model or config.MODEL
        self.budget = budget or Budget()
        terminals = [t.name for t in tools if t.terminal]
        if len(terminals) != 1:
            raise ValueError("Each agent needs exactly one terminal tool.")
        self.terminal = terminals[0]

    def run(self, task: str) -> AgentResult:
        result = AgentResult(agent=self.name, output=None, stop_reason="max_steps")
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        seen: dict[str, int] = {}
        nudges = 0
        tool_schemas = [t.schema() for t in self.tools.values()]

        for step in range(1, self.budget.max_steps + 1):
            if result.total_tokens >= self.budget.max_tokens:
                result.stop_reason = "token_budget"
                break
            response = self.client.messages.create(
                model=self.model, max_tokens=config.MAX_TOKENS_PER_CALL,
                system=self.system, tools=tool_schemas, messages=messages,
            )
            result.steps = step
            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens
            messages.append({"role": "assistant", "content": response.content})

            texts = [b.text for b in response.content if b.type == "text" and b.text.strip()]
            if texts:
                self.audit.log("model_text", agent=self.name, step=step, text=" ".join(texts)[:1000])
            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                nudges += 1
                if nudges > MAX_NUDGES:
                    result.stop_reason = "no_terminal_tool"
                    break
                messages.append({"role": "user", "content": f"Continue using tools, and finish by calling `{self.terminal}`."})
                continue

            tool_results, finished = [], False
            for block in tool_uses:
                key = f"{block.name}:{json.dumps(block.input, sort_keys=True, default=str)}"
                seen[key] = seen.get(key, 0) + 1
                result.tool_calls.append({"name": block.name, "input": block.input})
                self.audit.log("tool_call", agent=self.name, step=step, tool=block.name, input=block.input)
                is_error = False
                tool = self.tools.get(block.name)
                try:
                    if tool is None:
                        raise ToolError(f"Unknown tool '{block.name}'. Available: {sorted(self.tools)}")
                    if isinstance(block.input, dict) and "_malformed_arguments" in block.input:
                        raise ToolError("Your tool arguments were not valid JSON. Resend the call with a valid JSON object.")
                    if seen[key] > MAX_IDENTICAL_CALLS:
                        raise ToolError("You have repeated this exact call several times. Change approach or finish.")
                    text = tool.invoke(block.input)
                    if tool.terminal:
                        result.output = tool.input_model.model_validate(block.input).model_dump()
                        finished = True
                except ToolError as exc:
                    text, is_error = str(exc), True
                except Exception as exc:  # noqa: BLE001 - tool bugs must not crash the agent loop
                    text, is_error = f"Tool failed unexpectedly: {type(exc).__name__}: {exc}", True
                self.audit.log("tool_result", agent=self.name, step=step, tool=block.name, is_error=is_error, chars=len(text))
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error})

            if finished:
                result.stop_reason = "terminal_tool"
                break
            messages.append({"role": "user", "content": tool_results})

        self.audit.log("agent_done", agent=self.name, stop_reason=result.stop_reason, steps=result.steps, tokens=result.total_tokens)
        return result
