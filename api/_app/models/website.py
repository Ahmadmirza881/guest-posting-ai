"""Website database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.search_result import SearchResult
    from app.models.website_analysis import WebsiteAnalysis
    from app.models.guest_post import GuestPostInformation
    from app.models.saved_website import SavedWebsite


class Website(Base):
    """Website entity representing a discovered domain and single-page crawl state."""

    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Step 12: Single-page crawl metadata
    crawl_status: Mapped[Optional[str]] = mapped_column(String(50), default="pending", nullable=True)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(nullable=True)
    final_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    html_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    search_results: Mapped[list["SearchResult"]] = relationship(
        "SearchResult",
        back_populates="website",
        cascade="all, delete-orphan"
    )
    analysis: Mapped[Optional["WebsiteAnalysis"]] = relationship(
        "WebsiteAnalysis",
        back_populates="website",
        uselist=False,
        cascade="all, delete-orphan"
    )
    guest_post_info: Mapped[Optional["GuestPostInformation"]] = relationship(
        "GuestPostInformation",
        back_populates="website",
        uselist=False,
        cascade="all, delete-orphan"
    )
    saved_records: Mapped[list["SavedWebsite"]] = relationship(
        "SavedWebsite",
        back_populates="website",
        cascade="all, delete-orphan"
    )

    @property
    def is_saved(self) -> bool:
        """Default is_saved flag when unauthenticated. Endpoints dynamically calculate this per user."""
        return False

    def __repr__(self) -> str:
        return f"<Website(id={self.id}, domain='{self.domain}', crawl_status='{self.crawl_status}')>"
