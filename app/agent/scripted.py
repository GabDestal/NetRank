"""A chat model that replays a fixed list of replies, for tests and for the guardrail demo.

A real LLM cannot be relied on to produce a bad query on demand, so the demo scripts the "LLM output"
and lets the real guardrails, tools and Neo4j handle it.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(BaseChatModel):
    """Returns the scripted replies in order, one per call. Tool binding is accepted and ignored."""

    replies: list[AIMessage]
    seen: list[list[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        """Name LangChain uses for this model type."""
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        """Ignore the tools: the replies are already written."""
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None,
                  **kwargs: Any) -> ChatResult:
        """Record what the model was shown and return the next reply."""
        self.seen.append(list(messages))
        if not self.replies:
            raise RuntimeError("the script has no more replies")
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])


def tool_call(name: str, call_id: str, **arguments: Any) -> AIMessage:
    """An LLM reply that calls one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": arguments, "id": call_id, "type": "tool_call"}])
