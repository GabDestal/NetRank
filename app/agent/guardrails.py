"""Guardrails for LLM-generated Cypher and for the agent's scope (decision log D62-D63).

Cypher passes five independent layers; any one is enough to stop a write:
1. static text checks: one statement, no write clauses, no LOAD CSV, procedures only from an allow-list;
2. schema check: every label and relationship type must exist in the NetRank schema;
3. EXPLAIN in a READ transaction: syntax errors, write operators in the plan and the server's
   unknown-label / unknown-type notifications are rejected;
4. LIMIT enforced (appended when missing, capped when too large);
5. execution in a READ-mode transaction (the server refuses writes) with a timeout and a row cap.
"""

import re
from dataclasses import dataclass

from neo4j.exceptions import ClientError, CypherSyntaxError

from app.database.client import Neo4jClient

MAX_LIMIT = 50
TIMEOUT_SECONDS = 5.0
LABELS = frozenset({"Player", "Match", "Tournament", "Bookmaker"})
RELATIONSHIP_TYPES = frozenset({"WON", "LOST", "PART_OF", "PRICED", "BEAT", "SIMILAR_STYLE"})
ALLOWED_PROCEDURES = frozenset({"db.index.fulltext.querynodes", "db.labels", "db.relationshiptypes"})

WRITE_CLAUSES = re.compile(
    r"""\b(
        CREATE | MERGE | DELETE | DETACH | SET | REMOVE | DROP | FOREACH
      | LOAD\s+CSV | PERIODIC\s+COMMIT | IN\s+TRANSACTIONS
      | GRANT | DENY | REVOKE | ALTER | RENAME | START\s+DATABASE | STOP\s+DATABASE
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
# CALL followed by a dotted name is a procedure; CALL { or CALL ( is a subquery.
PROCEDURE_CALL = re.compile(r"\bCALL\s+([A-Za-z_][\w.]*)\s*\(", re.IGNORECASE)
NODE_LABELS = re.compile(r"\(\s*\w*\s*((?::\s*`?\w+`?\s*)+)")
REL_TYPES = re.compile(r"\[\s*\w*\s*:\s*([`\w|:\s]+?)\s*(?:\*|\{|\]|WHERE)", re.IGNORECASE)
TRAILING_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\s*$", re.IGNORECASE)
STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
# Procedure calls are covered by the allow-list (layer 1) and the READ transaction (layer 5).
WRITE_OPERATORS = ("Create", "Merge", "Delete", "Set", "Remove", "Foreach", "LoadCSV")
# GQL status codes: label / relationship type / property key does not exist.
SCHEMA_NOTIFICATIONS = {"01N50": "unknown label", "01N51": "unknown relationship type", "01N52": "unknown property key"}


class GuardrailError(ValueError):
    """Generated Cypher was rejected; `layer` names the check that stopped it."""

    def __init__(self, layer: str, message: str) -> None:
        """Keep the layer for the trace and the evaluation report."""
        super().__init__(f"[{layer}] {message}")
        self.layer = layer


@dataclass(frozen=True)
class CheckedQuery:
    """A query that passed every static and EXPLAIN check, with the LIMIT actually applied."""

    text: str
    limit: int


def strip_literals_and_comments(query: str) -> str:
    """Query text with strings and comments blanked, so keywords inside them are not matched."""
    return STRING_LITERAL.sub("''", COMMENT.sub(" ", query))


def static_check(query: str) -> str:
    """Layer 1: single statement, read-only clauses, allowed procedures. Returns the trimmed query."""
    text = query.strip().rstrip(";").strip()
    if not text:
        raise GuardrailError("static", "empty query")
    code = strip_literals_and_comments(text)
    if ";" in code:
        raise GuardrailError("static", "only one statement is allowed")
    if match := WRITE_CLAUSES.search(code):
        raise GuardrailError("static", f"write or admin clause not allowed: {match.group(1).upper()}")
    for name in PROCEDURE_CALL.findall(code):
        if name.lower() not in ALLOWED_PROCEDURES:
            raise GuardrailError("static", f"procedure not allowed: {name}")
    return text


def schema_check(query: str) -> None:
    """Layer 2: labels and relationship types must belong to the NetRank schema."""
    code = strip_literals_and_comments(query)
    labels = {name.strip(" `") for group in NODE_LABELS.findall(code) for name in group.split(":")} - {""}
    types = {name.strip(" `:") for group in REL_TYPES.findall(code) for name in group.split("|")} - {""}
    if unknown := sorted(labels - LABELS):
        raise GuardrailError("schema", f"unknown label(s) {unknown}; labels are {sorted(LABELS)}")
    if unknown := sorted(types - RELATIONSHIP_TYPES):
        known = sorted(RELATIONSHIP_TYPES)
        raise GuardrailError("schema", f"unknown relationship type(s) {unknown}; types are {known}")


def enforce_limit(query: str) -> CheckedQuery:
    """Layer 4: a trailing LIMIT no larger than MAX_LIMIT (appended when missing, lowered when larger)."""
    if match := TRAILING_LIMIT.search(query):
        limit = min(int(match.group(1)), MAX_LIMIT)
        return CheckedQuery(text=query[: match.start()] + f"LIMIT {limit}", limit=limit)
    return CheckedQuery(text=f"{query}\nLIMIT {MAX_LIMIT}", limit=MAX_LIMIT)


def operators(plan: dict) -> list[str]:
    """Operator names of a plan tree (planner suffix removed)."""
    return [plan["operatorType"].split("@")[0]] + [op for child in plan.get("children", []) for op in operators(child)]


def explain_check(db: Neo4jClient, query: str) -> None:
    """Layer 3: the server parses and plans the query in a READ transaction without running it."""
    try:
        plan, notifications = db.explain(query, {})
    except CypherSyntaxError as exc:
        raise GuardrailError("explain", f"syntax error: {exc.message}") from exc
    except ClientError as exc:
        raise GuardrailError("explain", f"rejected by the server: {exc.message}") from exc
    if writes := [op for op in operators(plan) if op.startswith(WRITE_OPERATORS)]:
        raise GuardrailError("explain", f"plan contains write operators {writes}")
    if unknown := [description for code, description in notifications if code in SCHEMA_NOTIFICATIONS]:
        raise GuardrailError("explain", "server reports: " + "; ".join(sorted(set(unknown))))


def check(db: Neo4jClient, query: str) -> CheckedQuery:
    """Layers 1-4; returns the query that may be executed."""
    text = static_check(query)
    schema_check(text)
    checked = enforce_limit(text)
    explain_check(db, checked.text)
    return checked


def run_readonly(db: Neo4jClient, query: str) -> dict:
    """Check, then execute in a READ-mode transaction with timeout and row cap (layer 5)."""
    checked = check(db, query)
    try:
        rows = db.read_only(checked.text, {}, timeout=TIMEOUT_SECONDS, max_rows=checked.limit)
    except ClientError as exc:
        raise GuardrailError("execute", f"rejected at execution: {exc.message}") from exc
    return {"cypher": checked.text, "rows": rows, "rowCount": len(rows), "limit": checked.limit}


# --------------------------------------------------------------------------- scope (decision log D65)

BETTING = re.compile(
    r"""\b(
        bet | bets | betting | wager | stake | stakes | bankroll | accumulator | parlay | punt
      | tip | tips | value\s+bet | should\s+i\s+back | which\s+side\s+to\s+back | kelly
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
ADVICE = re.compile(
    r"""\b(
        you\s+should\s+(bet|back|stake|wager) | i\s+(recommend|suggest)\s+(betting|backing|a\s+bet)
      | place\s+a\s+bet | good\s+bet | value\s+bet | worth\s+(a\s+)?bet
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)
BETTING_REFUSAL = (
    "NetRank does not give betting advice or staking recommendations. It can report the model's "
    "probability and the bookmakers' margin-free probabilities for a match, as information only."
)


def asks_for_betting_advice(question: str) -> bool:
    """True when the question asks what to bet or how much to stake."""
    return bool(BETTING.search(question))


def contains_betting_advice(text: str) -> bool:
    """True when generated text recommends a bet."""
    return bool(ADVICE.search(text))
