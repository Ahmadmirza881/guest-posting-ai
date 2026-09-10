"""Search database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.search_result import SearchResult


class Search(Base):
    """Search entity representing a user's niche/keyword search request."""

    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    requested_website_count: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="searches")
    results: Mapped[list["SearchResult"]] = relationship(
        "SearchResult",
        back_populates="search",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Search(id={self.id}, keyword='{self.keyword}', status='{self.status}')>"
