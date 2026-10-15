"""Schemas for the graph-algorithm endpoints: centrality (question 6), group similarity (D17) and the
mitigation plan (question 5)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.groups import GroupSummary


class AnalyticsRun(BaseModel):
    """When and how the stored centrality results were computed (make analytics)."""

    gds_version: str
    computed_at: str
    parameters: str
    community_count: int
    modularity: float


class CentralTechnique(BaseModel):
    """A technique's centrality scores."""

    attack_id: str
    name: str
    used_by_groups: int
    betweenness: float
    community: int | None = None
    community_size: int | None = None


class TechniqueCommunity(BaseModel):
    """A cluster of techniques that groups tend to use together, described by its most used members."""

    community: int
    size: int
    top_techniques: list[str]


class CentralTechniquesResponse(BaseModel):
    """Body of GET /techniques/central."""

    analytics: AnalyticsRun
    ranked_by: Literal["used_by_groups", "betweenness"]
    techniques: list[CentralTechnique]
    communities: list[TechniqueCommunity]


class SimilarGroup(BaseModel):
    """A group with a similar technique profile."""

    attack_id: str
    name: str
    jaccard: float
    shared_techniques: int
    techniques_used: int


class SimilarGroupsResponse(BaseModel):
    """Body of GET /groups/{group_id}/similar."""

    group: GroupSummary
    techniques_used: int
    method: Literal["gds.nodeSimilarity, Jaccard over techniques used, computed live"] = (
        "gds.nodeSimilarity, Jaccard over techniques used, computed live")
    similar: list[SimilarGroup]


class PlanScope(BaseModel):
    """Which exploited CVEs the plan is built from."""

    since: date | None
    kev_cves: int
    mapped_cves: int


class PlanStep(BaseModel):
    """One mitigation picked by the greedy cover, and what it adds."""

    rank: int
    attack_id: str
    name: str
    gain: int
    newly_covered_techniques: int
    cumulative_weight: int
    cumulative_pct: float


class UncoverableTechnique(BaseModel):
    """A reachable technique that no ATT&CK mitigation covers."""

    attack_id: str
    name: str
    weight: int


class Uncoverable(BaseModel):
    """The part of the weight no mitigation can cover, listed explicitly."""

    technique_count: int
    weight: int
    pct: float
    techniques: list[UncoverableTechnique]


class MitigationPlanResponse(BaseModel):
    """Body of GET /mitigations/plan: question 5 as a greedy weighted cover (D14)."""

    scope: PlanScope
    weighting: str
    reachable_techniques: int
    total_weight: int
    covered_pct: float
    picks: list[PlanStep]
    uncoverable: Uncoverable
    guarantee: str
