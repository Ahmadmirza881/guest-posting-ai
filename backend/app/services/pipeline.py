"""End-to-End Pipeline Orchestration and Background Processing Engine (Step 19).

Coordinates all previous modular stages:
1. Discovery (Steps 10 & 11)
2. Single-Page Crawling (Step 12)
3. Guest Post Detection (Step 13)
4. Submission Extraction (Step 14)
5. AI Semantic Verification (Step 15)
6. AI Semantic Analysis (Step 16)
7. Deterministic Scoring (Step 17)
8. Smart Database Filtering (Step 18)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select, func, distinct
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal

from app.models.website import Website
from app.models.guest_post import GuestPostInformation
from app.models.website_analysis import WebsiteAnalysis
from app.models.search import Search
from app.models.search_result import SearchResult

from app.services.crawler import crawl_website_record, crawl_url
from app.services.guest_post_detector import detect_guest_post_for_website
from app.services.submission_extractor import extract_and_save_submission_info
from app.services.ai_verifier import verify_website_record
from app.services.ai_analyzer import analyze_website_record
from app.services.scoring import score_website_record

logger = logging.getLogger(__name__)


async def process_single_website_pipeline(
    db: Session,
    website_id: int,
    keyword: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
) -> Website:
    """Execute the full 6-stage analysis and scoring pipeline for a single website.

    Stages:
    1. Crawl HTML (Step 12)
    2. Guest Post Detection (Step 13)
    3. Submission Extraction (Step 14)
    4. AI Semantic Verification (Step 15)
    5. AI Website Analysis (Step 16)
    6. Deterministic Scoring (Step 17)

    Args:
        db: SQLAlchemy database session.
        website_id: Target Website ID.
        keyword: Search keyword / niche context for semantic analysis.
        gemini_api_key: Optional Gemini API key override.

    Returns:
        Fully analyzed, verified, and scored Website ORM entity.
    """
    website = db.get(Website, website_id)
    if not website:
        raise ValueError(f"Website with ID {website_id} not found.")

    if website.crawl_status == "crawling":
        logger.info(f"Website #{website_id} is already being processed. Skipping duplicate execution.")
        return website

    logger.info(f"Starting pipeline execution for Website #{website_id} ({website.domain})...")

    # -------------------------------------------------------------
    # STAGE 1: Single-Page HTML Crawl (Step 12)
    # -------------------------------------------------------------
    website, crawl_res = await crawl_website_record(db=db, website_id=website_id)

    if not crawl_res.success or not website.html_content:
        logger.warning(
            f"Crawl failed for Website #{website_id} ({website.domain}): {crawl_res.error_message}"
        )
        # Create minimal fallback analysis and guest post records with 0 score
        stmt_gp = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
        gp_info = db.scalars(stmt_gp).first()
        if not gp_info:
            gp_info = GuestPostInformation(website_id=website.id)
            db.add(gp_info)

        gp_info.accepts_guest_posts = False
        gp_info.confidence = 0
        gp_info.verification_status = "rejected"
        gp_info.ai_confidence = 0
        gp_info.ai_reason = f"Crawl failed: {crawl_res.error_message or 'Unreachable site'}"
        gp_info.updated_at = datetime.now(timezone.utc)

        stmt_wa = select(WebsiteAnalysis).where(WebsiteAnalysis.website_id == website.id)
        analysis = db.scalars(stmt_wa).first()
        if not analysis:
            analysis = WebsiteAnalysis(website_id=website.id)
            db.add(analysis)

        analysis.analysis_status = "failed"
        analysis.quality_score = 0
        analysis.relevance_score = 0
        analysis.content_quality_score = 0
        analysis.analyzed_at = datetime.now(timezone.utc)
        analysis.scored_at = datetime.now(timezone.utc)
        analysis.scoring_status = "completed"

        # Update associated SearchResult statuses
        for sr in db.scalars(select(SearchResult).where(SearchResult.website_id == website.id)).all():
            sr.status = "processed"

        db.commit()
        db.refresh(website)
        return website

    # -------------------------------------------------------------
    # STAGE 2: Deterministic Guest Post Detection (Step 13)
    # -------------------------------------------------------------
    detect_guest_post_for_website(db=db, website_id=website_id)

    # -------------------------------------------------------------
    # STAGE 3: Submission Information Extraction (Step 14)
    # -------------------------------------------------------------
    extract_and_save_submission_info(db=db, website_id=website_id)

    # -------------------------------------------------------------
    # STAGE 4: AI Semantic Verification (Step 15)
    # -------------------------------------------------------------
    await verify_website_record(db=db, website_id=website_id, api_key=gemini_api_key)

    # -------------------------------------------------------------
    # STAGE 5: AI Website Semantic Analysis (Step 16)
    # -------------------------------------------------------------
    niche_keyword = keyword or website.name or website.domain
    await analyze_website_record(
        db=db,
        website_id=website_id,
        search_keyword=niche_keyword,
        api_key=gemini_api_key,
    )

    # -------------------------------------------------------------
    # STAGE 6: Deterministic Website Scoring (Step 17)
    # -------------------------------------------------------------
    score_website_record(db=db, website_id=website_id)

    # Update associated SearchResult statuses
    for sr in db.scalars(select(SearchResult).where(SearchResult.website_id == website.id)).all():
        sr.status = "processed"

    db.commit()
    db.refresh(website)

    logger.info(
        f"Completed pipeline for Website #{website_id} ({website.domain}): "
        f"Quality Score = {website.analysis.quality_score if website.analysis else 0}/100"
    )
    return website


async def process_search_pipeline(
    search_id: int,
    max_concurrency: Optional[int] = None,
    gemini_api_key: Optional[str] = None,
) -> None:
    """Background worker to process all candidate websites belonging to a search query concurrently.

    Args:
        search_id: ID of the search to process.
        max_concurrency: Maximum number of concurrent website pipelines (defaults to settings.MAX_CONCURRENT_WEBSITES).
        gemini_api_key: Optional Gemini API key override.
    """
    effective_concurrency = (
        max_concurrency if max_concurrency is not None else settings.MAX_CONCURRENT_WEBSITES
    )
    # Ensure concurrency limit is strictly bounded between 1 and configured maximum limit
    effective_concurrency = max(1, min(effective_concurrency, settings.PIPELINE_MAX_CONCURRENCY_LIMIT))

    db = SessionLocal()
    try:
        search = db.get(Search, search_id)
        if not search:
            logger.error(f"Search #{search_id} not found for background pipeline processing.")
            return

        if search.status == "processing":
            logger.info(f"Search #{search_id} is already in 'processing' status. Skipping duplicate run.")
            return

        search.status = "processing"
        db.commit()

        # Fetch all associated website IDs for this search
        website_ids = list(
            db.scalars(
                select(SearchResult.website_id).where(SearchResult.search_id == search_id)
            ).all()
        )
        keyword = search.keyword
    finally:
        db.close()

    if not website_ids:
        db = SessionLocal()
        try:
            search = db.get(Search, search_id)
            if search:
                search.status = "no_results"
                db.commit()
        finally:
            db.close()
        return

    logger.info(
        f"Starting batch pipeline processing for Search #{search_id} "
        f"({len(website_ids)} websites, concurrency={effective_concurrency})..."
    )

    semaphore = asyncio.Semaphore(effective_concurrency)

    async def _process_worker(w_id: int):
        async with semaphore:
            worker_db = SessionLocal()
            try:
                await process_single_website_pipeline(
                    db=worker_db,
                    website_id=w_id,
                    keyword=keyword,
                    gemini_api_key=gemini_api_key,
                )
            except Exception as e:
                logger.error(f"Error processing Website #{w_id} in pipeline: {e}")
                try:
                    worker_db.rollback()
                except Exception:
                    pass
            finally:
                worker_db.close()

    # Run batch with controlled, bounded concurrency
    tasks = [_process_worker(w_id) for w_id in website_ids]
    await asyncio.gather(*tasks, return_exceptions=True)

    # Mark search as completed
    final_db = SessionLocal()
    try:
        search = final_db.get(Search, search_id)
        if search:
            search.status = "completed"
            final_db.commit()
            logger.info(f"Successfully finished search pipeline for Search #{search_id}.")
    finally:
        final_db.close()



def get_search_pipeline_progress(db: Session, search_id: int) -> Dict[str, Any]:
    """Calculate realtime progress breakdown and completion status for a search run.

    Args:
        db: SQLAlchemy database session.
        search_id: Search ID to query.

    Returns:
        dict containing total_websites, crawled_count, verified_count, analyzed_count,
        scored_count, progress_percentage, status, and is_completed.
    """
    search = db.get(Search, search_id)
    if not search:
        raise ValueError(f"Search with ID {search_id} not found.")

    # Base query for websites attached to this search
    website_ids = list(
        db.scalars(
            select(SearchResult.website_id).where(SearchResult.search_id == search_id)
        ).all()
    )
    total_websites = len(website_ids)

    if total_websites == 0:
        return {
            "search_id": search_id,
            "status": search.status,
            "total_websites": 0,
            "crawled_count": 0,
            "verified_count": 0,
            "analyzed_count": 0,
            "scored_count": 0,
            "progress_percentage": 100.0 if search.status in ("completed", "no_results") else 0.0,
            "is_completed": search.status in ("completed", "no_results"),
        }

    # Count crawled websites
    crawled_count = db.scalar(
        select(func.count(distinct(Website.id)))
        .where(
            Website.id.in_(website_ids),
            Website.crawl_status.in_(["success", "crawled", "failed"])
        )
    ) or 0

    # Count verified websites
    verified_count = db.scalar(
        select(func.count(distinct(GuestPostInformation.website_id)))
        .where(
            GuestPostInformation.website_id.in_(website_ids),
            GuestPostInformation.verification_status.is_not(None),
            GuestPostInformation.verification_status != "unverified"
        )
    ) or 0

    # Count analyzed websites
    analyzed_count = db.scalar(
        select(func.count(distinct(WebsiteAnalysis.website_id)))
        .where(
            WebsiteAnalysis.website_id.in_(website_ids),
            WebsiteAnalysis.analysis_status.in_(["completed", "fallback", "failed"])
        )
    ) or 0

    # Count scored websites
    scored_count = db.scalar(
        select(func.count(distinct(WebsiteAnalysis.website_id)))
        .where(
            WebsiteAnalysis.website_id.in_(website_ids),
            WebsiteAnalysis.quality_score.is_not(None)
        )
    ) or 0

    progress_percentage = round((scored_count / total_websites) * 100.0, 1)
    is_completed = search.status == "completed" or scored_count >= total_websites

    return {
        "search_id": search_id,
        "status": search.status,
        "total_websites": total_websites,
        "crawled_count": crawled_count,
        "verified_count": verified_count,
        "analyzed_count": analyzed_count,
        "scored_count": scored_count,
        "progress_percentage": progress_percentage,
        "is_completed": is_completed,
    }
