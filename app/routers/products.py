"""Vendor and product endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j import Driver

from app.database.connection import get_driver
from app.models.common import ErrorResponse
from app.models.products import (ExposureResponse, ProductRankingResponse, ProductSearchResponse,
                                 VendorRankingResponse)
from app.services.products import product_exposure, search_products, top_products, top_vendors

router = APIRouter(tags=["products"])

Limit = Annotated[int, Query(ge=1, le=100, description="Maximum entries returned")]
CweLimit = Annotated[int, Query(ge=0, le=20, description="Weaknesses listed per entry")]


@router.get("/vendors/top", response_model=VendorRankingResponse)
def get_top_vendors(driver: Annotated[Driver, Depends(get_driver)], limit: Limit = 10,
                    cwe_limit: CweLimit = 3) -> VendorRankingResponse:
    """Question 4: vendors with the most actively exploited CVEs, broken down by weakness."""
    return top_vendors(driver, limit=limit, cwe_limit=cwe_limit)


@router.get("/products/top", response_model=ProductRankingResponse)
def get_top_products(driver: Annotated[Driver, Depends(get_driver)], limit: Limit = 10,
                     cwe_limit: CweLimit = 3) -> ProductRankingResponse:
    """Question 4: products with the most actively exploited CVEs, broken down by weakness."""
    return top_products(driver, limit=limit, cwe_limit=cwe_limit)


@router.get("/products", response_model=ProductSearchResponse)
def get_products(
    driver: Annotated[Driver, Depends(get_driver)],
    search: Annotated[str, Query(min_length=2, max_length=100, description="Part of a product or vendor name")],
    limit: Limit = 20,
) -> ProductSearchResponse:
    """Find product keys to use with /products/exposure."""
    return search_products(driver, search, limit=limit)


@router.get(
    "/products/exposure",
    response_model=ExposureResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "No product with this key"}},
)
def get_product_exposure(
    driver: Annotated[Driver, Depends(get_driver)],
    product: Annotated[str, Query(min_length=3, max_length=300,
                                  description="Product key as vendor:product, e.g. fortinet:fortios")],
    limit: Limit = 10,
) -> ExposureResponse:
    """Question 7: a product's exploited CVEs, the techniques they enable, groups using those techniques,
    and the mitigations covering the most of them."""
    result = product_exposure(driver, product, limit=limit)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Product {product} not found; use GET /products?search= to find its key")
    return result
