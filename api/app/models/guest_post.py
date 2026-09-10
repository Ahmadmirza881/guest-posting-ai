"""GuestPostInformation database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.website import Website


class GuestPostInformation(Base):
    """GuestPostInformation entity storing guest-posting guidelines, detection, and AI verification details."""

    __tablename__ = "guest_post_information"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )
    accepts_guest_posts: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True
    )
    confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pricing: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    submission_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    submission_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    guidelines_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dofollow: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Step 15: AI Verification Fields
    verification_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="unverified")
    ai_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationships
    website: Mapped["Website"] = relationship("Website", back_populates="guest_post_info")

    def __repr__(self) -> str:
        return (
            f"<GuestPostInformation(id={self.id}, website_id={self.website_id}, "
            f"accepts_guest_posts={self.accepts_guest_posts}, verification_status='{self.verification_status}')>"
        )
