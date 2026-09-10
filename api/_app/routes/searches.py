"""Search endpoints for managing search records and discovery (Steps 10-22)."""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db

from app.dependencies import get_current_user, get_optional_current_user
from app.models.user import User
from app.schemas.search import (
    SearchCreate,
    SearchResponse,
    SearchListResponse,
    SearchSummaryResponse,
    SearchProgressResponse,
    SearchDeleteResponse,
)
from app.services import search_service
from app.services.pipeline import process_search_pipeline, get_search_pipeline_progress

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/searches", tags=["Searches"])


@router.post(
    "",
    response_model=SearchSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new search request and execute candidate discovery",
)
async def create_search_endpoint(
    search_in: SearchCreate,
    background_tasks: BackgroundTasks,
    auto_process: bool = Query(True, description="Automatically trigger background pipeline processing"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Create a new search record in the database and run candidate discovery if configured."""
    user_id = current_user.id if current_user else None
    search = search_service.create_search(db=db, search_in=search_in, user_id=user_id)

    # Attempt to execute discovery with configured search provider
    try:
        search = await search_service.execute_search_discovery(db=db, search=search)
        if auto_process and search.status == "discovered":
            background_tasks.add_task(process_search_pipeline, search.id, settings.MAX_CONCURRENT_WEBSITES)
    except Exception as e:
        logger.warning(f"Discovery execution encountered an error for search #{search.id}: {e}")

    # Re-fetch or count results
    results_count = len(search.results) if search.results else 0

    return SearchSummaryResponse(
        id=search.id,
        user_id=search.user_id,
        keyword=search.keyword,
        requested_website_count=search.requested_website_count,
        status=search.status,
        created_at=search.created_at,
        results_count=results_count,
    )


@router.post(
    "/{search_id}/discover",
    response_model=SearchResponse,
    summary="Trigger candidate website discovery for a search",
)
async def trigger_discovery_endpoint(
    search_id: int,
    background_tasks: BackgroundTasks,
    auto_process: bool = Query(True, description="Automatically trigger background pipeline processing after discovery"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Manually trigger candidate URL discovery for an existing search record."""
    user_id = current_user.id if current_user else None
    search = search_service.get_search_by_id(db=db, search_id=search_id, user_id=user_id)
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found",
        )

    search = await search_service.execute_search_discovery(db=db, search=search)
    if auto_process and search.status == "discovered":
        background_tasks.add_task(process_search_pipeline, search.id, settings.MAX_CONCURRENT_WEBSITES)
    return search_service.build_search_response(search)


@router.post(
    "/{search_id}/process",
    response_model=SearchProgressResponse,
    summary="Trigger full batch pipeline processing for a search (Step 19 & 23)",
)
async def process_search_pipeline_endpoint(
    search_id: int,
    background_tasks: BackgroundTasks,
    concurrency: int = Query(
        default=settings.MAX_CONCURRENT_WEBSITES,
        ge=1,
        le=settings.PIPELINE_MAX_CONCURRENCY_LIMIT,
        description="Max concurrent website processors",
    ),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Trigger background batch crawling, detection, verification, analysis, and scoring for all search candidates."""
    user_id = current_user.id if current_user else None
    search = search_service.get_search_by_id(db=db, search_id=search_id, user_id=user_id)
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found",
        )

    background_tasks.add_task(process_search_pipeline, search_id, concurrency)
    progress = get_search_pipeline_progress(db=db, search_id=search_id)
    return SearchProgressResponse(**progress)



@router.get(
    "/{search_id}/progress",
    response_model=SearchProgressResponse,
    summary="Get realtime search pipeline progress breakdown (Step 19)",
)
async def get_search_progress_endpoint(
    search_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Get the current progress, count of crawled, verified, analyzed, and scored websites for a search."""
    user_id = current_user.id if current_user else None
    search = search_service.get_search_by_id(db=db, search_id=search_id, user_id=user_id)
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found",
        )

    try:
        progress = get_search_pipeline_progress(db=db, search_id=search_id)
        return SearchProgressResponse(**progress)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "",
    response_model=SearchListResponse,
    summary="List search history",
)
@router.get(
    "/history",
    response_model=SearchListResponse,
    summary="List search history (alias)",
)
async def list_searches_endpoint(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=100, description="Limit of results per page"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """List historical search queries with pagination, scoped to current user if authenticated."""
    user_id = current_user.id if current_user else None
    summaries, total = search_service.list_searches(db=db, user_id=user_id, skip=skip, limit=limit)
    return SearchListResponse(searches=summaries, total=total)


@router.get(
    "/{search_id}",
    response_model=SearchResponse,
    summary="Get search details by ID",
)
async def get_search_endpoint(
    search_id: int,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed search result including associated discovered websites and metrics."""
    user_id = current_user.id if current_user else None
    search = search_service.get_search_by_id(db=db, search_id=search_id, user_id=user_id)
    if not search:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found",
        )
    return search_service.build_search_response(search)


@router.delete(
    "/{search_id}",
    response_model=SearchDeleteResponse,
    summary="Delete search history record (Step 22)",
)
async def delete_search_endpoint(
    search_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a search record belonging to the authenticated user."""
    deleted = search_service.delete_search(db=db, search_id=search_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Search with ID {search_id} not found",
        )
    return SearchDeleteResponse(
        success=True,
        id=search_id,
        message=f"Search #{search_id} deleted successfully",
    )

