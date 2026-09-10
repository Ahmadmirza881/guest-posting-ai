"""Deterministic Guest Post Detection Module (Step 13).

Provides rule-based heuristic pattern matching, evidence extraction, and confidence calculation
from HTML content crawled in Step 12 to identify guest posting opportunities.

CRITICAL CONSTRAINTS:
- 100% Deterministic (NO LLM, NO AI, NO Gemini, NO OpenAI).
- NO submission extraction (emails/forms belong to Step 14).
- NO website quality scoring (belongs to Step 17).
- NO additional HTTP requests / crawling (Step 13 operates strictly on crawled HTML).
"""

import html as html_lib
import logging
import re
from typing import Optional, List, Tuple
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.website import Website
from app.models.guest_post import GuestPostInformation

logger = logging.getLogger(__name__)

# Strong invitation and submission signals
STRONG_SIGNALS: list[str] = [
    "write for us",
    "write for our blog",
    "write for our website",
    "write for our publication",
    "submit a guest post",
    "submit your guest post",
    "submit guest post",
    "guest post submissions",
    "guest post guidelines",
    "guest author guidelines",
    "contributor guidelines",
    "become a contributor",
    "become a guest contributor",
    "become a guest author",
    "become an author",
    "accepting guest posts",
    "we accept guest posts",
    "guest article guidelines",
    "submit article guidelines",
    "guest post submission",
    "guest blogging guidelines",
    "guest contributors wanted",
    "contribute to our blog",
    "contribute to our website",
]

# Medium positive context signals (require multiple or supporting URL signal for positive classification)
MEDIUM_SIGNALS: list[str] = [
    "guest post",
    "guest posts",
    "guest posting",
    "guest author",
    "guest contributor",
    "submit an article",
    "submit your article",
    "submit article",
    "article submissions",
    "guest blogging",
    "call for writers",
    "call for contributors",
    "pitch a story",
    "pitch an article",
]

# Weak signals (Contextual words that are NOT sufficient on their own)
WEAK_SIGNALS: list[str] = [
    "contributors",
    "writers wanted",
    "contribute",
    "guest blogger",
    "guest article",
    "guest writer",
]

# Explicit negative / closed opportunity regex patterns
NEGATIVE_PATTERNS: list[Tuple[str, str]] = [
    (r"\b(?:we\s+)?(?:do\s+not|don't|no\s+longer)\s+accept(?:ing)?\s+(?:guest|sponsored|unsolicited)\s+(?:posts?|articles?|contributions?)\b", "we do not accept guest posts"),
    (r"\b(?:not|no\s+longer)\s+accepting\s+(?:guest|sponsored|unsolicited)?\s*(?:posts?|articles?|contributions?|submissions?)\b", "not accepting guest posts"),
    (r"\bguest\s+posts?\s+(?:are|is)?\s*(?:currently|temporarily)?\s*(?:closed|suspended|paused|not\s+accepted)\b", "guest posts are currently closed"),
    (r"\bguest\s+post\s+submissions?\s+(?:are|is)?\s*(?:currently|temporarily)?\s*(?:closed|suspended|paused|not\s+accepted)\b", "guest post submissions are closed"),
    (r"\b(?:submissions?|guest\s+contributions?)\s+(?:are|is)?\s*(?:currently|temporarily)?\s*(?:closed|suspended|paused|not\s+accepted)\b", "submissions are closed"),
    (r"\b(?:we\s+)?(?:do\s+not|don't|no\s+longer)\s+accept\s+sponsored\s+posts?\b", "we do not accept sponsored posts"),
]

NEGATIVE_SIGNALS: list[str] = [label for _, label in NEGATIVE_PATTERNS]

# URL Path patterns that indicate possible guest-posting pages
URL_PATH_PATTERNS: list[str] = [
    "write-for-us",
    "guest-post",
    "guest-posts",
    "guest-posting",
    "contribute",
    "contributor-guidelines",
    "submit-article",
    "guest-author",
]


class GuestPostDetectionResult(BaseModel):
    """Structured deterministic guest post detection output."""
    detected: bool
    confidence: int  # 0 to 100
    strong_signals: List[str] = []
    medium_signals: List[str] = []
    weak_signals: List[str] = []
    negative_signals: List[str] = []
    all_positive_signals: List[str] = []
    has_conflicts: bool = False
    evidence_snippets: List[str] = []
    url_signal_matched: Optional[str] = None
    summary_reason: str


def normalize_html_for_detection(raw_html: Optional[str]) -> str:
    """Normalize raw HTML into clean searchable plain text.

    - Strips script, style, and noscript tags and their contents.
    - Replaces all HTML tags with spaces (preserving word boundaries).
    - Unescapes HTML entities.
    - Condenses multiple whitespace into single spaces.
    """
    if not raw_html or not isinstance(raw_html, str):
        return ""

    # Remove script, style, and noscript tags including contents
    cleaned = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)

    # Remove all other HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    # Unescape HTML entities (e.g. &amp; -> &, &quot; -> ")
    cleaned = html_lib.unescape(cleaned)

    # Condense whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def extract_evidence_snippets(text: str, matched_phrases: List[str], max_snippets: int = 5, window: int = 60) -> List[str]:
    """Extract bounded contextual evidence snippets around matched signal phrases."""
    if not text or not matched_phrases:
        return []

    snippets: List[str] = []
    seen_ranges: List[Tuple[int, int]] = []

    for phrase in matched_phrases:
        if len(snippets) >= max_snippets:
            break

        pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            if len(snippets) >= max_snippets:
                break

            start_idx = match.start()
            end_idx = match.end()

            # Check overlap with existing snippets
            if any(s <= start_idx <= e or s <= end_idx <= e for s, e in seen_ranges):
                continue

            snippet_start = max(0, start_idx - window)
            snippet_end = min(len(text), end_idx + window)

            seen_ranges.append((snippet_start, snippet_end))

            prefix = "..." if snippet_start > 0 else ""
            suffix = "..." if snippet_end < len(text) else ""
            raw_snippet = text[snippet_start:snippet_end].strip()

            snippets.append(f"{prefix}{raw_snippet}{suffix}")

    return snippets


def detect_guest_post_opportunity(
    html_content: Optional[str],
    url: Optional[str] = None
) -> GuestPostDetectionResult:
    """Analyze crawled HTML text and URL path deterministically to detect guest posting signals.

    Args:
        html_content: Raw HTML text of the crawled page.
        url: Page URL (used for secondary path signal verification).

    Returns:
        Structured GuestPostDetectionResult containing detected flag, confidence score,
        matched signals, and bounded evidence snippets.
    """
    clean_text = normalize_html_for_detection(html_content)

    if not clean_text:
        return GuestPostDetectionResult(
            detected=False,
            confidence=0,
            summary_reason="Empty or non-text HTML content provided."
        )

    # Check URL path signals (supporting only)
    url_signal_matched: Optional[str] = None
    if url:
        try:
            parsed_path = urlsplit(url).path.lower()
            for pattern in URL_PATH_PATTERNS:
                if pattern in parsed_path:
                    url_signal_matched = pattern
                    break
        except Exception:
            pass

    # 1. Match Negative / Closed Signals and track their character spans & exact text
    matched_negative: List[str] = []
    matched_negative_raw_texts: List[str] = []
    negative_spans: List[Tuple[int, int]] = []
    for pattern_regex, label in NEGATIVE_PATTERNS:
        for match in re.finditer(pattern_regex, clean_text, re.IGNORECASE):
            if label not in matched_negative:
                matched_negative.append(label)
            matched_negative_raw_texts.append(match.group(0))
            negative_spans.append((match.start(), match.end()))

    def is_inside_negative_span(start: int, end: int) -> bool:
        """Check if a match span is entirely inside an already matched negative phrase."""
        return any(neg_s <= start and end <= neg_e for neg_s, neg_e in negative_spans)

    # 2. Match Strong Signals (ignoring any match that is just a substring of a negative signal)
    matched_strong: List[str] = []
    matched_strong_raw_texts: List[str] = []
    for strong_phrase in STRONG_SIGNALS:
        pattern = re.compile(r"\b" + re.escape(strong_phrase) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            if not is_inside_negative_span(match.start(), match.end()):
                if strong_phrase not in matched_strong:
                    matched_strong.append(strong_phrase)
                matched_strong_raw_texts.append(match.group(0))

    # 3. Match Medium Signals (ignoring matches inside negative spans or strong signals)
    matched_medium: List[str] = []
    matched_medium_raw_texts: List[str] = []
    for med_phrase in MEDIUM_SIGNALS:
        if any(med_phrase in s for s in matched_strong):
            continue
        pattern = re.compile(r"\b" + re.escape(med_phrase) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            if not is_inside_negative_span(match.start(), match.end()):
                if med_phrase not in matched_medium:
                    matched_medium.append(med_phrase)
                matched_medium_raw_texts.append(match.group(0))

    # 4. Match Weak Signals
    matched_weak: List[str] = []
    matched_weak_raw_texts: List[str] = []
    for weak_phrase in WEAK_SIGNALS:
        if any(weak_phrase in s for s in matched_strong + matched_medium):
            continue
        pattern = re.compile(r"\b" + re.escape(weak_phrase) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(clean_text):
            if not is_inside_negative_span(match.start(), match.end()):
                if weak_phrase not in matched_weak:
                    matched_weak.append(weak_phrase)
                matched_weak_raw_texts.append(match.group(0))

    all_positive = matched_strong + matched_medium

    # Extract contextual evidence using exact matched texts
    evidence_phrases = matched_negative_raw_texts + matched_strong_raw_texts + matched_medium_raw_texts
    if not evidence_phrases and matched_weak_raw_texts:
        evidence_phrases = matched_weak_raw_texts

    evidence_snippets = extract_evidence_snippets(clean_text, evidence_phrases, max_snippets=5)

    # Deterministic Evaluation & Confidence Scoring
    has_conflicts = bool(matched_negative and (matched_strong or matched_medium))

    # Case 1: Negative / Closed Signals present
    if matched_negative:
        if has_conflicts:
            return GuestPostDetectionResult(
                detected=False,
                confidence=20,
                strong_signals=matched_strong,
                medium_signals=matched_medium,
                weak_signals=matched_weak,
                negative_signals=matched_negative,
                all_positive_signals=all_positive,
                has_conflicts=True,
                evidence_snippets=evidence_snippets,
                url_signal_matched=url_signal_matched,
                summary_reason="Conflicting signals detected: Page contains guest post mentions but explicitly indicates submissions are closed or not accepted."
            )
        else:
            return GuestPostDetectionResult(
                detected=False,
                confidence=0,
                strong_signals=[],
                medium_signals=[],
                weak_signals=[],
                negative_signals=matched_negative,
                all_positive_signals=[],
                has_conflicts=False,
                evidence_snippets=evidence_snippets,
                url_signal_matched=url_signal_matched,
                summary_reason="Page explicitly indicates guest post submissions are not accepted or closed."
            )

    # Case 2: Strong Positive Signals (Very high / high confidence)
    if len(matched_strong) >= 2:
        return GuestPostDetectionResult(
            detected=True,
            confidence=95,
            strong_signals=matched_strong,
            medium_signals=matched_medium,
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=all_positive,
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason=f"Multiple strong contributor signals found: {', '.join(matched_strong[:3])}."
        )

    if len(matched_strong) == 1:
        conf = 90 if (url_signal_matched or matched_medium) else 85
        return GuestPostDetectionResult(
            detected=True,
            confidence=conf,
            strong_signals=matched_strong,
            medium_signals=matched_medium,
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=all_positive,
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason=f"Strong contributor signal detected: '{matched_strong[0]}'."
        )

    # Case 3: Multiple Medium Signals or 1 Medium + URL Path Match
    if len(matched_medium) >= 2:
        conf = 80 if url_signal_matched else 75
        return GuestPostDetectionResult(
            detected=True,
            confidence=conf,
            strong_signals=[],
            medium_signals=matched_medium,
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=all_positive,
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason=f"Multiple medium contributor signals found: {', '.join(matched_medium[:3])}."
        )

    if len(matched_medium) == 1 and url_signal_matched:
        return GuestPostDetectionResult(
            detected=True,
            confidence=70,
            strong_signals=[],
            medium_signals=matched_medium,
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=all_positive,
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason=f"Medium signal '{matched_medium[0]}' supported by matching URL path '{url_signal_matched}'."
        )

    # Case 4: Single Medium Signal without Supporting Context (False Positive Protection)
    if len(matched_medium) == 1:
        return GuestPostDetectionResult(
            detected=False,
            confidence=45,
            strong_signals=[],
            medium_signals=matched_medium,
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=all_positive,
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason=f"Single isolated mention of '{matched_medium[0]}' without explicit invitation guidelines (insufficient for positive guest post confirmation)."
        )

    # Case 5: Weak Signals only (False-positive protection: NOT classified as positive)
    if matched_weak:
        conf = 35 if url_signal_matched else 25
        return GuestPostDetectionResult(
            detected=False,
            confidence=conf,
            strong_signals=[],
            medium_signals=[],
            weak_signals=matched_weak,
            negative_signals=[],
            all_positive_signals=[],
            has_conflicts=False,
            evidence_snippets=evidence_snippets,
            url_signal_matched=url_signal_matched,
            summary_reason="Only weak contextual terms found (insufficient for positive guest post classification)."
        )

    # Case 6: URL-only signal (No HTML body signals)
    if url_signal_matched:
        return GuestPostDetectionResult(
            detected=False,
            confidence=20,
            strong_signals=[],
            medium_signals=[],
            weak_signals=[],
            negative_signals=[],
            all_positive_signals=[],
            has_conflicts=False,
            evidence_snippets=[],
            url_signal_matched=url_signal_matched,
            summary_reason="URL path matches guest-posting keywords, but page HTML contains no corresponding contributor signals."
        )

    # Case 7: No signals found
    return GuestPostDetectionResult(
        detected=False,
        confidence=0,
        strong_signals=[],
        medium_signals=[],
        weak_signals=[],
        negative_signals=[],
        all_positive_signals=[],
        has_conflicts=False,
        evidence_snippets=[],
        url_signal_matched=None,
        summary_reason="No guest-posting or contributor signals detected on page."
    )


def detect_guest_post_for_website(
    db: Session,
    website_id: int
) -> Tuple[Optional[Website], GuestPostDetectionResult]:
    """Execute guest post detection for a crawled website record and upsert GuestPostInformation.

    Args:
        db: SQLAlchemy database session.
        website_id: ID of the Website record.

    Returns:
        tuple of (Website entity, GuestPostDetectionResult)
    """
    website = db.get(Website, website_id)
    if not website:
        return None, GuestPostDetectionResult(
            detected=False,
            confidence=0,
            summary_reason=f"Website #{website_id} not found."
        )

    # Run detection on crawled HTML content
    result = detect_guest_post_opportunity(
        html_content=website.html_content,
        url=website.final_url or website.url
    )

    # Upsert GuestPostInformation record
    stmt = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
    gp_info = db.scalars(stmt).first()

    evidence_text = " | ".join(result.evidence_snippets) if result.evidence_snippets else None
    guidelines_url = (website.final_url or website.url) if result.detected else None

    if not gp_info:
        gp_info = GuestPostInformation(
            website_id=website.id,
            accepts_guest_posts=result.detected,
            confidence=result.confidence,
            guidelines_url=guidelines_url,
            evidence=evidence_text,
            updated_at=datetime.now(timezone.utc)
        )
        db.add(gp_info)
    else:
        gp_info.accepts_guest_posts = result.detected
        gp_info.confidence = result.confidence
        if guidelines_url:
            gp_info.guidelines_url = guidelines_url
        if evidence_text:
            gp_info.evidence = evidence_text
        gp_info.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(website)

    return website, result
