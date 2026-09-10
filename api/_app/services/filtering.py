"""Smart Filtering Service for Website Opportunities (Step 18).

Provides safe, SQL-injection-proof filtering, sorting, and pagination across
discovered websites, guest-post detection, submission extraction, AI verification,
semantic analysis, and deterministic quality scores.

CRITICAL CONSTRAINTS:
- Operates 100% on stored database records (NO new crawling or AI calls).
- Fully supports combinations of all filter criteria with AND logic.
- Enforces strict whitelist validation for sorting and score ranges [0, 100].
- Supports Search Scoping (SearchResult -> Search).
"""

import logging
import math
from typing import Optional, List, Tuple, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, distinct
from sqlalchemy.orm import Session

from app.models.website import Website
from app.models.guest_post import GuestPostInformation
from app.models.website_analysis import WebsiteAnalysis
from app.models.search_result import SearchResult

logger = logging.getLogger(__name__)

# Sorting field whitelist mapping to SQLAlchemy column attributes
SORT_COLUMN_MAPPING = {
    "quality_score": WebsiteAnalysis.quality_score,
    "relevance_score": WebsiteAnalysis.relevance_score,
    "content_quality": WebsiteAnalysis.content_quality_score,
    "domain": Website.domain,
}

ALLOWED_SORT_ORDERS = {"asc", "desc"}
ALLOWED_STATUS = {"accepting", "not_accepting", "pending", "unknown", "all"}
ALLOWED_PRICING = {"free", "paid", "unknown", "all"}
ALLOWED_VERIFICATION = {"verified", "rejected", "uncertain", "unverified", "all"}
ALLOWED_CRAWL_STATUS = {"pending", "crawled", "success", "failed", "all"}
ALLOWED_SUBMISSION_METHODS = {"email", "form", "google_form", "typeform"}


class WebsiteFilterParams(BaseModel):
    """Validated input parameters for filtering websites (Step 18)."""
    search_id: Optional[int] = None
    guest_post_status: Optional[str] = None
    acceptance: Optional[str] = None  # Alias for guest_post_status
    pricing: Optional[str] = None
    min_quality_score: Optional[int] = None
    min_relevance_score: Optional[int] = None
    min_content_quality: Optional[int] = None
    min_content_quality_score: Optional[int] = None  # Alias for min_content_quality
    verification_status: Optional[str] = None
    min_ai_confidence: Optional[int] = None
    submission_method: Optional[str] = None
    niche: Optional[str] = None
    keyword: Optional[str] = None  # Alias for niche
    crawl_status: Optional[str] = None
    sort_by: str = "quality_score"
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 25


def validate_filter_params(params: WebsiteFilterParams) -> None:
    """Validate all filter parameters against strict whitelists and bounds.

    Raises:
        ValueError: If any parameter value is invalid or out of allowed bounds.
    """
    # 1. Sort fields validation
    if params.sort_by not in SORT_COLUMN_MAPPING:
        raise ValueError(
            f"Invalid sort_by '{params.sort_by}'. Allowed: {list(SORT_COLUMN_MAPPING.keys())}"
        )

    if params.sort_order.lower() not in ALLOWED_SORT_ORDERS:
        raise ValueError(
            f"Invalid sort_order '{params.sort_order}'. Allowed: {list(ALLOWED_SORT_ORDERS)}"
        )

    # 2. Status & Acceptance validation
    status_val = params.guest_post_status or params.acceptance
    if status_val and status_val.lower() not in ALLOWED_STATUS:
        raise ValueError(
            f"Invalid guest_post_status '{status_val}'. Allowed: {list(ALLOWED_STATUS)}"
        )

    # 3. Pricing validation
    if params.pricing and params.pricing.lower() not in ALLOWED_PRICING:
        raise ValueError(
            f"Invalid pricing filter '{params.pricing}'. Allowed: {list(ALLOWED_PRICING)}"
        )

    # 4. Verification status validation
    if params.verification_status and params.verification_status.lower() not in ALLOWED_VERIFICATION:
        raise ValueError(
            f"Invalid verification_status '{params.verification_status}'. Allowed: {list(ALLOWED_VERIFICATION)}"
        )

    # 5. Submission method validation
    if params.submission_method and params.submission_method.lower() not in ALLOWED_SUBMISSION_METHODS:
        raise ValueError(
            f"Invalid submission_method '{params.submission_method}'. Allowed: {list(ALLOWED_SUBMISSION_METHODS)}"
        )

    # 6. Crawl status validation
    if params.crawl_status and params.crawl_status.lower() not in ALLOWED_CRAWL_STATUS:
        raise ValueError(
            f"Invalid crawl_status '{params.crawl_status}'. Allowed: {list(ALLOWED_CRAWL_STATUS)}"
        )

    # 7. Numerical ranges validation [0, 100]
    if params.min_quality_score is not None and not (0 <= params.min_quality_score <= 100):
        raise ValueError(
            f"min_quality_score must be between 0 and 100 (got {params.min_quality_score})"
        )

    if params.min_relevance_score is not None and not (0 <= params.min_relevance_score <= 100):
        raise ValueError(
            f"min_relevance_score must be between 0 and 100 (got {params.min_relevance_score})"
        )

    cq_val = params.min_content_quality_score if params.min_content_quality_score is not None else params.min_content_quality
    if cq_val is not None and not (0 <= cq_val <= 100):
        raise ValueError(
            f"min_content_quality must be between 0 and 100 (got {cq_val})"
        )

    if params.min_ai_confidence is not None and not (0 <= params.min_ai_confidence <= 100):
        raise ValueError(
            f"min_ai_confidence must be between 0 and 100 (got {params.min_ai_confidence})"
        )

    # 8. Pagination bounds validation
    if params.page < 1:
        raise ValueError(f"page must be >= 1 (got {params.page})")

    if not (1 <= params.page_size <= 100):
        raise ValueError(f"page_size must be between 1 and 100 (got {params.page_size})")


def filter_websites(
    db: Session,
    params: WebsiteFilterParams
) -> Tuple[List[Website], int, int, int, int, Dict[str, Any]]:
    """Execute dynamic SQL filtering, sorting, and pagination across stored website data.

    Args:
        db: SQLAlchemy database session.
        params: Validated WebsiteFilterParams.

    Returns:
        tuple of (items, total_count, page, page_size, total_pages, filters_applied)
    """
    validate_filter_params(params)

    # Base query joining related tables with outer joins to handle missing analysis/guest post records
    stmt = (
        select(Website)
        .outerjoin(GuestPostInformation, GuestPostInformation.website_id == Website.id)
        .outerjoin(WebsiteAnalysis, WebsiteAnalysis.website_id == Website.id)
    )

    filters_applied: Dict[str, Any] = {}

    # 1. Search Scope Filter (SearchResult association)
    if params.search_id is not None:
        stmt = stmt.join(SearchResult, SearchResult.website_id == Website.id).where(
            SearchResult.search_id == params.search_id
        )
        filters_applied["search_id"] = params.search_id

    # 2. Guest Post Acceptance / Status Filter
    status_val = (params.guest_post_status or params.acceptance or "").lower()
    if status_val and status_val != "all":
        filters_applied["guest_post_status"] = status_val
        if status_val == "accepting":
            stmt = stmt.where(GuestPostInformation.accepts_guest_posts == True)  # noqa: E712
        elif status_val == "not_accepting":
            stmt = stmt.where(GuestPostInformation.accepts_guest_posts == False)  # noqa: E712
        elif status_val in ("pending", "unknown"):
            stmt = stmt.where(
                or_(
                    GuestPostInformation.id.is_(None),
                    GuestPostInformation.accepts_guest_posts.is_(None),
                    GuestPostInformation.verification_status == "unverified",
                    Website.crawl_status == "pending"
                )
            )

    # 3. Pricing Filter (free vs paid vs unknown vs all)
    pricing_val = (params.pricing or "").lower()
    if pricing_val and pricing_val != "all":
        filters_applied["pricing"] = pricing_val
        if pricing_val == "free":
            stmt = stmt.where(
                or_(
                    func.lower(GuestPostInformation.pricing).like("%free%"),
                    func.lower(GuestPostInformation.pricing).like("%no fee%"),
                    func.lower(GuestPostInformation.pricing) == "free"
                )
            )
        elif pricing_val == "paid":
            stmt = stmt.where(
                or_(
                    func.lower(GuestPostInformation.pricing).like("%paid%"),
                    func.lower(GuestPostInformation.pricing).like("%sponsor%"),
                    func.lower(GuestPostInformation.pricing).like("%$%"),
                    func.lower(GuestPostInformation.pricing).like("%€%"),
                    func.lower(GuestPostInformation.pricing).like("%£%")
                )
            )
        elif pricing_val == "unknown":
            stmt = stmt.where(
                or_(
                    GuestPostInformation.id.is_(None),
                    GuestPostInformation.pricing.is_(None),
                    func.lower(GuestPostInformation.pricing).like("%unknown%")
                )
            )

    # 4. Minimum Quality Score (0-100)
    if params.min_quality_score is not None:
        filters_applied["min_quality_score"] = params.min_quality_score
        stmt = stmt.where(WebsiteAnalysis.quality_score >= params.min_quality_score)

    # 5. Minimum Relevance Score (0-100)
    if params.min_relevance_score is not None:
        filters_applied["min_relevance_score"] = params.min_relevance_score
        stmt = stmt.where(WebsiteAnalysis.relevance_score >= params.min_relevance_score)

    # 6. Minimum Content Quality Score (0-100)
    cq_val = params.min_content_quality_score if params.min_content_quality_score is not None else params.min_content_quality
    if cq_val is not None:
        filters_applied["min_content_quality"] = cq_val
        stmt = stmt.where(WebsiteAnalysis.content_quality_score >= cq_val)

    # 7. Minimum AI Verification Confidence (0-100)
    if params.min_ai_confidence is not None:
        filters_applied["min_ai_confidence"] = params.min_ai_confidence
        stmt = stmt.where(GuestPostInformation.ai_confidence >= params.min_ai_confidence)

    # 8. Submission Method Filter (matches partial / multi-methods like ["email", "google_form"])
    if params.submission_method:
        sm = params.submission_method.lower().strip()
        filters_applied["submission_method"] = sm
        stmt = stmt.where(func.lower(GuestPostInformation.submission_method).like(f"%{sm}%"))

    # 9. Verification Status Filter
    if params.verification_status:
        vs = params.verification_status.lower()
        if vs != "all":
            filters_applied["verification_status"] = vs
            if vs == "unverified":
                stmt = stmt.where(
                    or_(
                        GuestPostInformation.id.is_(None),
                        GuestPostInformation.verification_status.is_(None),
                        GuestPostInformation.verification_status == "unverified"
                    )
                )
            else:
                stmt = stmt.where(GuestPostInformation.verification_status == vs)

    # 10. Crawl Status Filter
    if params.crawl_status:
        cs = params.crawl_status.lower()
        if cs != "all":
            filters_applied["crawl_status"] = cs
            if cs in ("crawled", "success"):
                stmt = stmt.where(Website.crawl_status.in_(["crawled", "success"]))
            else:
                stmt = stmt.where(Website.crawl_status == cs)

    # 11. Niche / Keyword Text Search (Case-Insensitive on stored DB records)
    niche_text = (params.niche or params.keyword or "").strip().lower()
    if niche_text:
        filters_applied["niche"] = niche_text
        stmt = stmt.where(
            or_(
                func.lower(WebsiteAnalysis.primary_niche).like(f"%{niche_text}%"),
                func.lower(WebsiteAnalysis.topics).like(f"%{niche_text}%"),
                func.lower(WebsiteAnalysis.relevance_reason).like(f"%{niche_text}%"),
                func.lower(Website.domain).like(f"%{niche_text}%"),
                func.lower(Website.name).like(f"%{niche_text}%"),
            )
        )

    # Deduplicate website instances
    stmt = stmt.distinct()

    # Calculate total count before pagination
    count_stmt = select(func.count(distinct(Website.id)))
    count_stmt = (
        count_stmt
        .outerjoin(GuestPostInformation, GuestPostInformation.website_id == Website.id)
        .outerjoin(WebsiteAnalysis, WebsiteAnalysis.website_id == Website.id)
    )
    if params.search_id is not None:
        count_stmt = count_stmt.join(SearchResult, SearchResult.website_id == Website.id).where(
            SearchResult.search_id == params.search_id
        )
    if stmt.whereclause is not None:
        count_stmt = count_stmt.where(stmt.whereclause)

    total_count = db.scalar(count_stmt) or 0

    # 12. Apply Sorting
    sort_col = SORT_COLUMN_MAPPING[params.sort_by]
    if params.sort_order.lower() == "asc":
        stmt = stmt.order_by(sort_col.asc().nullslast(), Website.id.asc())
    else:
        stmt = stmt.order_by(sort_col.desc().nullslast(), Website.id.desc())

    # 13. Apply Pagination
    offset = (params.page - 1) * params.page_size
    stmt = stmt.offset(offset).limit(params.page_size)

    results = list(db.scalars(stmt).all())
    total_pages = math.ceil(total_count / params.page_size) if params.page_size > 0 else 0

    return results, total_count, params.page, params.page_size, total_pages, filters_applied
