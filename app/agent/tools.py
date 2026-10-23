"""Tools the agent can call: typed wrappers around the API services first, guarded Cypher last.

Every call is recorded in the trace with a short id (t1, t2, ...) that claims cite as their source.
Player ids are accepted only once resolved: returned by an unambiguous search_player, or present in
an earlier tool result. Ids the LLM invents, or picks from an ambiguous search, are refused
(decision log D61).
"""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agent import guardrails
from app.agent.schema import DraftAnswer, ToolCallRecord
from app.config import get_settings
from app.database.client import Neo4jClient
from app.errors import GdsUnavailableError, InvalidRequestError, NotFoundError
from app.models.players import Surface
from app.services import analytics, graph, players, predict
from app.text import fold

LLM_LIST_LIMIT = 5
BIOGRAPHY = frozenset({"hand", "dob", "height", "wikidataId"})
# Fields the model does not need for any question, per tool; list sizes where 5 items are too few.
LLM_OMIT = {
    "similar_players": frozenset({"features"}),
    "list_styles": frozenset({"feature"}),
    "get_style": frozenset({"feature"}),
    "predict_match": frozenset({"modelVersion"}),
}
LLM_LIMITS = {"list_styles": 10}
MAX_CYPHER_REJECTIONS = 2

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- argument schemas


class NameArgs(BaseModel):
    """search_player arguments."""

    name: str = Field(description="A player's name or part of it, as written by the user.")


class PlayerArgs(BaseModel):
    """One resolved player."""

    player_id: int = Field(description="Id returned by search_player.")


class PairArgs(BaseModel):
    """Two resolved players."""

    player1_id: int
    player2_id: int


class ChainArgs(BaseModel):
    """beat_chain arguments."""

    from_id: int = Field(description="Player at the start of the chain (the one who beat the next).")
    to_id: int
    max_hops: int = Field(default=4, ge=1, le=6)


class PrestigeArgs(BaseModel):
    """prestige arguments."""

    player_id: int
    era: str | None = Field(default=None, description="'2000s', '2004-2008' or '2010'; omit for all-time.")


class BoardArgs(BaseModel):
    """prestige_leaderboard arguments."""

    era: str | None = Field(default=None, description="'1990s', '2004-2008'...; omit for all-time.")
    size: int = Field(default=5, ge=1, le=10)


class StyleArgs(BaseModel):
    """get_style arguments."""

    style_id: int = Field(ge=1)


class PredictArgs(BaseModel):
    """predict_match arguments."""

    player1_id: int
    player2_id: int
    surface: Surface | None = Field(default=None, description="Required unless match_id is given.")
    match_id: str | None = Field(default=None, description="A past match between the two players.")


class CypherArgs(BaseModel):
    """run_readonly_cypher arguments."""

    query: str = Field(description="One read-only Cypher query using only the NetRank schema.")


class NoArgs(BaseModel):
    """Tools without arguments."""


TOOL_DESCRIPTIONS = {
    "search_player": "Resolve a player name to an id. Call before any tool that takes a player id.",
    "get_player": "Career record: matches, wins, losses, titles, best rank, per surface.",
    "head_to_head": "Meetings between two players, overall and per surface.",
    "nemesis": "Opponents who beat a player most often; non-transitive triangles.",
    "beat_chain": "Shortest chain from one player to another where each beat the next.",
    "prestige": "PageRank prestige score and rank, all-time or in an era.",
    "prestige_leaderboard": "Most prestigious players, all-time or in an era.",
    "similar_players": "Players with the most similar playing style.",
    "list_styles": "Playing-style communities and their traits.",
    "get_style": "One style community: traits and best-known members.",
    "predict_match": "Model probability that player 1 beats player 2; with match_id also odds and result.",
    "run_readonly_cypher": "LAST RESORT when no other tool answers. Read-only Cypher. Labels: Player, Match, "
    + "Tournament, Bookmaker. Relationships: (Player)-[:WON|LOST]->(Match)-[:PART_OF]->(Tournament), "
    + "(Bookmaker)-[:PRICED]->(Match), (Player)-[:BEAT]->(Player), SIMILAR_STYLE. Example: MATCH (w:Player)-[:WON]->"
    + "(m:Match {round: 'F'})-[:PART_OF]->(t:Tournament {name: 'Wimbledon', year: 2019}) RETURN w.name, m.score",
    "submit_answer": "Finish with the structured answer. Call exactly once, at the end.",
}

TOOL_ARGS: dict[str, type[BaseModel]] = {
    "search_player": NameArgs,
    "get_player": PlayerArgs,
    "head_to_head": PairArgs,
    "nemesis": PlayerArgs,
    "beat_chain": ChainArgs,
    "prestige": PrestigeArgs,
    "prestige_leaderboard": BoardArgs,
    "similar_players": PlayerArgs,
    "list_styles": NoArgs,
    "get_style": StyleArgs,
    "predict_match": PredictArgs,
    "run_readonly_cypher": CypherArgs,
    "submit_answer": DraftAnswer,
}


def compact_schema(node: Any) -> Any:
    """JSON schema without what the model does not need: titles, model docstrings, null defaults.

    `anyOf: [X, null]` becomes X with a nullable type. The tool specs are sent on every turn, so
    this is most of the prompt-size cut of decision log D72.
    """
    if isinstance(node, list):
        return [compact_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    out = {key: compact_schema(value) for key, value in node.items()
           if key != "title" and not (key == "description" and "properties" in node)
           and not (key == "default" and value is None)}
    options = out.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options:
        kept = dict(next(option for option in options if option != {"type": "null"}))
        if "enum" in kept:
            kept["enum"] = [*kept["enum"], None]
        if isinstance(kept.get("type"), str):
            kept["type"] = [kept["type"], "null"]
        out = {**{k: v for k, v in out.items() if k != "anyOf"}, **kept}
    return out


def tool_specs() -> list[dict]:
    """OpenAI-style function specs for bind_tools (also used by the scripted test LLM)."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": compact_schema(schema.model_json_schema()),
            },
        }
        for name, schema in TOOL_ARGS.items()
    ]


def ids_in(value: Any) -> set[int]:
    """Every integer stored under an 'id' / '...Id' key of a tool result (players it mentions)."""
    found: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if (key == "id" or key.endswith("Id")) and isinstance(item, int):
                found.add(item)
            else:
                found |= ids_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= ids_in(item)
    return found


def names_in(value: Any) -> list[str]:
    """Every string stored under a 'name' key of a tool result."""
    if isinstance(value, dict):
        own = [value["name"]] if isinstance(value.get("name"), str) else []
        return own + [n for key, item in value.items() if key != "name" for n in names_in(item)]
    if isinstance(value, list):
        return [n for item in value for n in names_in(item)]
    return []


def trim_for_llm(value: Any, omit: frozenset[str] = frozenset(), limit: int = LLM_LIST_LIMIT, depth: int = 0) -> Any:
    """What the LLM sees of a result; the trace (and so the verifier) keeps the full result.

    Lists are cut to `limit` items, null values dropped, floats rounded to 4 decimals (the verifier
    rounds the full value to the precision the model writes, so cited numbers still match), player
    biography fields dropped below the top level, and the tool's `omit` keys left out (decision log D72).
    """
    if isinstance(value, dict):
        hidden = omit | (BIOGRAPHY if depth else frozenset())
        return {key: trim_for_llm(item, omit, limit, depth + 1) for key, item in value.items()
                if key not in hidden and item is not None}
    if isinstance(value, list):
        trimmed = [trim_for_llm(item, omit, limit, depth + 1) for item in value[:limit]]
        return trimmed + ([f"... {len(value) - limit} more"] if len(value) > limit else [])
    if isinstance(value, float):
        return round(value, 4)
    return value


class ToolBox:
    """Executes tool calls for one question and keeps the trace and resolution state."""

    def __init__(self, db: Neo4jClient, question: str = "") -> None:
        """Fresh state per question; the question text bounds which names may be searched."""
        self._db = db
        self.question_words = set(re.findall(r"[a-z0-9]+", fold(question)))
        self.trace: list[ToolCallRecord] = []
        self.resolved: set[int] = set()
        self.ambiguous: set[int] = set()
        self.cypher_rejections = 0
        self.fallback_calls = 0
        self.handlers: dict[str, Callable[[Any], Any]] = {
            "search_player": self.search_player,
            "get_player": lambda a: players.profile(self._db, self.player(a.player_id)),
            "head_to_head": lambda a: graph.head_to_head(
                self._db, self.player(a.player1_id), self.player(a.player2_id)
            ),
            "nemesis": lambda a: graph.nemesis(
                self._db, self.player(a.player_id), {"minWins": 2, "triangles": 3}, 1, 5
            ),
            "beat_chain": lambda a: graph.beat_chain(
                self._db, self.player(a.from_id), self.player(a.to_id), a.max_hops
            ),
            "prestige": lambda a: analytics.player_prestige(
                self._db, self.player(a.player_id), analytics.parse_era(a.era)
            ),
            "prestige_leaderboard": lambda a: analytics.prestige_board(self._db, analytics.parse_era(a.era), 1, a.size),
            "similar_players": lambda a: analytics.similar(
                self._db, self.player(a.player_id), 1, 5, get_settings().style_min_matches
            ),
            "list_styles": lambda a: analytics.styles(self._db, 1, 20),
            "get_style": lambda a: analytics.style(self._db, a.style_id, 1, 5),
            "predict_match": lambda a: predict.predict(
                self._db, self.player(a.player1_id), self.player(a.player2_id), a.surface, a.match_id
            ),
            "run_readonly_cypher": self.run_cypher,
        }

    # ------------------------------------------------------------------ resolution

    def player(self, player_id: int) -> int:
        """Accept only resolved ids; explain what to do otherwise."""
        if player_id in self.ambiguous and player_id not in self.resolved:
            raise InvalidRequestError(
                f"player id {player_id} came from an ambiguous search: ask the user which player they mean"
            )
        if player_id not in self.resolved:
            raise InvalidRequestError(f"player id {player_id} has not been resolved: call search_player first")
        return player_id

    def known_words(self) -> set[str]:
        """Words the agent may use in a search: the question's, plus player names returned so far."""
        names = [n for r in self.trace if r.success for n in names_in(r.result)]
        return self.question_words | {w for name in names for w in re.findall(r"[a-z0-9]+", fold(name))}

    def search_player(self, args: NameArgs) -> dict:
        """Unique when exactly one hit or an exact full-name match; otherwise ambiguous (never guessed).

        The name must use only words from the question or from earlier results: in live runs the model
        expanded "Zverev" to "Alexander Zverev" by itself, which is a guess (decision log D61).
        """
        if self.question_words:
            extra = sorted(set(re.findall(r"[a-z0-9]+", fold(args.name))) - self.known_words())
            if extra:
                raise InvalidRequestError(
                    f"search with the name exactly as the user wrote it; {extra} is not in the question. "
                    + "If that search is ambiguous, ask the user which player they mean"
                )
        page = players.search(self._db, args.name, 1, 5)
        candidates = [{"id": h.id, "name": h.name, "ioc": h.ioc} for h in page.items]
        exact = [c for c in candidates if fold(c["name"]) == fold(args.name)]
        if len(exact) == 1 or len(candidates) == 1 and page.total == 1:
            chosen = exact[0] if exact else candidates[0]
            self.resolved.add(chosen["id"])
            return {"status": "unique", "query": args.name, "player": chosen}
        if not candidates:
            return {"status": "not_found", "query": args.name, "candidates": []}
        self.ambiguous |= {c["id"] for c in candidates}
        return {"status": "ambiguous", "query": args.name, "totalMatches": page.total, "candidates": candidates}

    # ------------------------------------------------------------------ fallback Cypher

    def run_cypher(self, args: CypherArgs) -> dict:
        """Guarded read-only Cypher; after MAX_CYPHER_REJECTIONS rejections the tool is closed."""
        if self.cypher_rejections >= MAX_CYPHER_REJECTIONS:
            raise guardrails.GuardrailError("retry", "Cypher was rejected twice: answer without it or report failure")
        self.fallback_calls += 1
        log.info(f"agent fallback Cypher used: {args.query!r}")
        try:
            return guardrails.run_readonly(self._db, args.query)
        except guardrails.GuardrailError:
            self.cypher_rejections += 1
            raise

    # ------------------------------------------------------------------ dispatch

    def call(self, name: str, raw_args: dict) -> tuple[ToolCallRecord, str]:
        """Run one tool call; returns its trace record and the JSON content shown to the LLM."""
        call_id = f"t{len(self.trace) + 1}"
        record = ToolCallRecord(id=call_id, tool=name, arguments=raw_args, success=False)
        try:
            if name not in self.handlers:
                raise InvalidRequestError(f"unknown tool {name}")
            args = TOOL_ARGS[name].model_validate(raw_args)
            result = self.handlers[name](args)
            data = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
            record.success, record.result = True, data
            self.resolved |= ids_in(data) - (self.ambiguous if name == "search_player" else set())
            shown = trim_for_llm(data, LLM_OMIT.get(name, frozenset()), LLM_LIMITS.get(name, LLM_LIST_LIMIT))
            content = {"toolCallId": call_id, "result": shown}
        except guardrails.GuardrailError as exc:
            record.error, record.guardrail = str(exc), exc.layer
            content = {"toolCallId": call_id, "error": f"Guardrail rejected the query: {exc}"}
        except (ValidationError, InvalidRequestError, NotFoundError, GdsUnavailableError) as exc:
            record.error = str(exc).splitlines()[0][:300]
            content = {"toolCallId": call_id, "error": record.error}
        self.trace.append(record)
        return record, json.dumps(content, default=str)

    def record_rejection(self, message: str) -> None:
        """Keep a provider-rejected model output in the trace (it produced no tool call)."""
        call_id = f"t{len(self.trace) + 1}"
        self.trace.append(ToolCallRecord(id=call_id, tool="(rejected model output)", arguments={}, success=False,
                                         error=message[:500]))

    def record_recovery(self, tool: str, payload: dict) -> None:
        """Keep, next to the rejection, that its payload was accepted as the answer (decision log D71)."""
        call_id = f"t{len(self.trace) + 1}"
        self.trace.append(ToolCallRecord(id=call_id, tool=f"(recovered answer sent to '{tool}')", arguments=payload,
                                         success=True))

    def results_by_id(self) -> dict[str, ToolCallRecord]:
        """Trace records keyed by call id."""
        return {record.id: record for record in self.trace}
