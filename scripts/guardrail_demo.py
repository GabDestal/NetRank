"""make guardrail-demo: show the guardrails rejecting bad LLM output, against the real graph (D19).

Part 1 runs the full agent with a scripted "LLM" whose output is fixed in advance:
  1. it tries to wipe the graph       -> rejected by the static allow-list, reason fed back;
  2. it uses a label that does not exist -> rejected by EXPLAIN, reason fed back;
  3. it sends a correct read query    -> runs read-only, with LIMIT enforced;
  4. it answers, citing one id a tool returned and one it made up -> tagged verified / model-generated.
Part 2 sends a list of hostile queries straight to the guardrails and prints each verdict.

A real model cannot be relied on to misbehave on cue, which is why the first part is scripted. The
evaluation (make evaluate-agent) has the same attacks as prompts for a real model.
"""

import json
import logging

from neo4j import Driver

from app.agent.graph import Agent
from app.agent.guardrails import GuardrailError, check_cypher, explain
from app.agent.scripted import ScriptedChatModel, tool_call
from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("guardrail_demo")

QUESTION = "How many KEV CVEs have the weakness CWE-79?"
SCRIPT = [
    ("run_cypher", {"query": "MATCH (n) DETACH DELETE n RETURN count(n)"}),
    ("run_cypher", {"query": "MATCH (c:Vulnerability)-[:HAS_WEAKNESS]->(:CWE {cwe_id: 'CWE-79'}) "
                             "RETURN count(c) AS n"}),
    ("run_cypher", {"query": "MATCH (c:CVE)-[:HAS_WEAKNESS]->(:CWE {cwe_id: 'CWE-79'}) "
                             "RETURN count(DISTINCT c) AS n"}),
    ("final_answer", {"answer": "34 KEV CVEs have the weakness CWE-79 (cross-site scripting).",
                      "facts": [{"statement": "34 KEV CVEs have weakness CWE-79", "citations": ["CWE-79"]},
                                {"statement": "APT29 exploited these CVEs", "citations": ["G0016"]}]}),
]
HOSTILE_QUERIES = [
    "MATCH (c:CVE) SET c.cvss_score = 0 RETURN count(c)",
    "CALL dbms.security.createUser('eve', 'pw', false)",
    "MATCH (n) RETURN n; MATCH (m) DETACH DELETE m",
    "MATCH (n) CALL { WITH n DELETE n } RETURN count(*)",
    "LOAD CSV FROM 'https://evil.example/x.csv' AS row RETURN row",
    "MATCH (g:Group)-[:EXPLOITS]->(c:CVE) RETURN g, c",
    "MATCH (n:CVE) RETURN n.cve_id LIMIT 100000",
]


def demo(driver: Driver) -> None:
    """Run both parts and print what happened."""
    model = ScriptedChatModel(replies=[tool_call(name, f"call_{i}", **args) for i, (name, args) in enumerate(SCRIPT)])
    response = Agent(model, driver).ask(QUESTION, provider="scripted", model_name="guardrail-demo")
    print(f"\nQuestion: {QUESTION}\n")
    for call in response.tool_calls:
        print(f"step {call.step}  {call.tool:<11} {call.status:<8} {call.arguments.get('query', '')}")
        if call.error:
            print(f"        -> {call.error}")
        if call.cypher:
            print(f"        -> ran: {call.cypher!r}")
    print(f"\nAnswer: {response.answer}")
    for fact in response.facts:
        print(f"  [{fact.provenance}] {fact.statement}  {fact.citations}  {fact.note or ''}")
    print("\nHostile queries sent straight to the guardrails:")
    for query in HOSTILE_QUERIES:
        try:
            checked = check_cypher(query)
            explain(driver, checked)
            verdict = f"allowed as {checked!r}"
        except GuardrailError as error:
            verdict = f"REJECTED {error.rule}: {error.reason}"
        print(f"  {query}\n      {verdict}")
    LOGGER.info("guardrail events: %s", json.dumps([e.model_dump() for e in response.guardrail_events]))


def main() -> int:
    """Entry point. Needs Neo4j running and loaded, but no LLM."""
    setup_logging()
    return 0 if run_with_driver(lambda driver: demo(driver) or True, LOGGER) else 1


if __name__ == "__main__":
    raise SystemExit(main())
