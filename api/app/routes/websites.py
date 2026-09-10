"""Website endpoints for querying website metadata, quality analysis, single-page crawls, guest post detection, submission extraction, AI verification, AI analysis, scoring, and smart filters."""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user, get_optional_current_user
from app.models.user import User
from app.schemas.website import (
    WebsiteResponse,
    WebsiteDetailResponse,
    WebsiteAnalysisResponse,
    GuestPostInfoResponse,
    CrawlResultResponse,
    GuestPostDetectionResponse,
    SubmissionExtractionResponse,
    AIVerificationResponse,
    AIAnalysisResponse,
    ScoringResponse,
    ScoringBreakdown,
    ScoreCategoryBreakdown,
    WebsiteFilterResponse,
    SaveWebsiteResponse,
    SavedWebsiteItemResponse,
    SavedWebsiteListResponse,
)
from app.services import website_service, saved_service
from app.services.csv_exporter import generate_websites_csv, create_csv_response
from app.services.crawler import crawl_website_record
from app.services.guest_post_detector import detect_guest_post_for_website
from app.services.submission_extractor import extract_and_save_submission_info
from app.services.ai_verifier import verify_website_record
from app.services.ai_analyzer import analyze_website_record
from app.services.scoring import score_website_record
from app.services.filtering import filter_websites, WebsiteFilterParams
from app.services.pipeline import process_single_website_pipeline

router = APIRouter(prefix="/websites", tags=["Websites"])


@router.get(
    "",
    response_model=list[WebsiteResponse],
    summary="List discovered websites",
)
async def list_websites_endpoint(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Limit of results per page"),
    db: Session = Depends(get_db),
):
    """List discovered websites with pagination."""
    websites, _ = website_service.list_websites(db=db, skip=skip, limit=limit)
    return [WebsiteResponse.model_validate(w) for w in websites]


@router.get(
    "/filter",
    response_model=WebsiteFilterResponse,
    summary="Filter, search, sort, and paginate website opportunities (Step 18)",
)
async def filter_websites_endpoint(
    search_id: Optional[int] = Query(None, description="Scope results to specific Search ID"),
    guest_post_status: Optional[str] = Query(None, description="Guest post acceptance ('accepting', 'not_accepting', 'pending', 'unknown', 'all')"),
    acceptance: Optional[str] = Query(None, description="Alias for guest_post_status"),
    pricing: Optional[str] = Query(None, description="Pricing model ('free', 'paid', 'unknown', 'all')"),
    min_quality_score: Optional[int] = Query(None, description="Minimum quality score (0-100)"),
    min_relevance_score: Optional[int] = Query(None, description="Minimum relevance score (0-100)"),
    min_content_quality: Optional[int] = Query(None, description="Minimum content quality score (0-100)"),
    min_content_quality_score: Optional[int] = Query(None, description="Alias for min_content_quality"),
    verification_status: Optional[str] = Query(None, description="Verification status ('verified', 'rejected', 'uncertain', 'unverified', 'all')"),
    min_ai_confidence: Optional[int] = Query(None, description="Minimum AI confidence (0-100)"),
    submission_method: Optional[str] = Query(None, description="Submission method ('email', 'form', 'google_form', 'typeform')"),
    niche: Optional[str] = Query(None, description="Filter by niche / keyword text in stored data"),
    keyword: Optional[str] = Query(None, description="Alias for niche filter"),
    crawl_status: Optional[str] = Query(None, description="Crawl status ('pending', 'crawled', 'failed', 'all')"),
    sort_by: str = Query("quality_score", description="Sort field ('quality_score', 'relevance_score', 'content_quality', 'domain')"),
    sort_order: str = Query("desc", description="Sort order ('asc', 'desc')"),
    page: int = Query(1, description="Page number (1-indexed)"),
    page_size: int = Query(25, description="Results per page (1-100)"),
    skip: Optional[int] = Query(None, description="Optional offset for legacy pagination"),
    limit: Optional[int] = Query(None, description="Optional limit for legacy pagination"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Dynamically query and filter already-scored websites using stored criteria."""
    try:
        calc_page = page
        calc_page_size = page_size

        # Support legacy skip/limit parameters if explicitly passed
        if skip is not None and limit is not None and limit > 0:
            calc_page_size = limit
            calc_page = (skip // limit) + 1

        filter_params = WebsiteFilterParams(
            search_id=search_id,
            guest_post_status=guest_post_status,
            acceptance=acceptance,
            pricing=pricing,
            min_quality_score=min_quality_score,
            min_relevance_score=min_relevance_score,
            min_content_quality=min_content_quality,
            min_content_quality_score=min_content_quality_score,
            verification_status=verification_status,
            min_ai_confidence=min_ai_confidence,
            submission_method=submission_method,
            niche=niche,
            keyword=keyword,
            crawl_status=crawl_status,
            sort_by=sort_by,
            sort_order=sort_order,
            page=calc_page,
            page_size=calc_page_size,
        )
        websites, total_count, res_page, res_page_size, total_pages, filters_applied = filter_websites(
            db=db, params=filter_params
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    saved_ids = saved_service.get_user_saved_website_ids(
        db=db,
        website_ids=[w.id for w in websites],
        user_id=current_user.id if current_user else None,
    )

    items = [
        WebsiteDetailResponse(
            id=w.id,
            domain=w.domain,
            url=w.url,
            name=w.name,
            crawl_status=w.crawl_status,
            last_crawled_at=w.last_crawled_at,
            http_status=w.http_status,
            final_url=w.final_url,
            content_type=w.content_type,
            created_at=w.created_at,
            updated_at=w.updated_at,
            analysis=WebsiteAnalysisResponse.model_validate(w.analysis) if w.analysis else None,
            guest_post_info=GuestPostInfoResponse.model_validate(w.guest_post_info) if w.guest_post_info else None,
            is_saved=w.id in saved_ids,
        )
        for w in websites
    ]

    return WebsiteFilterResponse(
        items=items,
        total=total_count,
        page=res_page,
        page_size=res_page_size,
        total_pages=total_pages,
        filters_applied=filters_applied,
    )


@router.get(
    "/export/csv",
    summary="Export filtered website opportunities to CSV (Step 20)",
)
async def export_websites_csv_endpoint(
    search_id: Optional[int] = Query(None, description="Scope results to specific Search ID"),
    guest_post_status: Optional[str] = Query(None, description="Guest post acceptance ('accepting', 'not_accepting', 'pending', 'unknown', 'all')"),
    acceptance: Optional[str] = Query(None, description="Alias for guest_post_status"),
    pricing: Optional[str] = Query(None, description="Pricing model ('free', 'paid', 'unknown', 'all')"),
    min_quality_score: Optional[int] = Query(None, description="Minimum quality score (0-100)"),
    min_relevance_score: Optional[int] = Query(None, description="Minimum relevance score (0-100)"),
    min_content_quality: Optional[int] = Query(None, description="Minimum content quality score (0-100)"),
    min_content_quality_score: Optional[int] = Query(None, description="Alias for min_content_quality"),
    verification_status: Optional[str] = Query(None, description="Verification status ('verified', 'rejected', 'uncertain', 'unverified', 'all')"),
    min_ai_confidence: Optional[int] = Query(None, description="Minimum AI confidence (0-100)"),
    submission_method: Optional[str] = Query(None, description="Submission method ('email', 'form', 'google_form', 'typeform')"),
    niche: Optional[str] = Query(None, description="Filter by niche / keyword text in stored data"),
    keyword: Optional[str] = Query(None, description="Alias for niche filter"),
    crawl_status: Optional[str] = Query(None, description="Crawl status ('pending', 'crawled', 'failed', 'all')"),
    sort_by: str = Query("quality_score", description="Sort field ('quality_score', 'relevance_score', 'content_quality', 'domain')"),
    sort_order: str = Query("desc", description="Sort order ('asc', 'desc')"),
    db: Session = Depends(get_db),
):
    """Export all filtered website opportunities matching the criteria to an attachment CSV file."""
    try:
        filter_params = WebsiteFilterParams(
            search_id=search_id,
            guest_post_status=guest_post_status,
            acceptance=acceptance,
            pricing=pricing,
            min_quality_score=min_quality_score,
            min_relevance_score=min_relevance_score,
            min_content_quality=min_content_quality,
            min_content_quality_score=min_content_quality_score,
            verification_status=verification_status,
            min_ai_confidence=min_ai_confidence,
            submission_method=submission_method,
            niche=niche,
            keyword=keyword,
            crawl_status=crawl_status,
            sort_by=sort_by,
            sort_order=sort_order,
            page=1,
            page_size=100,
        )
        websites = []
        current_page = 1
        while True:
            filter_params.page = current_page
            batch, total_count, _, _, total_pages, _ = filter_websites(db=db, params=filter_params)
            websites.extend(batch)
            if current_page >= total_pages or len(batch) == 0:
                break
            current_page += 1
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    csv_content = generate_websites_csv(websites)
    return create_csv_response(csv_content, filename="guest_posting_opportunities.csv")


@router.get(
    "/saved/export/csv",
    summary="Export all saved websites to CSV (Step 20 & 21)",
)
async def export_saved_websites_csv_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export all saved/bookmarked websites for the authenticated user to an attachment CSV file."""
    websites = saved_service.get_all_saved_websites_for_export(db=db, user_id=current_user.id)
    csv_content = generate_websites_csv(websites)
    return create_csv_response(csv_content, filename="saved_websites.csv")


@router.get(
    "/saved",
    response_model=SavedWebsiteListResponse,
    summary="List saved / bookmarked websites (Step 20 & 21)",
)
async def list_saved_websites_endpoint(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(25, ge=1, le=100, description="Results per page (1-100)"),
    skip: Optional[int] = Query(None, description="Optional offset for legacy pagination"),
    limit: Optional[int] = Query(None, description="Optional limit for legacy pagination"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List bookmarked websites with preloaded analysis, guest post data, and pagination for authenticated user."""
    calc_page = page
    calc_page_size = page_size
    if skip is not None and limit is not None and limit > 0:
        calc_page_size = limit
        calc_page = (skip // limit) + 1

    items, total_count, res_page, res_page_size, total_pages = saved_service.get_saved_websites(
        db=db, user_id=current_user.id, page=calc_page, page_size=calc_page_size
    )

    return SavedWebsiteListResponse(
        items=[SavedWebsiteItemResponse(**item) for item in items],
        total=total_count,
        page=res_page,
        page_size=res_page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{website_id}",
    response_model=WebsiteDetailResponse,
    summary="Get website details and analysis by ID",
)
async def get_website_endpoint(
    website_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Get full website details including crawl status, AI quality breakdown, and guest posting rules."""
    website = website_service.get_website_by_id(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    analysis_res = (
        WebsiteAnalysisResponse.model_validate(website.analysis)
        if website.analysis
        else None
    )
    guest_post_res = (
        GuestPostInfoResponse.model_validate(website.guest_post_info)
        if website.guest_post_info
        else None
    )

    is_saved = saved_service.is_website_saved(
        db=db,
        website_id=website.id,
        user_id=current_user.id if current_user else None,
    )

    return WebsiteDetailResponse(
        id=website.id,
        domain=website.domain,
        url=website.url,
        name=website.name,
        crawl_status=website.crawl_status,
        last_crawled_at=website.last_crawled_at,
        http_status=website.http_status,
        final_url=website.final_url,
        content_type=website.content_type,
        created_at=website.created_at,
        updated_at=website.updated_at,
        analysis=analysis_res,
        guest_post_info=guest_post_res,
        is_saved=is_saved,
    )


@router.post(
    "/{website_id}/crawl",
    response_model=CrawlResultResponse,
    summary="Execute single-page crawl for candidate website",
)
async def crawl_website_endpoint(
    website_id: int,
    db: Session = Depends(get_db),
):
    """Fetch HTML content for a specific candidate website URL without link recursion."""
    website, crawl_res = await crawl_website_record(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    return CrawlResultResponse(
        original_url=crawl_res.original_url,
        final_url=crawl_res.final_url,
        status_code=crawl_res.status_code,
        content_type=crawl_res.content_type,
        content_length=crawl_res.content_length,
        response_time_ms=crawl_res.response_time_ms,
        title=crawl_res.title,
        html_snippet=crawl_res.html[:200] if crawl_res.html else None,
        success=crawl_res.success,
        error_type=crawl_res.error_type,
        error_message=crawl_res.error_message,
    )


@router.post(
    "/{website_id}/detect-guest-post",
    response_model=GuestPostDetectionResponse,
    summary="Run deterministic guest post detection on crawled website HTML",
)
async def detect_guest_post_endpoint(
    website_id: int,
    db: Session = Depends(get_db),
):
    """Analyze crawled HTML to detect guest-posting signals, confidence, and evidence."""
    website, detection_res = detect_guest_post_for_website(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    return GuestPostDetectionResponse(
        website_id=website.id,
        detected=detection_res.detected,
        confidence=detection_res.confidence,
        strong_signals=detection_res.strong_signals,
        medium_signals=detection_res.medium_signals,
        weak_signals=detection_res.weak_signals,
        negative_signals=detection_res.negative_signals,
        has_conflicts=detection_res.has_conflicts,
        evidence_snippets=detection_res.evidence_snippets,
        summary_reason=detection_res.summary_reason,
    )


@router.post(
    "/{website_id}/extract-submission",
    response_model=SubmissionExtractionResponse,
    summary="Extract submission channels, emails, forms, and pricing from crawled website HTML",
)
async def extract_submission_endpoint(
    website_id: int,
    db: Session = Depends(get_db),
):
    """Deterministically inspect crawled HTML to extract submission emails, form URLs, guidelines, and pricing."""
    website, extraction_res = extract_and_save_submission_info(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    return SubmissionExtractionResponse(
        website_id=website.id,
        submission_methods=extraction_res.submission_methods,
        primary_submission_method=extraction_res.primary_submission_method,
        submission_emails=extraction_res.submission_emails,
        primary_email=extraction_res.primary_email,
        submission_urls=extraction_res.submission_urls,
        primary_submission_url=extraction_res.primary_submission_url,
        guidelines_urls=extraction_res.guidelines_urls,
        primary_guidelines_url=extraction_res.primary_guidelines_url,
        is_paid=extraction_res.is_paid,
        pricing_model=extraction_res.pricing_model,
        price_amount=extraction_res.price_amount,
        evidence_snippets=extraction_res.evidence_snippets,
        has_submission_channel=extraction_res.has_submission_channel,
    )


@router.post(
    "/{website_id}/verify",
    response_model=AIVerificationResponse,
    summary="Execute Gemini AI semantic verification for candidate website",
)
async def verify_website_endpoint(
    website_id: int,
    db: Session = Depends(get_db),
):
    """Semantically verify guest post opportunities and cross-validate deterministic extraction results with Gemini."""
    website, verification_res = await verify_website_record(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    return AIVerificationResponse(
        website_id=website.id,
        verification_status=verification_res.verification_status,
        accepts_guest_posts=verification_res.accepts_guest_posts,
        confidence=verification_res.confidence,
        reason=verification_res.reason,
        guest_post_evidence=verification_res.guest_post_evidence,
        submission_method=verification_res.submission_method,
        submission_email=verification_res.submission_email,
        submission_url=verification_res.submission_url,
        guidelines_url=verification_res.guidelines_url,
        pricing=verification_res.pricing,
        corrections=verification_res.corrections,
        verified_at=datetime.now(timezone.utc),
    )


@router.post(
    "/{website_id}/analyze",
    response_model=AIAnalysisResponse,
    summary="Execute Gemini AI semantic website analysis (Step 16)",
)
async def analyze_website_endpoint(
    website_id: int,
    keyword: Optional[str] = Query(None, description="Optional search keyword to evaluate relevance against"),
    db: Session = Depends(get_db),
):
    """Semantically analyze website niche, content quality, trust signals, and editorial standards with Gemini."""
    website, analysis_res = await analyze_website_record(
        db=db,
        website_id=website_id,
        search_keyword=keyword
    )
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    return AIAnalysisResponse(
        website_id=website.id,
        primary_niche=analysis_res.primary_niche,
        topics=analysis_res.topics,
        niche_confidence=analysis_res.niche_confidence,
        relevance_score=analysis_res.relevance_score,
        relevance_reason=analysis_res.relevance_reason,
        content_quality_score=analysis_res.content_quality_score,
        content_quality_reason=analysis_res.content_quality_reason,
        trust_signals=analysis_res.trust_signals,
        editorial_standards=analysis_res.editorial_standards,
        strengths=analysis_res.strengths,
        weaknesses=analysis_res.weaknesses,
        analysis_confidence=analysis_res.analysis_confidence,
        evidence=analysis_res.evidence,
        warnings=analysis_res.warnings,
        analysis_status=analysis_res.analysis_status,
        analyzed_at=datetime.now(timezone.utc),
    )


@router.post(
    "/{website_id}/score",
    response_model=ScoringResponse,
    summary="Calculate deterministic quality score (Step 17)",
)
async def score_website_endpoint(
    website_id: int,
    db: Session = Depends(get_db),
):
    """Calculate bounded, explainable 0-100 quality score combining Steps 13-16 results."""
    website, scoring_res = score_website_record(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    breakdown_dto = ScoringBreakdown(
        guest_post_acceptance=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["guest_post_acceptance"].points,
            max_points=scoring_res.breakdown["guest_post_acceptance"].max_points,
            reason=scoring_res.breakdown["guest_post_acceptance"].reason,
        ),
        niche_relevance=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["niche_relevance"].points,
            max_points=scoring_res.breakdown["niche_relevance"].max_points,
            reason=scoring_res.breakdown["niche_relevance"].reason,
        ),
        content_quality=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["content_quality"].points,
            max_points=scoring_res.breakdown["content_quality"].max_points,
            reason=scoring_res.breakdown["content_quality"].reason,
        ),
        trust_signals=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["trust_signals"].points,
            max_points=scoring_res.breakdown["trust_signals"].max_points,
            reason=scoring_res.breakdown["trust_signals"].reason,
        ),
        editorial_standards=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["editorial_standards"].points,
            max_points=scoring_res.breakdown["editorial_standards"].max_points,
            reason=scoring_res.breakdown["editorial_standards"].reason,
        ),
        ai_verification=ScoreCategoryBreakdown(
            points=scoring_res.breakdown["ai_verification"].points,
            max_points=scoring_res.breakdown["ai_verification"].max_points,
            reason=scoring_res.breakdown["ai_verification"].reason,
        ),
    )

    return ScoringResponse(
        website_id=website.id,
        quality_score=scoring_res.quality_score,
        breakdown=breakdown_dto,
        scoring_status=scoring_res.scoring_status,
        scored_at=scoring_res.scored_at,
    )


@router.post(
    "/{website_id}/process",
    response_model=WebsiteDetailResponse,
    summary="Execute the entire 6-stage pipeline for a single website (Step 19)",
)
async def process_website_pipeline_endpoint(
    website_id: int,
    keyword: Optional[str] = Query(None, description="Optional niche / keyword context"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Execute end-to-end HTML crawling, guest post detection, submission extraction, AI verification, analysis, and scoring."""
    website = website_service.get_website_by_id(db=db, website_id=website_id)
    if not website:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Website with ID {website_id} not found",
        )

    processed_website = await process_single_website_pipeline(
        db=db,
        website_id=website_id,
        keyword=keyword,
    )

    is_saved = saved_service.is_website_saved(
        db=db,
        website_id=processed_website.id,
        user_id=current_user.id if current_user else None,
    )

    return WebsiteDetailResponse(
        id=processed_website.id,
        domain=processed_website.domain,
        url=processed_website.url,
        name=processed_website.name,
        crawl_status=processed_website.crawl_status,
        last_crawled_at=processed_website.last_crawled_at,
        http_status=processed_website.http_status,
        final_url=processed_website.final_url,
        content_type=processed_website.content_type,
        created_at=processed_website.created_at,
        updated_at=processed_website.updated_at,
        analysis=WebsiteAnalysisResponse.model_validate(processed_website.analysis) if processed_website.analysis else None,
        guest_post_info=GuestPostInfoResponse.model_validate(processed_website.guest_post_info) if processed_website.guest_post_info else None,
        is_saved=is_saved,
    )


@router.post(
    "/{website_id}/save",
    response_model=SaveWebsiteResponse,
    summary="Bookmark / save a website opportunity (Step 20 & 21)",
)
async def save_website_endpoint(
    website_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a candidate website to the bookmarked opportunities list for current user idempotently."""
    try:
        success, is_saved, message = saved_service.save_website(
            db=db, website_id=website_id, user_id=current_user.id
        )
        return SaveWebsiteResponse(
            success=success,
            website_id=website_id,
            is_saved=is_saved,
            message=message,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete(
    "/{website_id}/save",
    response_model=SaveWebsiteResponse,
    summary="Remove a website from saved list (Step 20 & 21)",
)
async def unsave_website_endpoint(
    website_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a candidate website from the saved opportunities list for current user idempotently."""
    try:
        success, is_saved, message = saved_service.unsave_website(
            db=db, website_id=website_id, user_id=current_user.id
        )
        return SaveWebsiteResponse(
            success=success,
            website_id=website_id,
            is_saved=is_saved,
            message=message,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

