"""Service layer for website and analysis database operations."""

from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from app.models.website import Website


def get_website_by_id(db: Session, website_id: int) -> Optional[Website]:
    """Retrieve a website by ID including its analysis and guest post information."""
    stmt = (
        select(Website)
        .where(Website.id == website_id)
        .options(
            selectinload(Website.analysis),
            selectinload(Website.guest_post_info),
        )
    )
    return db.scalars(stmt).first()


def list_websites(
    db: Session, skip: int = 0, limit: int = 50
) -> tuple[list[Website], int]:
    """List websites with total count."""
    total = db.scalar(select(func.count(Website.id))) or 0
    stmt = (
        select(Website)
        .options(
            selectinload(Website.analysis),
            selectinload(Website.guest_post_info),
        )
        .order_by(Website.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    websites = db.scalars(stmt).all()
    return list(websites), total
