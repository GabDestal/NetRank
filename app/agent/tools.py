"""Tools the agent can call: typed wrappers around the API services first, guarded Cypher last.

Every call is recorded in the trace with a short id (t1, t2, ...) that claims cite as their source.
Player ids are accepted only once resolved: returned by an unambiguous search_player, or present in
an earlier tool result. Ids the LLM invents, or picks from an ambiguous search, are refused
(decision log D61).
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agent import guardrails
from app.agent.schema import AgentAnswer, ToolCallRecord
from app.config import get_settings
from app.database.client import Neo4jClient
from app.errors import GdsUnavailableError, InvalidRequestError, NotFoundError
from app.models.players import Surface
from app.services import analytics, graph, players, predict
from app.text import fold

LLM_LIST_LIMIT = 10
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
    "search_player": "Resolve a player name to an id. Always call this before any tool that takes a player id.",
    "get_player": "Career record: matches, wins, losses, titles, best rank, record per surface.",
    "head_to_head": "Every meeting between two players with overall and per-surface records.",
    "nemesis": "Opponents who beat a player most often, and non-transitive triangles through the player.",
    "beat_chain": "Shortest chain from one player to another where each player beat the next.",
    "prestige": "PageRank prestige score and rank of a player, all-time or within an era.",
    "prestige_leaderboard": "Most prestigious players, all-time or within an era.",
    "similar_players": "Players with the most similar playing style (serve/return statistics).",
    "list_styles": "Playing-style communities with their traits.",
    "get_style": "One playing-style community: traits and best-known members.",
    "predict_match": "Model probability that player 1 beats player 2; with match_id also bookmaker odds and result.",
    "run_readonly_cypher": "LAST RESORT for questions no other tool answers. Read-only Cypher over labels "
    + "Player, Match, Tournament, Bookmaker and relationships WON, LOST, PART_OF, PRICED, BEAT, SIMILAR_STYLE. "
    + "Writes are rejected. Example: MATCH (w:Player)-[:WON]->(m:Match {round: 'F'})-[:PART_OF]->"
    + "(t:Tournament {name: 'Wimbledon', year: 2019}) RETURN w.name, m.score",
    "submit_answer": "Finish: give the structured answer. Call exactly once, at the end.",
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
    "submit_answer": AgentAnswer,
}


def tool_specs() -> list[dict]:
    """OpenAI-style function specs for bind_tools (also used by the scripted test LLM)."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": schema.model_json_schema(),
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


def trim_for_llm(value: Any) -> Any:
    """Copy of a result with long lists cut to LLM_LIST_LIMIT items (the trace keeps everything)."""
    if isinstance(value, dict):
        return {key: trim_for_llm(item) for key, item in value.items()}
    if isinstance(value, list):
        trimmed = [trim_for_llm(item) for item in value[:LLM_LIST_LIMIT]]
        return trimmed + ([f"... {len(value) - LLM_LIST_LIMIT} more"] if len(value) > LLM_LIST_LIMIT else [])
    return value


class ToolBox:
    """Executes tool calls for one question and keeps the trace and resolution state."""

    def __init__(self, db: Neo4jClient) -> None:
        """Fresh state per question."""
        self._db = db
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

    def search_player(self, args: NameArgs) -> dict:
        """Unique when exactly one hit or an exact full-name match; otherwise ambiguous (never guessed)."""
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
            content = {"toolCallId": call_id, "result": trim_for_llm(data)}
        except guardrails.GuardrailError as exc:
            record.error, record.guardrail = str(exc), exc.layer
            content = {"toolCallId": call_id, "error": f"Guardrail rejected the query: {exc}"}
        except (ValidationError, InvalidRequestError, NotFoundError, GdsUnavailableError) as exc:
            record.error = str(exc).splitlines()[0][:300]
            content = {"toolCallId": call_id, "error": record.error}
        self.trace.append(record)
        return record, json.dumps(content, default=str)

    def results_by_id(self) -> dict[str, ToolCallRecord]:
        """Trace records keyed by call id."""
        return {record.id: record for record in self.trace}
