"""SearchResult database model representing association between Search and Website."""

from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.search import Search
    from app.models.website import Website


class SearchResult(Base):
    """SearchResult entity connecting a search query with a discovered website."""

    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        ForeignKey("searches.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="discovered", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("search_id", "website_id", name="uq_search_website"),
    )

    # Relationships
    search: Mapped["Search"] = relationship("Search", back_populates="results")
    website: Mapped["Website"] = relationship("Website", back_populates="search_results")

    def __repr__(self) -> str:
        return f"<SearchResult(id={self.id}, search_id={self.search_id}, website_id={self.website_id})>"
