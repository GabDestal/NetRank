"""Tools the agent can call (D19).

Fixed tools wrap the same service functions as the API endpoints, so the agent and the API give the
same answers. `run_cypher` is the guarded fallback for questions no fixed tool covers.

Every tool returns a ToolOutput: compact data for the LLM, the graph path it walked, and the ids it
returned, split into verified ids (from ATT&CK, KEV, NVD, CTID, or computed from them) and
model-generated ids (D18 suggestions). The agent uses those sets to tag each fact in its answer.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from neo4j import Driver, RoutingControl
from pydantic import BaseModel, Field, ValidationError

from app.agent.guardrails import MAX_ROWS, run_guarded, string_literals
from app.models.common import CVE_ID_PATTERN, GROUP_ID_PATTERN, TECHNIQUE_ID_PATTERN
from app.services import analytics, cves, groups, products, techniques

ID_KEYS = ("attack_id", "cve_id", "product_key", "vendor_key", "cwe_id")
# Lists longer than this are cut in what the LLM sees (the full list still feeds citations).
LIST_CAP = 25
TEXT_CAP = 300

# Name or alias lookup across the main node types. Each branch is a label scan with CONTAINS, O(n) on
# at most ~3,600 nodes (products), and returns at most $limit rows, exact names first.
SEARCH_QUERY = """
MATCH (n) WHERE (n:Group OR n:Software OR n:Campaign)
  AND (toLower(n.name) CONTAINS $term OR any(a IN coalesce(n.aliases, []) WHERE toLower(a) CONTAINS $term))
RETURN labels(n)[0] AS kind, n.attack_id AS id, n.name AS name, toLower(n.name) = $term AS exact
ORDER BY exact DESC, size(n.name) LIMIT $limit
UNION ALL
MATCH (n) WHERE (n:Technique OR n:Mitigation OR n:Tactic)
  AND (toLower(n.name) CONTAINS $term OR toLower(n.attack_id) = $term)
RETURN labels(n)[0] AS kind, n.attack_id AS id, n.name AS name, toLower(n.name) = $term AS exact
ORDER BY exact DESC, size(n.name) LIMIT $limit
UNION ALL
MATCH (p:Product) WHERE p.product_key CONTAINS $term OR toLower(p.name) CONTAINS $term
RETURN 'Product' AS kind, p.product_key AS id, p.name AS name, toLower(p.name) = $term AS exact
ORDER BY exact DESC, COUNT { (p)<-[:AFFECTS]-() } DESC LIMIT $limit
UNION ALL
MATCH (c:CVE) WHERE toLower(c.name) CONTAINS $term OR toLower(c.cve_id) = $term
RETURN 'CVE' AS kind, c.cve_id AS id, c.name AS name, toLower(c.cve_id) = $term AS exact
ORDER BY exact DESC, c.cvss_score DESC LIMIT $limit
"""

GRAPH_SCHEMA = """Nodes (key property first):
Group(attack_id G####, name, aliases), Campaign(attack_id C####, name), Software(attack_id S####, name),
Technique(attack_id T#### or T####.###, name, is_subtechnique, used_by_groups, betweenness, community),
Tactic(attack_id, name, shortname, order), Mitigation(attack_id M####, name),
CVE(cve_id, name, cvss_score, cvss_severity, date_added (date), known_ransomware_use (bool), kev_vendor,
kev_product, ssvc_exploitation, ssvc_automatable, ssvc_technical_impact), CWE(cwe_id CWE-###),
Product(product_key vendor:product, name, part), Vendor(vendor_key, name).
Relationships:
(Group|Campaign|Software)-[:USES]->(Technique), (Group|Campaign)-[:USES]->(Software),
(Campaign)-[:ATTRIBUTED_TO]->(Group), (Technique)-[:SUBTECHNIQUE_OF]->(Technique),
(Technique)-[:IN_TACTIC]->(Tactic), (Mitigation)-[:MITIGATES]->(Technique),
(CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(Technique) (verified CTID mappings),
(CVE)-[:HAS_WEAKNESS]->(CWE), (CVE)-[:AFFECTS]->(Product), (Product)-[:MADE_BY]->(Vendor).
Groups never link to CVEs directly: only through a shared technique (an association, not exploitation)."""


@dataclass
class ToolOutput:
    """What one tool call produced."""

    data: Any
    path: str
    source: str
    verified_ids: set[str] = field(default_factory=set)
    inferred_ids: set[str] = field(default_factory=set)
    cypher: str | None = None
    rows: int | None = None


class ToolFailure(Exception):
    """A tool could not answer (unknown id, invalid arguments). The message is fed back to the LLM."""


def collect_ids(value: Any) -> set[str]:
    """Return every graph id (ATT&CK id, CVE id, product, vendor or CWE key) found in a nested result."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ID_KEYS and isinstance(item, str):
                found.add(item)
            else:
                found |= collect_ids(item)
    elif isinstance(value, list):
        for item in value:
            found |= collect_ids(item)
    return found


def compact(value: Any) -> Any:
    """Shorten a result for the LLM: long lists are cut with a count of what was left out, long text trimmed."""
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items()}
    if isinstance(value, list):
        items = [compact(item) for item in value[:LIST_CAP]]
        if len(value) > LIST_CAP:
            items.append(f"... {len(value) - LIST_CAP} more not shown")
        return items
    if isinstance(value, str) and len(value) > TEXT_CAP:
        return value[:TEXT_CAP] + "..."
    if isinstance(value, date):
        return value.isoformat()
    return value


# Argument schemas. Their JSON schema is what the LLM sees, so descriptions matter.
class SearchArgs(BaseModel):
    """Find graph ids by name or alias: groups, software, campaigns, techniques, mitigations, tactics,
    products and CVEs. Use it first whenever the question names something without its id."""

    text: str = Field(min_length=2, max_length=80, description="Name, alias or part of it, e.g. 'Cozy Bear'")


class GroupArgs(BaseModel):
    """Question 1: the techniques an ATT&CK group uses, their tactics and the mitigations covering them."""

    group_id: str = Field(pattern=GROUP_ID_PATTERN, description="ATT&CK group id, e.g. G0016")


class TechniqueCvesArgs(BaseModel):
    """Question 2: actively exploited (KEV) CVEs that CTID maps to a technique as exploitation."""

    technique_id: str = Field(pattern=TECHNIQUE_ID_PATTERN, description="ATT&CK technique id, e.g. T1190")
    ransomware: bool | None = Field(None, description="true: only CVEs with known ransomware use; omit for all")


class CveArgs(BaseModel):
    """Question 3: the techniques a KEV CVE enables and the groups using them (association only).
    Also returns model-generated technique suggestions, which are never verified."""

    cve_id: str = Field(pattern=CVE_ID_PATTERN, description="CVE id, e.g. CVE-2021-44228")


class RankingArgs(BaseModel):
    """Question 4: vendors or products with the most actively exploited CVEs, with their top weaknesses."""

    level: Literal["vendor", "product"] = "vendor"
    limit: int = Field(10, ge=1, le=25)


class PlanArgs(BaseModel):
    """Question 5: greedy mitigation plan covering the techniques reachable from exploited CVEs."""

    since: date | None = Field(None, description="Only CVEs added to KEV on or after this date")
    max_picks: int = Field(10, ge=1, le=25)


class CentralArgs(BaseModel):
    """Question 6: the most central techniques (GDS degree or betweenness) and technique communities."""

    by: Literal["used_by_groups", "betweenness"] = "used_by_groups"
    limit: int = Field(10, ge=1, le=25)


class ExposureArgs(BaseModel):
    """Question 7: a product's exploited CVEs, the techniques they enable, groups and mitigations."""

    product_key: str = Field(min_length=3, description="vendor:product key from search_entities, e.g. fortinet:fortios")


class SimilarArgs(BaseModel):
    """Groups with the most similar technique profiles to a group (GDS node similarity, Jaccard)."""

    group_id: str = Field(pattern=GROUP_ID_PATTERN, description="ATT&CK group id, e.g. G0016")
    limit: int = Field(5, ge=1, le=20)


class CypherArgs(BaseModel):
    """Fallback only, when no other tool fits: run one read-only Cypher query. Writes, CALL and admin
    commands are rejected, the query is checked with EXPLAIN and LIMIT is capped at 50."""

    query: str = Field(min_length=10, max_length=2000, description="One read-only Cypher query")


CypherArgs.__doc__ = f"{CypherArgs.__doc__} {GRAPH_SCHEMA}"


def search_entities(driver: Driver, args: SearchArgs) -> ToolOutput:
    """Look up ids by name or alias."""
    records, _, _ = driver.execute_query(SEARCH_QUERY, {"term": args.text.lower(), "limit": 5},
                                         routing_=RoutingControl.READ)
    matches = [{"kind": r["kind"], "id": r["id"], "name": r["name"]} for r in records]
    return ToolOutput(data={"matches": matches}, path="(n) WHERE name or alias CONTAINS text",
                      source="ATT&CK, KEV, NVD", verified_ids={m["id"] for m in matches})


def group_techniques(driver: Driver, args: GroupArgs) -> ToolOutput:
    """Question 1 for the agent: techniques with tactics, plus the mitigations covering most of them."""
    result = groups.group_techniques(driver, args.group_id)
    if result is None:
        raise ToolFailure(f"No group {args.group_id}. Use search_entities to find the right id.")
    body = result.model_dump()
    covers: dict[str, dict[str, Any]] = {}
    for technique in body["techniques"]:
        for mitigation in technique["mitigations"]:
            entry = covers.setdefault(mitigation["attack_id"], {**mitigation, "covers_techniques": 0})
            entry["covers_techniques"] += 1
    data = {
        "group": body["group"],
        "technique_count": body["technique_count"],
        "techniques": [{"attack_id": t["attack_id"], "name": t["name"], "tactics": t["tactics"]}
                       for t in body["techniques"]],
        "top_mitigations": sorted(covers.values(), key=lambda m: (-m["covers_techniques"], m["attack_id"]))[:10],
    }
    return ToolOutput(data=data, path="(Group)-[:USES]->(Technique)-[:IN_TACTIC]->(Tactic); "
                                      "(Mitigation)-[:MITIGATES]->(Technique)",
                      source="MITRE ATT&CK v20", verified_ids=collect_ids(body))


def technique_cves(driver: Driver, args: TechniqueCvesArgs) -> ToolOutput:
    """Question 2 for the agent."""
    result = techniques.technique_cves(driver, args.technique_id, ransomware=args.ransomware)
    if result is None:
        raise ToolFailure(f"No technique {args.technique_id}. Use search_entities to find the right id.")
    body = result.model_dump(mode="json")
    for cve in body["cves"]:
        cve.pop("mapping_comment", None)
    return ToolOutput(data=body, path="(CVE)-[:EXPLOITS_VIA]->(Technique)[<-[:SUBTECHNIQUE_OF]-(Technique)]",
                      source="CISA KEV + CTID mappings", verified_ids=collect_ids(body))


def cve_groups(driver: Driver, args: CveArgs) -> ToolOutput:
    """Question 3 for the agent. Suggestions are kept apart and their ids marked model-generated."""
    result = cves.cve_groups(driver, args.cve_id, limit=15)
    if result is None:
        raise ToolFailure(f"{args.cve_id} is not in the KEV catalog.")
    body = result.model_dump()
    suggested = {s["attack_id"] for s in body["suggested_techniques"]}
    verified = collect_ids({key: value for key, value in body.items() if key != "suggested_techniques"})
    return ToolOutput(data=body, path="(CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(Technique)"
                                      "<-[:USES]-(Group); model: (CVE)-[:INFERRED_MAPS_TO]->(Technique)",
                      source="CISA KEV + CTID mappings + ATT&CK; suggestions from the D18 model",
                      verified_ids=verified, inferred_ids=suggested - verified)


def top_exploited(driver: Driver, args: RankingArgs) -> ToolOutput:
    """Question 4 for the agent."""
    if args.level == "vendor":
        body = products.top_vendors(driver, limit=args.limit).model_dump()
        path = "(Vendor)<-[:MADE_BY]-(Product)<-[:AFFECTS]-(CVE)-[:HAS_WEAKNESS]->(CWE)"
    else:
        body = products.top_products(driver, limit=args.limit).model_dump()
        path = "(Product)<-[:AFFECTS]-(CVE)-[:HAS_WEAKNESS]->(CWE)"
    return ToolOutput(data=body, path=path, source="CISA KEV + NVD (CPE, CWE)", verified_ids=collect_ids(body))


def mitigation_plan(driver: Driver, args: PlanArgs) -> ToolOutput:
    """Question 5 for the agent."""
    body = analytics.mitigation_plan(driver, since=args.since, max_picks=args.max_picks).model_dump(mode="json")
    return ToolOutput(data=body, path="(CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(Technique)"
                                      "<-[:MITIGATES]-(Mitigation)",
                      source="greedy cover computed from CTID mappings and ATT&CK (D14)",
                      verified_ids=collect_ids(body))


def central_techniques(driver: Driver, args: CentralArgs) -> ToolOutput:
    """Question 6 for the agent."""
    result = analytics.central_techniques(driver, by=args.by, limit=args.limit)
    if result is None:
        raise ToolFailure("Centrality has not been computed: run make analytics.")
    body = result.model_dump(mode="json")
    return ToolOutput(data=body, path="(Group)-[:USES]->(Technique) projected by GDS",
                      source="GDS degree, betweenness and Louvain over ATT&CK (D15)", verified_ids=collect_ids(body))


def product_exposure(driver: Driver, args: ExposureArgs) -> ToolOutput:
    """Question 7 for the agent."""
    result = products.product_exposure(driver, args.product_key, limit=10)
    if result is None:
        raise ToolFailure(f"No product {args.product_key}. Use search_entities to find the vendor:product key.")
    body = result.model_dump()
    return ToolOutput(data=body, path="(Product)<-[:AFFECTS]-(CVE)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->"
                                      "(Technique)<-[:USES]-(Group); (Mitigation)-[:MITIGATES]->(Technique)",
                      source="NVD CPE + CISA KEV + CTID mappings + ATT&CK", verified_ids=collect_ids(body))


def similar_groups(driver: Driver, args: SimilarArgs) -> ToolOutput:
    """Group similarity for the agent."""
    result = analytics.similar_groups(driver, args.group_id, limit=args.limit)
    if result is None:
        raise ToolFailure(f"No group {args.group_id}. Use search_entities to find the right id.")
    body = result.model_dump()
    return ToolOutput(data=body, path="(Group)-[:USES]->(Technique)<-[:USES]-(Group), GDS node similarity",
                      source="GDS node similarity (Jaccard) over ATT&CK (D17)", verified_ids=collect_ids(body))


def run_cypher(driver: Driver, args: CypherArgs) -> ToolOutput:
    """The guarded fallback. Raises GuardrailError when a check rejects the query."""
    result = run_guarded(driver, args.query)
    touches_model = "INFERRED_MAPS_TO" in result.query.upper()
    # Ids count as returned when they are in the rows, or when the query matched on them as literals
    # (an aggregate like count(c) for {cwe_id: 'CWE-79'} rests on CWE-79 without returning it).
    values = [value for row in result.rows for value in row.values() if isinstance(value, str)]
    ids = collect_ids(result.rows) | {v for v in values + string_literals(result.query) if _looks_like_id(v)}
    return ToolOutput(data={"rows": result.rows, "row_count": len(result.rows), "row_cap": MAX_ROWS},
                      path=result.query, source="read-only Cypher written by the LLM, checked by the guardrails",
                      verified_ids=set() if touches_model else ids, inferred_ids=ids if touches_model else set(),
                      cypher=result.query, rows=len(result.rows))


def _looks_like_id(value: str) -> bool:
    """True for strings shaped like ATT&CK, CVE or CWE ids, so bare id columns still count as citations."""
    return bool(value[:4] == "CVE-" or value[:4] == "CWE-" or (value[:1] in "GTMSC" and value[1:5].isdigit()))


@dataclass(frozen=True)
class Tool:
    """A tool: its name, argument schema and implementation."""

    name: str
    args: type[BaseModel]
    run: Callable[[Driver, Any], ToolOutput]

    def spec(self) -> dict[str, Any]:
        """The tool in the function-calling format both providers accept."""
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        schema.pop("description", None)
        description = " ".join((self.args.__doc__ or "").split())
        return {"type": "function", "function": {"name": self.name, "description": description,
                                                 "parameters": schema}}


TOOLS = {tool.name: tool for tool in (
    Tool("search_entities", SearchArgs, search_entities),
    Tool("group_techniques", GroupArgs, group_techniques),
    Tool("technique_cves", TechniqueCvesArgs, technique_cves),
    Tool("cve_groups", CveArgs, cve_groups),
    Tool("top_exploited", RankingArgs, top_exploited),
    Tool("mitigation_plan", PlanArgs, mitigation_plan),
    Tool("central_techniques", CentralArgs, central_techniques),
    Tool("product_exposure", ExposureArgs, product_exposure),
    Tool("similar_groups", SimilarArgs, similar_groups),
    Tool("run_cypher", CypherArgs, run_cypher),
)}


def call_tool(driver: Driver, name: str, arguments: dict[str, Any]) -> ToolOutput:
    """Validate the arguments and run the named tool. Raises ToolFailure or GuardrailError."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolFailure(f"Unknown tool {name!r}. Available: {', '.join(TOOLS)}.")
    try:
        args = tool.args.model_validate(arguments)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'arguments'}: {e['msg']}" for e in error.errors())
        raise ToolFailure(f"Invalid arguments for {name}: {problems}") from error
    return tool.run(driver, args)
