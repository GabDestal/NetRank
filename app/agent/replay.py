"""Record and replay LLM turns, so tests and CI never call Groq (decision log D67).

A recording is a JSON list of turns: {"content": str, "tool_calls": [{"name", "args", "id"}]}.
RecordingLLM wraps the live model and stores every turn; ReplayLLM returns them in order.
"""

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage


def to_turn(message: AIMessage) -> dict:
    """Serialisable form of one model turn."""
    calls = [{"name": c["name"], "args": c["args"], "id": c["id"]} for c in message.tool_calls]
    return {"content": message.content if isinstance(message.content, str) else "", "tool_calls": calls}


def from_turn(turn: dict) -> AIMessage:
    """AIMessage from a recorded turn."""
    calls = [{**call, "type": "tool_call"} for call in turn["tool_calls"]]
    return AIMessage(content=turn.get("content", ""), tool_calls=calls)


class ReplayLLM:
    """Plays back recorded turns, one per invoke; fails loudly if the agent asks for more."""

    def __init__(self, turns: list[dict]) -> None:
        """`turns` as produced by RecordingLLM (or written by hand for unit tests)."""
        self.turns = list(turns)
        self.calls = 0

    @classmethod
    def from_file(cls, path: Path) -> "ReplayLLM":
        """Load a recording."""
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def invoke(self, _messages: list) -> AIMessage:
        """Next recorded turn."""
        if self.calls >= len(self.turns):
            raise RuntimeError(f"recording exhausted after {self.calls} turns")
        turn = self.turns[self.calls]
        self.calls += 1
        return from_turn(turn)


class RecordingLLM:
    """Delegates to a live model and keeps every turn for later replay."""

    def __init__(self, llm: Any) -> None:
        """Wrap the bound, retrying chat model."""
        self.llm = llm
        self.turns: list[dict] = []

    def invoke(self, messages: list) -> AIMessage:
        """Call the live model and record its answer."""
        message = self.llm.invoke(messages)
        self.turns.append(to_turn(message))
        return message

    def save(self, path: Path) -> None:
        """Write the recording."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.turns, indent=2, default=str), encoding="utf-8", newline="\n")
