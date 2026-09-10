"""Saved website database model (Step 20)."""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.website import Website
    from app.models.user import User


class SavedWebsite(Base):
    """Represents a bookmarked / saved website opportunity belonging to a user (Step 21)."""

    __tablename__ = "saved_websites"
    __table_args__ = (
        UniqueConstraint("user_id", "website_id", name="uq_user_website_saved"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    website_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("websites.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="saved_websites",
    )
    website: Mapped["Website"] = relationship(
        "Website",
        back_populates="saved_records",
    )

    def __repr__(self) -> str:
        return f"<SavedWebsite(id={self.id}, user_id={self.user_id}, website_id={self.website_id}, created_at='{self.created_at}')>"
