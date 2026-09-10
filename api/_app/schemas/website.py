"""Website and analysis Pydantic schemas."""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, field_validator


class ScoreCategoryBreakdown(BaseModel):
    """Breakdown details for an individual scoring dimension."""
    points: float
    max_points: int
    reason: str


class ScoringBreakdown(BaseModel):
    """Structured breakdown of all 6 deterministic scoring categories."""
    guest_post_acceptance: ScoreCategoryBreakdown
    niche_relevance: ScoreCategoryBreakdown
    content_quality: ScoreCategoryBreakdown
    trust_signals: ScoreCategoryBreakdown
    editorial_standards: ScoreCategoryBreakdown
    ai_verification: ScoreCategoryBreakdown


class ScoringResponse(BaseModel):
    """Schema for direct website scoring endpoint output (Step 17)."""
    website_id: int
    quality_score: int
    breakdown: ScoringBreakdown
    scoring_status: str
    scored_at: datetime


class WebsiteAnalysisResponse(BaseModel):
    """Schema for website quality, niche relevance, trust, semantic analysis, and scoring (Step 16 & 17)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    primary_niche: Optional[str] = None
    topics: List[str] = []
    niche_confidence: Optional[int] = None
    niche_relevance: Optional[int] = None
    relevance_score: Optional[int] = None
    relevance_reason: Optional[str] = None
    content_quality: Optional[int] = None
    content_quality_score: Optional[int] = None
    content_quality_reason: Optional[str] = None
    website_trust: Optional[int] = None
    trust_signals: List[str] = []
    editorial_standards: List[str] = []
    strengths: List[str] = []
    weaknesses: List[str] = []
    analysis_confidence: Optional[int] = None
    analysis_evidence: List[str] = []
    warnings: List[str] = []
    analysis_status: Optional[str] = "completed"
    quality_score: Optional[int] = None
    score_breakdown: Optional[Dict[str, Any]] = None
    scoring_status: Optional[str] = "pending"
    scored_at: Optional[datetime] = None
    guest_post_quality: Optional[int] = None
    website_activity: Optional[int] = None
    analyzed_at: datetime

    @field_validator("topics", "trust_signals", "editorial_standards", "strengths", "weaknesses", "analysis_evidence", "warnings", mode="before")
    @classmethod
    def parse_json_or_list(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(item) for item in v]
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            except Exception:
                return [v] if v.strip() else []
        return []

    @field_validator("score_breakdown", mode="before")
    @classmethod
    def parse_score_breakdown(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return None
        return None


class AIAnalysisResponse(BaseModel):
    """Schema for direct AI website analysis endpoint output (Step 16)."""
    website_id: int
    primary_niche: Optional[str] = None
    topics: List[str] = []
    niche_confidence: int
    relevance_score: int
    relevance_reason: str
    content_quality_score: int
    content_quality_reason: str
    trust_signals: List[str] = []
    editorial_standards: List[str] = []
    strengths: List[str] = []
    weaknesses: List[str] = []
    analysis_confidence: int
    evidence: List[str] = []
    warnings: List[str] = []
    analysis_status: str
    analyzed_at: datetime


class GuestPostInfoResponse(BaseModel):
    """Schema for guest posting details, guidelines, and AI verification."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    accepts_guest_posts: bool
    confidence: Optional[int] = None
    pricing: Optional[str] = None
    submission_method: Optional[str] = None
    submission_url: Optional[str] = None
    contact_email: Optional[str] = None
    guidelines_url: Optional[str] = None
    dofollow: Optional[bool] = None
    evidence: Optional[str] = None
    verification_status: Optional[str] = "unverified"
    ai_confidence: Optional[int] = None
    ai_reason: Optional[str] = None
    ai_evidence: Optional[str] = None
    verified_at: Optional[datetime] = None
    updated_at: datetime


class WebsiteResponse(BaseModel):
    """Schema for basic website metadata."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    url: str
    name: Optional[str] = None
    crawl_status: Optional[str] = "pending"
    last_crawled_at: Optional[datetime] = None
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WebsiteDetailResponse(BaseModel):
    """Schema for full website details including analysis and guest posting info."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    url: str
    name: Optional[str] = None
    crawl_status: Optional[str] = "pending"
    last_crawled_at: Optional[datetime] = None
    http_status: Optional[int] = None
    final_url: Optional[str] = None
    content_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    analysis: Optional[WebsiteAnalysisResponse] = None
    guest_post_info: Optional[GuestPostInfoResponse] = None
    is_saved: bool = False


class CrawlResultResponse(BaseModel):
    """Schema for direct crawler output."""
    original_url: str
    final_url: Optional[str] = None
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    response_time_ms: Optional[float] = None
    title: Optional[str] = None
    html_snippet: Optional[str] = None
    success: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None


class GuestPostDetectionResponse(BaseModel):
    """Schema for deterministic guest post detection output (Step 13)."""
    website_id: int
    detected: bool
    confidence: int
    strong_signals: List[str]
    medium_signals: List[str]
    weak_signals: List[str]
    negative_signals: List[str]
    has_conflicts: bool
    evidence_snippets: List[str]
    summary_reason: str


class SubmissionExtractionResponse(BaseModel):
    """Schema for deterministic submission information extraction output (Step 14)."""
    website_id: int
    submission_methods: List[str]
    primary_submission_method: Optional[str] = None
    submission_emails: List[str]
    primary_email: Optional[str] = None
    submission_urls: List[str]
    primary_submission_url: Optional[str] = None
    guidelines_urls: List[str]
    primary_guidelines_url: Optional[str] = None
    is_paid: Optional[bool] = None
    pricing_model: str  # "free", "paid", "unknown"
    price_amount: Optional[str] = None
    evidence_snippets: List[str]
    has_submission_channel: bool


class AIVerificationResponse(BaseModel):
    """Schema for AI semantic verification output (Step 15)."""
    website_id: int
    verification_status: str  # "verified", "rejected", "uncertain"
    accepts_guest_posts: Optional[bool] = None
    confidence: int  # 0 to 100
    reason: str
    guest_post_evidence: Optional[str] = None
    submission_method: Optional[str] = None
    submission_email: Optional[str] = None
    submission_url: Optional[str] = None
    guidelines_url: Optional[str] = None
    pricing: Optional[str] = None
    corrections: List[str] = []
    verified_at: datetime


class WebsiteFilterResponse(BaseModel):
    """Schema for paginated filtered website opportunities (Step 18)."""
    items: List[WebsiteDetailResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: Dict[str, Any] = {}


class SaveWebsiteResponse(BaseModel):
    """Schema for save/unsave website response (Step 20)."""
    success: bool
    website_id: int
    is_saved: bool
    message: str


class SavedWebsiteItemResponse(BaseModel):
    """Schema for a saved website item with full opportunity metadata (Step 20)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    name: Optional[str] = None
    domain: str
    url: str
    niche: Optional[str] = None
    description: Optional[str] = None
    guest_post_status: Optional[str] = None
    accepts_guest_posts: Optional[bool] = None
    pricing: Optional[str] = None
    submission_method: Optional[str] = None
    relevance_score: Optional[int] = None
    content_quality_score: Optional[int] = None
    quality_score: Optional[int] = None
    verification_status: Optional[str] = None
    submission_url: Optional[str] = None
    guidelines_url: Optional[str] = None
    saved_date: datetime
    is_saved: bool = True


class SavedWebsiteListResponse(BaseModel):
    """Schema for paginated saved websites list (Step 20)."""
    items: List[SavedWebsiteItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

