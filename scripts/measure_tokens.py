"""Estimate the prompt tokens the agent sends per question, by replaying a recorded live run.

Each model turn is counted as Groq receives it: the tool specs plus every message so far. The recorded
turns are the same whatever the code version, so running this before and after a change measures what
the change does to the prompt. Tokens are estimated with tiktoken's o200k_base encoding (the tokenizer
family of gpt-oss); live runs also record Groq's own count (`promptTokens` in eval/runs/).

    python -m scripts.measure_tokens --recordings live-3
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import tiktoken

from app.agent import graph
from app.agent.llm import ToolCallRejectedError
from app.agent.replay import ReplayLLM
from app.agent.tools import tool_specs
from app.config import get_settings
from app.database.client import Neo4jClient

RECORDINGS = Path("eval/recordings")
RUNS = Path("eval/runs")
QUESTION_SETS = {"v1": Path("eval/questions_v1.json"), "v2": Path("eval/questions_v2.json")}
PER_MESSAGE = 4  # role and separator tokens of the chat format

log = logging.getLogger(__name__)


class CountingLLM:
    """Counts the prompt of every turn, then plays the recorded answer."""

    def __init__(self, replay: ReplayLLM, encoding) -> None:
        """Wrap a replay."""
        self.replay = replay
        self.encoding = encoding
        self.specs = len(encoding.encode(json.dumps(tool_specs())))
        self.prompt_tokens: list[int] = []

    def tokens(self, message) -> int:
        """Tokens of one message: text plus tool-call arguments."""
        text = message.content if isinstance(message.content, str) else json.dumps(message.content)
        calls = json.dumps(getattr(message, "tool_calls", []) or [], default=str)
        return len(self.encoding.encode(text)) + len(self.encoding.encode(calls)) + PER_MESSAGE

    def invoke(self, messages: list):
        """Count, then replay."""
        self.prompt_tokens.append(self.specs + sum(self.tokens(m) for m in messages))
        return self.replay.invoke(messages)


def measure(label: str) -> list[dict]:
    """Prompt tokens per question of one recorded run."""
    encoding = tiktoken.get_encoding("o200k_base")
    run = RUNS / f"{label}.json"
    set_name = json.loads(run.read_text(encoding="utf-8"))["meta"].get("questionSet", "v1") if run.exists() else "v1"
    questions = json.loads(QUESTION_SETS[set_name].read_text(encoding="utf-8"))
    settings = get_settings()
    db = Neo4jClient.from_settings(settings)
    rows = []
    try:
        for question in questions:
            path = RECORDINGS / label / f"{question['id']}.json"
            if not path.exists():
                continue
            llm = CountingLLM(ReplayLLM.from_file(path), encoding)
            try:
                graph.ask(db, llm, question["question"], settings.agent_max_steps, "replay")
            except (RuntimeError, ToolCallRejectedError):
                pass  # recording ended early (throttled question): the turns it has are still counted
            rows.append({"id": question["id"], "turns": len(llm.prompt_tokens), "tokens": sum(llm.prompt_tokens)})
    finally:
        db.close()
    return rows


def main() -> None:
    """Print a markdown table and the average over questions that reached the model."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recordings", required=True, help="Recorded live run, e.g. live-3")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    rows = measure(args.recordings)
    used = [r for r in rows if r["turns"]]
    lines = ["| Id | Turns | Prompt tokens |", "| --- | ---: | ---: |"]
    lines += [f"| {r['id']} | {r['turns']} | {r['tokens']} |" for r in rows]
    if used:
        average = sum(r["tokens"] for r in used) / len(used)
        per_turn = sum(r["tokens"] for r in used) / sum(r["turns"] for r in used)
        specs = CountingLLM(ReplayLLM([]), tiktoken.get_encoding("o200k_base")).specs
        lines += [
            "",
            f"Average per question ({len(used)} questions that reached the model): {average:.0f} tokens; "
            + f"per turn: {per_turn:.0f}; tool specs alone: {specs} per turn.",
        ]
    sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
