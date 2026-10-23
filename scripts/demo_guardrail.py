"""Guardrail demo for the defense: replay recorded model turns through the Cypher guardrails (no LLM call).

Every run_readonly_cypher call in the turns goes through the agent's own tool path (as in a live run),
which reports the layer that rejects it. Then each later layer is tried on its own, to show that a
write stopped by the first layer would still be stopped by the others (decision log D62, D73).
Finally the node and relationship counts are compared with those before the demo.

    make demo-guardrail                      # eval/demo/guardrail_turns.json (scripted turns)
    make demo-guardrail REC=eval/recordings/live-4/q21.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from neo4j.exceptions import ClientError

from app.agent import guardrails
from app.agent.tools import ToolBox
from app.config import get_settings
from app.database.client import Neo4jClient

DEFAULT = Path("eval/demo/guardrail_turns.json")
COUNTS = (
    "CALL () { MATCH (n) RETURN count(n) AS nodes } CALL () { MATCH ()-[r]->() RETURN count(r) AS rels } "
    + "RETURN nodes, rels"
)


def say(text: str = "") -> None:
    """Console output for the audience."""
    sys.stdout.write(text + "\n")


def load(path: Path) -> tuple[str, list[dict]]:
    """Source description and turns, from a demo file or a plain recording (a list of turns)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return f"recorded live turns: {path.as_posix()}", data
    return data["source"], data["turns"]


def layer_by_layer(db: Neo4jClient, query: str) -> list[tuple[str, str]]:
    """Each layer run on its own (the later ones without the earlier ones in front of them)."""
    checks = [
        ("1 static", lambda: guardrails.static_check(query)),
        ("2 schema", lambda: guardrails.schema_check(query)),
        ("3 explain", lambda: guardrails.explain_check(db, query)),
        ("5 READ transaction", lambda: db.read_only(query, {}, timeout=guardrails.TIMEOUT_SECONDS, max_rows=1)),
    ]
    verdicts = []
    for name, run in checks:
        try:
            run()
            verdicts.append((name, "passes"))
        except guardrails.GuardrailError as exc:
            verdicts.append((name, f"REJECTS: {str(exc)[:140]}"))
        except ClientError as exc:
            verdicts.append((name, f"REJECTS (server): {exc.code}"))
    return verdicts


def main() -> None:
    """Replay, report, check integrity."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recording", type=Path, default=DEFAULT, help="demo file or eval recording")
    args = parser.parse_args()
    logging.getLogger("neo4j").setLevel(logging.ERROR)  # the EXPLAIN warnings are shown by the demo itself
    source, turns = load(args.recording)
    db = Neo4jClient.from_settings(get_settings())
    try:
        before = db.read(COUNTS)[0]
        say("REPLAY (offline: no LLM is called). Source: " + source)
        toolbox = ToolBox(db)
        queries = [
            call["args"]["query"]
            for turn in turns
            for call in turn.get("tool_calls", [])
            if call["name"] == "run_readonly_cypher"
        ]
        for number, query in enumerate(queries, 1):
            say()
            say(f"[{number}] model's Cypher: {query}")
            record, _ = toolbox.call("run_readonly_cypher", {"query": query})
            if record.success:
                say(f"    pipeline: accepted, {record.result['rowCount']} row(s), run as {record.result['cypher']!r}")
            else:
                say(f"    pipeline: REJECTED by layer '{record.guardrail}': {record.error}")
            for name, verdict in layer_by_layer(db, query):
                say(f"      layer {name:<20} {verdict}")
        after = db.read(COUNTS)[0]
        say()
        say(f"Graph before: {before}; after: {after}; unchanged: {before == after}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
