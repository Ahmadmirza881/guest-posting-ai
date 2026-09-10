"""Pydantic schemas package for Guest Posting AI."""

from app.schemas.search import (
    SearchCreate,
    SearchResponse,
    SearchSummaryResponse,
    SearchListResponse,
    SearchResultItemResponse,
)
from app.schemas.website import (
    WebsiteResponse,
    WebsiteDetailResponse,
    WebsiteAnalysisResponse,
    GuestPostInfoResponse,
)

__all__ = [
    "SearchCreate",
    "SearchResponse",
    "SearchSummaryResponse",
    "SearchListResponse",
    "SearchResultItemResponse",
    "WebsiteResponse",
    "WebsiteDetailResponse",
    "WebsiteAnalysisResponse",
    "GuestPostInfoResponse",
]
