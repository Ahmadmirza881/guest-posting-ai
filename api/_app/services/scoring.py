"""Deterministic Website Scoring Engine (Step 17).

Calculates a final quality score (0–100) combining deterministic signals and AI analysis
from Steps 13–16 using an explainable, bounded, multi-factor scoring formula.

CRITICAL CONSTRAINTS:
- 100% Deterministic (NO Gemini API calls during scoring).
- Bounded strictly between 0 and 100.
- Weighted formula totaling exactly 100 points:
    1. Guest Post Acceptance: 25 pts
    2. Niche Relevance:       25 pts
    3. Content Quality:       20 pts
    4. Trust Signals:         15 pts
    5. Editorial Standards:   10 pts
    6. AI Verification:        5 pts
- Handles missing or incomplete data gracefully without crashing.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.website import Website
from app.models.guest_post import GuestPostInformation
from app.models.website_analysis import WebsiteAnalysis

logger = logging.getLogger(__name__)

# Configurable scoring category weights (Must sum to exactly 100)
SCORING_WEIGHTS: Dict[str, int] = {
    "guest_post_acceptance": 25,
    "niche_relevance": 25,
    "content_quality": 20,
    "trust_signals": 15,
    "editorial_standards": 10,
    "ai_verification": 5,
}

assert sum(SCORING_WEIGHTS.values()) == 100, "Scoring weights must total exactly 100 points."


class CategoryScoreDetail(BaseModel):
    """Detailed score breakdown for a single scoring dimension."""
    points: float
    max_points: int
    reason: str


class WebsiteScoringResult(BaseModel):
    """Structured result of the deterministic website scoring engine."""
    website_id: int
    quality_score: int
    breakdown: Dict[str, CategoryScoreDetail]
    scoring_status: str = "scored"
    scored_at: datetime


def calculate_guest_post_score(
    accepts_guest_posts: Optional[bool],
    confidence: Optional[int],
    verification_status: Optional[str]
) -> Tuple[float, str]:
    """Calculate score for guest post acceptance (Max 25 pts)."""
    max_pts = SCORING_WEIGHTS["guest_post_acceptance"]

    # Explicit rejection
    if verification_status == "rejected" or accepts_guest_posts is False:
        return 0.0, "Guest posts are explicitly closed, not accepted, or rejected by AI verification."

    # Verified positive acceptance
    if verification_status == "verified" or accepts_guest_posts is True:
        conf = max(0, min(100, confidence if confidence is not None else 80))
        pts = round(conf / 100.0 * max_pts, 1)
        return pts, f"Guest post acceptance verified with {conf}% confidence."

    # Uncertain case
    if verification_status == "uncertain":
        conf = max(0, min(100, confidence if confidence is not None else 40))
        pts = round((conf / 100.0 * max_pts) * 0.5, 1)
        return pts, f"Guest post opportunity is uncertain ({conf}% confidence)."

    # Missing / unverified
    return 0.0, "No guest post acceptance data available."


def calculate_relevance_score(
    relevance_score: Optional[int],
    reason: Optional[str] = None
) -> Tuple[float, str]:
    """Calculate score for niche relevance against search keyword (Max 25 pts)."""
    max_pts = SCORING_WEIGHTS["niche_relevance"]

    if relevance_score is None:
        return 0.0, "Niche relevance has not been analyzed."

    score = max(0, min(100, int(relevance_score)))
    pts = round(score / 100.0 * max_pts, 1)
    r_str = reason or f"Niche relevance evaluated at {score}/100."
    return pts, r_str


def calculate_content_quality_score(
    content_quality_score: Optional[int],
    reason: Optional[str] = None
) -> Tuple[float, str]:
    """Calculate score for published content quality and depth (Max 20 pts)."""
    max_pts = SCORING_WEIGHTS["content_quality"]

    if content_quality_score is None:
        return 0.0, "Content quality has not been analyzed."

    score = max(0, min(100, int(content_quality_score)))
    pts = round(score / 100.0 * max_pts, 1)
    r_str = reason or f"Content quality evaluated at {score}/100."
    return pts, r_str


def calculate_trust_score(trust_signals: Optional[List[str]]) -> Tuple[float, str]:
    """Calculate score for observable authenticity and trust signals (Max 15 pts)."""
    max_pts = SCORING_WEIGHTS["trust_signals"]

    if not trust_signals:
        return 0.0, "No observable trust signals recorded."

    # Award 5.0 points per distinct recognized trust signal, capped at 15.0
    count = len(trust_signals)
    pts = min(float(max_pts), round(count * 5.0, 1))
    return pts, f"{count} verified trust signal(s) present on the website."


def calculate_editorial_score(editorial_standards: Optional[List[str]]) -> Tuple[float, str]:
    """Calculate score for explicit contributor and editorial standards (Max 10 pts)."""
    max_pts = SCORING_WEIGHTS["editorial_standards"]

    if not editorial_standards:
        return 0.0, "No explicit editorial standards or contributor guidelines found."

    # Award 5.0 points per distinct standard, capped at 10.0
    count = len(editorial_standards)
    pts = min(float(max_pts), round(count * 5.0, 1))
    return pts, f"{count} editorial standard rule(s) and guidelines detected."


def calculate_ai_verification_score(
    verification_status: Optional[str],
    ai_confidence: Optional[int]
) -> Tuple[float, str]:
    """Calculate score for AI verification confidence (Max 5 pts)."""
    max_pts = SCORING_WEIGHTS["ai_verification"]

    if verification_status == "rejected" or verification_status == "unverified" or not verification_status:
        return 0.0, f"AI verification status is '{verification_status or 'unverified'}'."

    if verification_status == "verified":
        conf = max(0, min(100, ai_confidence if ai_confidence is not None else 80))
        pts = round(conf / 100.0 * max_pts, 1)
        return pts, f"AI semantic verification strongly confirmed ({conf}% confidence)."

    if verification_status == "uncertain":
        conf = max(0, min(100, ai_confidence if ai_confidence is not None else 40))
        pts = round((conf / 100.0 * max_pts) * 0.5, 1)
        return pts, f"AI verification returned uncertain status ({conf}% confidence)."

    return 0.0, "AI verification pending."


def calculate_website_score(
    website_id: int,
    gp_info: Optional[GuestPostInformation] = None,
    analysis: Optional[WebsiteAnalysis] = None
) -> WebsiteScoringResult:
    """Run deterministic multi-factor scoring formula across all dimensions.

    Args:
        website_id: Target Website ID.
        gp_info: Optional GuestPostInformation record from Steps 13-15.
        analysis: Optional WebsiteAnalysis record from Step 16.

    Returns:
        Structured WebsiteScoringResult with integer quality_score (0-100) and breakdown.
    """
    # 1. Guest Post Acceptance (25 pts)
    gp_accepts = gp_info.accepts_guest_posts if gp_info else None
    gp_conf = gp_info.confidence if gp_info else None
    ver_status = gp_info.verification_status if gp_info else None
    gp_pts, gp_reason = calculate_guest_post_score(gp_accepts, gp_conf, ver_status)

    # 2. Niche Relevance (25 pts)
    rel_score = analysis.relevance_score if analysis else None
    rel_reason_text = analysis.relevance_reason if analysis else None
    rel_pts, rel_reason = calculate_relevance_score(rel_score, rel_reason_text)

    # 3. Content Quality (20 pts)
    cq_score = analysis.content_quality_score if analysis else None
    cq_reason_text = analysis.content_quality_reason if analysis else None
    cq_pts, cq_reason = calculate_content_quality_score(cq_score, cq_reason_text)

    # 4. Trust Signals (15 pts)
    trust_list: List[str] = []
    if analysis and analysis.trust_signals:
        try:
            parsed = json.loads(analysis.trust_signals)
            if isinstance(parsed, list):
                trust_list = [str(x) for x in parsed]
        except Exception:
            pass
    tr_pts, tr_reason = calculate_trust_score(trust_list)

    # 5. Editorial Standards (10 pts)
    ed_list: List[str] = []
    if analysis and analysis.editorial_standards:
        try:
            parsed = json.loads(analysis.editorial_standards)
            if isinstance(parsed, list):
                ed_list = [str(x) for x in parsed]
        except Exception:
            pass
    ed_pts, ed_reason = calculate_editorial_score(ed_list)

    # 6. AI Verification (5 pts)
    ai_conf = gp_info.ai_confidence if gp_info else None
    ai_pts, ai_reason = calculate_ai_verification_score(ver_status, ai_conf)

    # Sum and strictly bound final score to [0, 100] integer
    raw_total = gp_pts + rel_pts + cq_pts + tr_pts + ed_pts + ai_pts
    final_score = max(0, min(100, round(raw_total)))

    breakdown = {
        "guest_post_acceptance": CategoryScoreDetail(
            points=gp_pts,
            max_points=SCORING_WEIGHTS["guest_post_acceptance"],
            reason=gp_reason
        ),
        "niche_relevance": CategoryScoreDetail(
            points=rel_pts,
            max_points=SCORING_WEIGHTS["niche_relevance"],
            reason=rel_reason
        ),
        "content_quality": CategoryScoreDetail(
            points=cq_pts,
            max_points=SCORING_WEIGHTS["content_quality"],
            reason=cq_reason
        ),
        "trust_signals": CategoryScoreDetail(
            points=tr_pts,
            max_points=SCORING_WEIGHTS["trust_signals"],
            reason=tr_reason
        ),
        "editorial_standards": CategoryScoreDetail(
            points=ed_pts,
            max_points=SCORING_WEIGHTS["editorial_standards"],
            reason=ed_reason
        ),
        "ai_verification": CategoryScoreDetail(
            points=ai_pts,
            max_points=SCORING_WEIGHTS["ai_verification"],
            reason=ai_reason
        ),
    }

    return WebsiteScoringResult(
        website_id=website_id,
        quality_score=final_score,
        breakdown=breakdown,
        scoring_status="scored",
        scored_at=datetime.now(timezone.utc)
    )


def score_website_record(
    db: Session,
    website_id: int
) -> Tuple[Optional[Website], WebsiteScoringResult]:
    """Calculate and persist deterministic quality score for a website record.

    Args:
        db: SQLAlchemy database session.
        website_id: Target Website ID.

    Returns:
        tuple of (Website entity, WebsiteScoringResult)
    """
    website = db.get(Website, website_id)
    if not website:
        empty_res = calculate_website_score(website_id=website_id)
        empty_res.scoring_status = "failed"
        return None, empty_res

    gp_stmt = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
    gp_info = db.scalars(gp_stmt).first()

    wa_stmt = select(WebsiteAnalysis).where(WebsiteAnalysis.website_id == website.id)
    analysis = db.scalars(wa_stmt).first()

    scoring_res = calculate_website_score(
        website_id=website.id,
        gp_info=gp_info,
        analysis=analysis
    )

    now_utc = datetime.now(timezone.utc)
    breakdown_json = json.dumps({k: v.model_dump() for k, v in scoring_res.breakdown.items()})

    if not analysis:
        analysis = WebsiteAnalysis(
            website_id=website.id,
            quality_score=scoring_res.quality_score,
            score_breakdown=breakdown_json,
            scoring_status="scored",
            scored_at=now_utc,
            analyzed_at=now_utc
        )
        db.add(analysis)
    else:
        analysis.quality_score = scoring_res.quality_score
        analysis.score_breakdown = breakdown_json
        analysis.scoring_status = "scored"
        analysis.scored_at = now_utc

    db.commit()
    db.refresh(website)

    return website, scoring_res
