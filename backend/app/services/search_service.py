"""Service layer for search-related database operations and discovery integration."""

import logging
from typing import Optional, Set
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from app.models.search import Search
from app.models.search_result import SearchResult
from app.models.website import Website
from app.schemas.search import (
    SearchCreate,
    SearchResponse,
    SearchResultItemResponse,
    SearchSummaryResponse,
)
from app.services.search_provider import (
    BaseSearchProvider,
    discover_candidates_for_keyword,
    SearchProviderConfigError,
)
from app.services.url_processor import (
    process_candidates,
    normalize_url,
)

logger = logging.getLogger(__name__)


def create_search(db: Session, search_in: SearchCreate, user_id: Optional[int] = None) -> Search:
    """Create a new search entry in the database associated with an authenticated user (or None for unauthenticated)."""
    search = Search(
        keyword=search_in.keyword.strip(),
        requested_website_count=search_in.requested_website_count,
        user_id=user_id,
        status="pending",
    )
    db.add(search)
    db.commit()
    db.refresh(search)
    return search



async def execute_search_discovery(
    db: Session,
    search: Search,
    provider: Optional[BaseSearchProvider] = None
) -> Search:
    """Execute candidate website discovery and URL processing, then record results.

    Pipeline:
    1. Step 10: Search provider queries candidate URLs across multiple query patterns.
    2. Step 11: Candidate URLs are syntactically validated, normalized, and deduplicated.
    3. Step 11 Database: Clean normalized URLs and domains are persisted as Website & SearchResult records.

    Args:
        db: SQLAlchemy database session.
        search: Search ORM instance to discover candidates for.
        provider: Optional search provider instance (defaults to configured provider).

    Returns:
        Updated Search ORM instance with associated discovered SearchResults.
    """
    search_id = search.id
    try:
        # Step 10: Search Engine Discovery
        raw_candidates = await discover_candidates_for_keyword(
            keyword=search.keyword,
            target_count=search.requested_website_count,
            provider=provider
        )

        # Step 11: URL Processing (Validation, Normalization, Deduplication)
        clean_candidates = process_candidates(raw_candidates)

        # Track existing associations to prevent duplicate insertions within same transaction
        associated_website_ids: Set[int] = set(
            db.scalars(
                select(SearchResult.website_id).where(SearchResult.search_id == search_id)
            ).all()
        )

        for candidate in clean_candidates:
            # Check or create Website entity
            norm_res = normalize_url(candidate.url)
            domain = candidate.domain or norm_res.domain or "unknown"
            canonical_url = norm_res.normalized_url or candidate.url

            stmt = select(Website).where(Website.domain == domain)
            website = db.scalars(stmt).first()
            if not website:
                website = Website(
                    domain=domain,
                    url=canonical_url,
                    name=candidate.title or domain
                )
                db.add(website)
                db.flush()

            # Check or create SearchResult association
            if website.id not in associated_website_ids:
                sr = SearchResult(
                    search_id=search_id,
                    website_id=website.id,
                    status="discovered"
                )
                db.add(sr)
                associated_website_ids.add(website.id)

        if clean_candidates:
            search.status = "discovered"
        else:
            search.status = "no_results"

        db.commit()
        db.refresh(search)
        return search

    except SearchProviderConfigError as e:
        logger.info(f"Search discovery skipped for search #{search_id} (provider not configured): {e}")
        db.rollback()
        search_record = db.get(Search, search_id)
        if search_record:
            search_record.status = "pending"
            db.commit()
            db.refresh(search_record)
            return search_record
        return search
    except Exception as e:
        logger.error(f"Search discovery encountered an error for search #{search_id}: {e}")
        db.rollback()
        search_record = db.get(Search, search_id)
        if search_record:
            search_record.status = "failed"
            db.commit()
            db.refresh(search_record)
        raise


def get_search_by_id(
    db: Session, search_id: int, user_id: Optional[int] = None
) -> Optional[Search]:
    """Retrieve a search by ID with its results, websites, analysis, and guest post information.

    If user_id is provided, enforces that the search belongs to that user (or is unowned legacy).
    If owned by another user, returns None to ensure strict isolation.
    """
    stmt = (
        select(Search)
        .where(Search.id == search_id)
        .options(
            selectinload(Search.results)
            .selectinload(SearchResult.website)
            .selectinload(Website.analysis),
            selectinload(Search.results)
            .selectinload(SearchResult.website)
            .selectinload(Website.guest_post_info),
        )
    )
    search = db.scalars(stmt).first()
    if not search:
        return None

    # If user_id is provided, ensure search belongs to user
    if user_id is not None:
        if search.user_id is not None and search.user_id != user_id:
            return None

    return search


def list_searches(
    db: Session, user_id: Optional[int] = None, skip: int = 0, limit: int = 50
) -> tuple[list[SearchSummaryResponse], int]:
    """List searches with total count, scoped by user_id if provided."""
    if user_id is not None:
        count_stmt = select(func.count(Search.id)).where(Search.user_id == user_id)
        stmt = (
            select(Search)
            .where(Search.user_id == user_id)
            .options(selectinload(Search.results))
            .order_by(Search.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
    else:
        count_stmt = select(func.count(Search.id)).where(Search.user_id.is_(None))
        stmt = (
            select(Search)
            .where(Search.user_id.is_(None))
            .options(selectinload(Search.results))
            .order_by(Search.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

    total = db.scalar(count_stmt) or 0
    searches = db.scalars(stmt).all()

    summaries = [
        SearchSummaryResponse(
            id=s.id,
            user_id=s.user_id,
            keyword=s.keyword,
            requested_website_count=s.requested_website_count,
            status=s.status,
            created_at=s.created_at,
            results_count=len(s.results),
        )
        for s in searches
    ]
    return summaries, total


def delete_search(db: Session, search_id: int, user_id: int) -> bool:
    """Delete a search record if it exists and is owned by the specified user.

    Returns True if deleted, False if not found or owned by a different user.
    """
    search = db.get(Search, search_id)
    if not search:
        return False
    if search.user_id != user_id:
        return False

    db.delete(search)
    db.commit()
    return True



def build_search_response(search: Search) -> SearchResponse:
    """Build a detailed SearchResponse from a Search ORM entity with deterministic result ordering."""
    result_items: list[SearchResultItemResponse] = []

    sorted_results = sorted(search.results, key=lambda r: r.id) if search.results else []

    for res in sorted_results:
        website = res.website
        analysis = website.analysis if website else None
        gp_info = website.guest_post_info if website else None

        result_items.append(
            SearchResultItemResponse(
                id=res.id,
                website_id=res.website_id,
                domain=website.domain if website else "",
                name=website.name if website else None,
                url=website.url if website else None,
                status=res.status,
                quality_score=analysis.quality_score if analysis else None,
                relevance=analysis.niche_relevance if analysis else None,
                accepts_guest_posts=gp_info.accepts_guest_posts if gp_info else None,
                pricing=gp_info.pricing if gp_info else None,
                submission_method=gp_info.submission_method if gp_info else None,
                created_at=res.created_at,
            )
        )

    return SearchResponse(
        id=search.id,
        user_id=search.user_id,
        keyword=search.keyword,
        requested_website_count=search.requested_website_count,
        status=search.status,
        created_at=search.created_at,
        results=result_items,
        total_results=len(result_items),
    )

