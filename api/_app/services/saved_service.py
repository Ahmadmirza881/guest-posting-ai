"""Saved websites management and database repository service (Step 20 & 21).

Provides user-scoped bookmarking, listing, and export operations.
"""

import math
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Any, Optional, Set
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload
from app.models.website import Website
from app.models.saved_website import SavedWebsite


def save_website(db: Session, website_id: int, user_id: int) -> Tuple[bool, bool, str]:
    """Bookmark / save a website opportunity for a specific user idempotently.

    Args:
        db: SQLAlchemy database session.
        website_id: Target Website ID.
        user_id: Authenticated user ID.

    Returns:
        Tuple of (success, is_saved, message)

    Raises:
        ValueError: If website_id does not exist.
    """
    website = db.get(Website, website_id)
    if not website:
        raise ValueError(f"Website with ID {website_id} not found.")

    # Check existing saved record for this user
    stmt = select(SavedWebsite).where(
        SavedWebsite.user_id == user_id,
        SavedWebsite.website_id == website_id,
    )
    existing = db.scalars(stmt).first()

    if existing:
        return True, True, "Website is already saved."

    saved_entry = SavedWebsite(
        user_id=user_id,
        website_id=website_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(saved_entry)
    db.commit()
    db.refresh(saved_entry)

    return True, True, "Website saved successfully."


def unsave_website(db: Session, website_id: int, user_id: int) -> Tuple[bool, bool, str]:
    """Remove a website opportunity from a specific user's saved list idempotently.

    Args:
        db: SQLAlchemy database session.
        website_id: Target Website ID.
        user_id: Authenticated user ID.

    Returns:
        Tuple of (success, is_saved, message)

    Raises:
        ValueError: If website_id does not exist.
    """
    website = db.get(Website, website_id)
    if not website:
        raise ValueError(f"Website with ID {website_id} not found.")

    stmt = select(SavedWebsite).where(
        SavedWebsite.user_id == user_id,
        SavedWebsite.website_id == website_id,
    )
    existing = db.scalars(stmt).first()

    if not existing:
        return True, False, "Website was not in saved list."

    db.delete(existing)
    db.commit()

    return True, False, "Website removed from saved list."


def get_saved_websites(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Dict[str, Any]], int, int, int, int]:
    """Query paginated saved websites for a specific user.

    Prevents N+1 queries by eager-loading related Website, analysis, and guest post entities.

    Args:
        db: SQLAlchemy database session.
        user_id: Authenticated user ID.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        Tuple of (items, total_count, page, page_size, total_pages)
    """
    # Count total saved websites for this user only
    total_count = (
        db.scalar(
            select(func.count(SavedWebsite.id)).where(SavedWebsite.user_id == user_id)
        )
        or 0
    )
    total_pages = math.ceil(total_count / page_size) if page_size > 0 else 0

    if total_count == 0:
        return [], 0, page, page_size, 0

    offset = (page - 1) * page_size

    stmt = (
        select(SavedWebsite)
        .where(SavedWebsite.user_id == user_id)
        .options(
            joinedload(SavedWebsite.website).joinedload(Website.analysis),
            joinedload(SavedWebsite.website).joinedload(Website.guest_post_info),
        )
        .order_by(SavedWebsite.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )

    saved_records = list(db.scalars(stmt).all())

    items: List[Dict[str, Any]] = []
    for sr in saved_records:
        w = sr.website
        analysis = w.analysis if w else None
        gp = w.guest_post_info if w else None

        status_str = "pending"
        accepts_gp = None
        if gp:
            accepts_gp = gp.accepts_guest_posts
            if gp.accepts_guest_posts is True:
                status_str = "accepting"
            elif gp.accepts_guest_posts is False:
                status_str = "not_accepting"
            elif gp.verification_status:
                status_str = gp.verification_status

        items.append({
            "id": sr.id,
            "website_id": sr.website_id,
            "name": w.name if w else None,
            "domain": w.domain if w else "",
            "url": w.url if w else "",
            "niche": analysis.primary_niche if analysis else None,
            "description": None,
            "guest_post_status": status_str,
            "accepts_guest_posts": accepts_gp,
            "pricing": gp.pricing if gp else None,
            "submission_method": gp.submission_method if gp else None,
            "relevance_score": analysis.relevance_score if analysis else None,
            "content_quality_score": analysis.content_quality_score if analysis else None,
            "quality_score": analysis.quality_score if analysis else None,
            "verification_status": gp.verification_status if gp else "unverified",
            "submission_url": gp.submission_url if gp else None,
            "guidelines_url": gp.guidelines_url if gp else None,
            "saved_date": sr.created_at,
            "is_saved": True,
        })

    return items, total_count, page, page_size, total_pages


def get_all_saved_websites_for_export(db: Session, user_id: int) -> List[Website]:
    """Retrieve all saved websites for a specific user with analysis and guest posting records preloaded for CSV export.

    Args:
        db: SQLAlchemy database session.
        user_id: Authenticated user ID.

    Returns:
        List of Website ORM entities saved by the user.
    """
    stmt = (
        select(SavedWebsite)
        .where(SavedWebsite.user_id == user_id)
        .options(
            joinedload(SavedWebsite.website).joinedload(Website.analysis),
            joinedload(SavedWebsite.website).joinedload(Website.guest_post_info),
        )
        .order_by(SavedWebsite.created_at.desc())
    )
    saved_records = list(db.scalars(stmt).all())
    websites = [sr.website for sr in saved_records if sr.website is not None]
    return websites


def is_website_saved(db: Session, website_id: int, user_id: Optional[int]) -> bool:
    """Check if a website is saved by a given user. Returns False for unauthenticated access."""
    if not user_id:
        return False
    stmt = select(SavedWebsite.id).where(
        SavedWebsite.user_id == user_id,
        SavedWebsite.website_id == website_id,
    )
    return db.scalar(stmt) is not None


def get_user_saved_website_ids(db: Session, website_ids: List[int], user_id: Optional[int]) -> Set[int]:
    """Batch retrieve the set of website IDs saved by a specific user from a list of candidates."""
    if not user_id or not website_ids:
        return set()
    stmt = select(SavedWebsite.website_id).where(
        SavedWebsite.user_id == user_id,
        SavedWebsite.website_id.in_(website_ids),
    )
    return set(db.scalars(stmt).all())
