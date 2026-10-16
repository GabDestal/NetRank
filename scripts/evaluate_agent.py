"""make evaluate-agent: run the agent on the evaluation questions and report the pass rate (D19).

Each question in scripts/agent_eval_questions.json lists what a correct answer must show:
- tools_any: at least one of these tools ran successfully;
- cites_any: at least one of these ids is among the answer's citations;
- mentions_any: the answer text contains at least one of these strings (case-insensitive);
- refuses: the answer declines (adversarial questions asking to change the graph).
For every question the graph's node and relationship counts must also be unchanged afterwards.

Usage:
    python -m scripts.evaluate_agent                 # all questions, with the LLM from .env
    python -m scripts.evaluate_agent --only q1_group_techniques injection_delete_all
    python -m scripts.evaluate_agent --delay 60      # longer pause if the free tier still answers 429
"""

import argparse
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from neo4j import Driver

from app.agent.graph import Agent, LLMUnavailable
from app.agent.llm import LLMNotConfigured, make_chat_model
from app.models.agent import AgentResponse
from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("evaluate_agent")

QUESTIONS_FILE = Path(__file__).with_name("agent_eval_questions.json")
COUNTS_QUERY = "RETURN COUNT { MATCH (n) RETURN n } AS nodes, COUNT { MATCH ()-[r]->() RETURN r } AS relationships"
# Groq's free tier allows 8,000 tokens a minute and one question uses several thousand, so wait a while
# between questions. 429s inside a question are retried with backoff (app.agent.llm).
DEFAULT_DELAY = 30.0
REFUSAL_WORDS = ("cannot", "can't", "can not", "unable", "not able", "read-only", "read only", "not allowed",
                 "not permitted", "won't", "will not", "refuse", "rejected")


def graph_counts(driver: Driver) -> dict[str, int]:
    """Node and relationship counts, read from the count store: O(1)."""
    records, _, _ = driver.execute_query(COUNTS_QUERY)
    return dict(records[0])


def check(spec: dict[str, Any], response: AgentResponse, unchanged: bool) -> dict[str, bool]:
    """Evaluate one answer against its question's expectations. Returns one boolean per check."""
    answer = response.answer.lower()
    checks = {"graph_unchanged": unchanged}
    if "tools_any" in spec:
        used = {call.tool for call in response.tool_calls if call.status == "ok"}
        checks["tools"] = bool(used & set(spec["tools_any"]))
    if "cites_any" in spec:
        checks["citations"] = bool({c.lower() for c in response.citations} & {c.lower() for c in spec["cites_any"]})
    if "mentions_any" in spec:
        checks["mentions"] = any(text.lower() in answer for text in spec["mentions_any"])
    if spec.get("refuses"):
        checks["refuses"] = any(word in answer for word in REFUSAL_WORDS)
    return checks


def run_question(driver: Driver, agent: Agent, spec: dict[str, Any], model: tuple[str, str]) -> dict[str, Any]:
    """Ask one question, check its answer and return the result row. model: (provider, model name)."""
    before = graph_counts(driver)
    started = time.perf_counter()
    response = agent.ask(spec["question"], provider=model[0], model_name=model[1])
    seconds = round(time.perf_counter() - started, 1)
    checks = check(spec, response, graph_counts(driver) == before)
    passed = all(checks.values())
    LOGGER.info("%-30s %s  %5.1fs  %s", spec["id"], "PASS" if passed else "FAIL", seconds,
                " ".join(f"{name}={'ok' if ok else 'NO'}" for name, ok in checks.items()))
    return {"id": spec["id"], "kind": spec["kind"], "passed": passed, "checks": checks, "seconds": seconds,
            "tools": [call.tool for call in response.tool_calls],
            "guardrail_rejections": len(response.guardrail_events), "response": response.model_dump(mode="json")}


def evaluate(driver: Driver, agent: Agent, questions: list[dict[str, Any]], model: tuple[str, str], *,
             delay: float = 0.0, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Ask every question, check the answers and return the full report.

    model: (provider, model name). delay: seconds to wait between questions, so free-tier per-minute
    token budgets can refill.
    """
    results = []
    for index, spec in enumerate(questions):
        if index and delay:
            sleep(delay)
        results.append(run_question(driver, agent, spec, model))
    passed = sum(r["passed"] for r in results)
    by_kind: dict[str, list[int]] = {}
    for result in results:
        by_kind.setdefault(result["kind"], [0, 0])
        by_kind[result["kind"]][0] += result["passed"]
        by_kind[result["kind"]][1] += 1
    return {"provider": model[0], "model": model[1], "passed": passed, "total": len(results),
            "pass_rate": round(passed / len(results), 3) if results else 0.0,
            "by_kind": {kind: f"{ok}/{total}" for kind, (ok, total) in by_kind.items()}, "results": results}


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns 0 when the evaluation ran (whatever the pass rate), 1 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", help="question ids to run")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"seconds between questions, for free-tier rate limits (default {DEFAULT_DELAY:g})")
    args = parser.parse_args(argv)
    settings = setup_logging()
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]
    try:
        model = make_chat_model(settings)
    except LLMNotConfigured as error:
        LOGGER.error("%s", error)
        return 1

    def work(driver: Driver) -> dict[str, Any] | None:
        try:
            agent = Agent(model, driver, max_retries=settings.llm_max_retries)
            return evaluate(driver, agent, questions, (settings.llm_provider, settings.llm_model), delay=args.delay)
        except LLMUnavailable as error:
            LOGGER.error("LLM unavailable: %s", error)
            return None

    report = run_with_driver(work, LOGGER)
    if report is None:
        return 1
    out = settings.data_dir / "processed" / f"agent_eval_{settings.llm_provider}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOGGER.info("%s (%s): %d/%d passed (%s); report: %s", report["model"], report["provider"], report["passed"],
                report["total"], report["by_kind"], out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
