"""Schemas for vendor and product endpoints (questions 4 and 7)."""

from typing import Literal

from pydantic import BaseModel

from app.models.common import CveSummary
from app.models.cves import MappingType


class WeaknessCount(BaseModel):
    """How many of the exploited CVEs have this weakness."""

    cwe_id: str
    cves: int


class VendorRanking(BaseModel):
    """A vendor with its count of actively exploited CVEs."""

    vendor_key: str
    name: str
    exploited_cves: int
    ransomware_cves: int
    top_weaknesses: list[WeaknessCount]


class ProductRanking(BaseModel):
    """A product with its count of actively exploited CVEs."""

    product_key: str
    name: str
    vendor: str | None
    exploited_cves: int
    ransomware_cves: int
    top_weaknesses: list[WeaknessCount]


class VendorRankingResponse(BaseModel):
    """Body of GET /vendors/top."""

    vendors: list[VendorRanking]


class ProductRankingResponse(BaseModel):
    """Body of GET /products/top."""

    products: list[ProductRanking]


class ProductMatch(BaseModel):
    """A product found by search, to use as the product key for /products/exposure."""

    product_key: str
    name: str
    vendor: str | None
    exploited_cves: int


class ProductSearchResponse(BaseModel):
    """Body of GET /products."""

    products: list[ProductMatch]


class ProductSummary(BaseModel):
    """The product the exposure report is about."""

    product_key: str
    name: str
    part: str | None = None
    vendor: str | None = None


class ExposureCve(CveSummary):
    """An exploited CVE affecting the product, and whether CTID maps it to ATT&CK."""

    mapped_to_attack: bool


class ExposureTechnique(BaseModel):
    """A technique enabled by the product's CVEs."""

    attack_id: str
    name: str
    via_cves: int
    mapping_types: list[MappingType]


class ExposureGroup(BaseModel):
    """A group using techniques the product's CVEs enable."""

    attack_id: str
    name: str
    shared_techniques: int


class ExposureMitigation(BaseModel):
    """A mitigation and how many of the enabled techniques it covers."""

    attack_id: str
    name: str
    covers_techniques: int


class ExposureResponse(BaseModel):
    """Body of GET /products/exposure: question 7, from product to mitigations."""

    product: ProductSummary
    cve_count: int
    mapped_cve_count: int
    cves: list[ExposureCve]
    technique_count: int
    techniques: list[ExposureTechnique]
    association: Literal["shared_technique"] = "shared_technique"
    note: str
    groups: list[ExposureGroup]
    mitigations: list[ExposureMitigation]
