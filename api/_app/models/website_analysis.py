"""WebsiteAnalysis database model."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.website import Website


class WebsiteAnalysis(Base):
    """WebsiteAnalysis entity storing semantic analysis, niche topics, trust signals, and final quality scoring."""

    __tablename__ = "website_analyses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    website_id: Mapped[int] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True
    )

    # Step 16: Semantic Niche & Topic Analysis
    primary_niche: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list of topics
    niche_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Step 16: Niche Relevance
    niche_relevance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    relevance_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    relevance_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Step 16: Content Quality
    content_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_quality_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_quality_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Step 16: Trust & Editorial Signals
    website_trust: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    trust_signals: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list
    editorial_standards: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list

    # Step 16: Strengths, Weaknesses, Evidence, Warnings
    strengths: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list
    weaknesses: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list
    analysis_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list
    warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded list

    # Step 16: Analysis Metadata
    analysis_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    analysis_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="completed")

    # Step 17: Final Deterministic Scoring Fields
    quality_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    score_breakdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON-encoded detailed breakdown
    scoring_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="pending")
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Legacy fields (preserved)
    guest_post_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    website_activity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    website: Mapped["Website"] = relationship("Website", back_populates="analysis")

    def __repr__(self) -> str:
        return (
            f"<WebsiteAnalysis(id={self.id}, website_id={self.website_id}, "
            f"quality_score={self.quality_score}, status='{self.scoring_status}')>"
        )
