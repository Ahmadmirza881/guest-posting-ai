"""Search Pydantic schemas for request validation and response serialization."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SearchCreate(BaseModel):
    """Schema for creating a new search entry."""
    keyword: str = Field(..., min_length=1, max_length=255, description="Search keyword or niche")
    requested_website_count: int = Field(100, ge=1, le=1000, description="Target number of websites to discover")
    user_id: Optional[int] = Field(None, description="Optional user ID for associated searches")


class SearchResultItemResponse(BaseModel):
    """Schema for a website entry in a search result."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    domain: str
    name: Optional[str] = None
    url: Optional[str] = None
    status: str
    quality_score: Optional[int] = None
    relevance: Optional[int] = None
    accepts_guest_posts: Optional[bool] = None
    pricing: Optional[str] = None
    submission_method: Optional[str] = None
    created_at: datetime


class SearchResponse(BaseModel):
    """Schema for returning search details."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    keyword: str
    requested_website_count: int
    status: str
    created_at: datetime
    results: list[SearchResultItemResponse] = []
    total_results: int = 0


class SearchSummaryResponse(BaseModel):
    """Schema for lightweight search item in list view."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int] = None
    keyword: str
    requested_website_count: int
    status: str
    created_at: datetime
    results_count: int = 0


class SearchListResponse(BaseModel):
    """Schema for paginated search history list."""
    searches: list[SearchSummaryResponse]
    total: int


class SearchProgressResponse(BaseModel):
    """Schema for realtime search pipeline progress breakdown (Step 19)."""
    search_id: int
    status: str
    total_websites: int
    crawled_count: int
    verified_count: int
    analyzed_count: int
    scored_count: int
    progress_percentage: float
    is_completed: bool


class SearchDeleteResponse(BaseModel):
    """Schema for search deletion response."""
    success: bool
    id: int
    message: str


