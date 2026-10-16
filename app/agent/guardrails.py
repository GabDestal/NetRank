"""Guardrails for Cypher written by the LLM (D19).

Generated Cypher is only the agent's fallback, used when no fixed tool fits. A query runs only if it
passes, in order:

1. static checks: one statement, starts with a read clause, no write or admin keyword, no CALL at all;
2. a LIMIT of at most MAX_ROWS, added when missing and lowered when too high;
3. EXPLAIN on the server: valid syntax, labels, relationship types and properties that exist, and a
   plan Neo4j itself classifies as read-only;

and then it runs in a READ transaction with a timeout, keeping at most MAX_ROWS rows.
"""

import re
from dataclasses import dataclass
from typing import Any

from neo4j import READ_ACCESS, Driver, Query
from neo4j.exceptions import ClientError, CypherSyntaxError, Neo4jError

MAX_ROWS = 50
TIMEOUT_SECONDS = 10.0
MAX_QUERY_LENGTH = 2000

# Clauses a query may start with. Anything else (CREATE, SHOW, CALL, USE, LOAD CSV...) is rejected.
READ_STARTS = ("MATCH", "OPTIONAL MATCH", "WITH", "UNWIND", "RETURN")
# Keywords that write, run procedures or administer the server. CALL is banned entirely, not only
# CALL dbms.*: it also covers apoc.* and gds.* procedures that can write, and CALL { } subqueries.
FORBIDDEN_KEYWORDS = ("CREATE", "MERGE", "DELETE", "DETACH", "SET", "REMOVE", "DROP", "CALL", "LOAD", "FOREACH",
                      "USE", "GRANT", "DENY", "REVOKE", "ALTER", "RENAME", "TERMINATE", "UNION")

# String literals, quoted identifiers and comments are blanked before keyword checks, so a CVE name
# containing "Remote Code Execution" or a comment saying "delete" does not trigger a false rejection.
_LITERALS = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`[^`]*`|//[^\n]*|/\*.*?\*/", re.DOTALL)
# A word preceded by "." or "$" is a property or parameter name (n.set, $delete), not a keyword.
_WORDS = re.compile(r"(?<![.$\w])[A-Za-z_]+")
_TRAILING_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\s*$", re.IGNORECASE)
# Server notifications that mean the query refers to something the graph does not have.
_UNKNOWN_CODES = ("UnknownLabelWarning", "UnknownRelationshipTypeWarning", "UnknownPropertyKeyWarning")
_MISSING = re.compile(r"the missing (label|relationship type|property)(?: name)? is: ([^)]+)\)")


class GuardrailError(Exception):
    """A generated query was rejected. `rule` names the check that failed, `reason` is fed back to the LLM."""

    def __init__(self, rule: str, reason: str):
        super().__init__(f"{rule}: {reason}")
        self.rule = rule
        self.reason = reason


@dataclass(frozen=True)
class CypherResult:
    """Rows returned by a guarded query, with the query text that actually ran."""

    query: str
    rows: list[dict[str, Any]]


def string_literals(query: str) -> list[str]:
    """The quoted string values in a query, e.g. ['CWE-79'] for {cwe_id: 'CWE-79'}."""
    return [m.group(0)[1:-1] for m in _LITERALS.finditer(query) if m.group(0)[0] in "'\""]


def _blank_literals(query: str) -> str:
    """Replace string literals, quoted names and comments with blanks of the same kind."""
    return _LITERALS.sub(lambda m: "''" if m.group(0)[0] in "'\"" else " ", query)


def check_cypher(query: str) -> str:
    """Run the static checks and return the query with its LIMIT enforced. Raises GuardrailError."""
    query = query.strip().rstrip(";").strip()
    if not query:
        raise GuardrailError("empty", "the query is empty")
    if len(query) > MAX_QUERY_LENGTH:
        raise GuardrailError("too_long", f"the query is longer than {MAX_QUERY_LENGTH} characters")
    code = _blank_literals(query)
    if ";" in code:
        raise GuardrailError("multiple_statements", "only one statement is allowed")
    normalized = " ".join(code.split()).upper()
    if not normalized.startswith(READ_STARTS):
        raise GuardrailError("not_a_read_clause", f"the query must start with one of {', '.join(READ_STARTS)}")
    found = sorted({w.upper() for w in _WORDS.findall(code)} & set(FORBIDDEN_KEYWORDS))
    if found:
        raise GuardrailError("forbidden_keyword", f"read-only queries cannot use {', '.join(found)}")
    if not re.search(r"\bRETURN\b", normalized):
        raise GuardrailError("no_return", "the query must end with a RETURN clause")
    return _enforce_limit(query, normalized)


def _enforce_limit(query: str, normalized: str) -> str:
    """Add LIMIT MAX_ROWS, or lower a larger literal LIMIT. A non-literal final LIMIT is rejected."""
    trailing = _TRAILING_LIMIT.search(query)
    if trailing:
        if int(trailing.group(1)) <= MAX_ROWS:
            return query
        return query[:trailing.start(1)] + str(MAX_ROWS)
    if re.search(r"\bLIMIT\b", normalized[normalized.rfind("RETURN"):]):
        raise GuardrailError("limit_not_literal", "the final LIMIT must be a plain integer")
    return f"{query}\nLIMIT {MAX_ROWS}"


def explain(driver: Driver, query: str, parameters: dict[str, Any] | None = None) -> None:
    """Ask Neo4j to plan the query without running it. Raises GuardrailError if the plan is not acceptable.

    EXPLAIN catches what the static checks cannot: syntax errors, labels, relationship types or
    properties the graph does not have, and any plan the server itself does not classify as read-only ("r").
    """
    with driver.session(default_access_mode=READ_ACCESS, notifications_min_severity="WARNING",
                        notifications_disabled_categories=[]) as session:
        try:
            summary = session.run("EXPLAIN " + query, parameters or {}).consume()
        except CypherSyntaxError as error:
            raise GuardrailError("explain_syntax", error.message or "invalid Cypher") from error
        except Neo4jError as error:
            raise GuardrailError("explain_failed", error.message or "EXPLAIN failed") from error
    if summary.query_type != "r":
        raise GuardrailError("explain_not_read_only", f"Neo4j plans this query as type {summary.query_type!r}, "
                                                      "only read-only ('r') queries are allowed")
    unknown = [_short_unknown(n.get("description", "")) for n in summary.notifications or []
               if n.get("code", "").endswith(_UNKNOWN_CODES)]
    if unknown:
        raise GuardrailError("explain_unknown_schema", "; ".join(unknown) + " (not in the graph schema)")


def _short_unknown(description: str) -> str:
    """Turn Neo4j's long 'not available in the database' text into e.g. 'unknown label: Vulnerability'."""
    found = _MISSING.search(description)
    return f"unknown {found.group(1)}: {found.group(2)}" if found else description


def run_guarded(driver: Driver, query: str, parameters: dict[str, Any] | None = None) -> CypherResult:
    """Check, EXPLAIN, then run a generated query read-only with a timeout. Raises GuardrailError."""
    checked = check_cypher(query)
    explain(driver, checked, parameters)
    with driver.session(default_access_mode=READ_ACCESS) as session:
        try:
            result = session.run(Query(checked, timeout=TIMEOUT_SECONDS), parameters or {})
            rows = [record.data() for record in result.fetch(MAX_ROWS)]
            result.consume()
        except ClientError as error:
            if "TimedOut" in (error.code or ""):
                raise GuardrailError("timeout", f"the query ran longer than {TIMEOUT_SECONDS:g} s") from error
            raise GuardrailError("runtime_error", error.message or "the query failed") from error
    return CypherResult(query=checked, rows=rows)
