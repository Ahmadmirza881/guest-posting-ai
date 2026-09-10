"""Deterministic Submission Information Extraction Module (Step 14).

Extracts submission channels (emails, submission form URLs, Google Forms, Typeform),
guidelines URLs, submission methods, and explicit pricing/fee statements from crawled HTML content.

CRITICAL CONSTRAINTS:
- 100% Deterministic (NO LLM, NO AI, NO Gemini, NO OpenAI).
- NO extra network requests or web crawling (operates strictly on crawled HTML).
- Avoid false positives (differentiate generic contact info from guest-post submission channels).
- Bounded evidence extraction.
"""

import html as html_lib
import logging
import re
from typing import Optional, List, Tuple
from urllib.parse import urljoin, urlsplit, unquote
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.website import Website
from app.models.guest_post import GuestPostInformation
from app.services.guest_post_detector import normalize_html_for_detection

logger = logging.getLogger(__name__)

# Valid email regex pattern
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE
)

# Non-editorial or administrative email prefixes to filter out
GENERIC_EMAIL_PREFIXES = {
    "privacy", "abuse", "legal", "dmca", "gdpr", "security",
    "billing", "sales", "jobs", "careers", "press", "media", "investors",
    "noreply", "no-reply", "donotreply", "webmaster", "postmaster",
    "unsubscribe", "help", "compliance"
}

# Editorial / submission preferred email prefixes
PREFERRED_EMAIL_PREFIXES = {
    "submissions", "submission", "submit", "guestpost", "guestposts",
    "guest", "write", "contribute", "editor", "editorial", "articles",
    "pitches", "pitch", "outreach", "content"
}

# Submission context keywords in surrounding text
SUBMISSION_CONTEXT_KEYWORDS = [
    "guest post", "write for us", "submit", "submission", "contributor",
    "contribute", "article", "pitch", "guidelines", "editorial",
    "send your draft", "email us at", "send article", "send post",
    "email your pitch", "submit your draft"
]

# External form provider domains
GOOGLE_FORM_DOMAINS = ["docs.google.com/forms", "forms.gle"]
TYPEFORM_DOMAINS = ["typeform.com"]
OTHER_FORM_DOMAINS = ["airtable.com/shr", "tally.so/r/", "jotform.com", "formkeep.com"]

# Keywords indicating submission form URLs or links
SUBMISSION_URL_KEYWORDS = [
    "submit-article", "submit-post", "submit-guest-post", "submit-pitch",
    "guest-post-submission", "submission-form", "contribute-form",
    "contributor-application", "guest-author-application", "pitch-article",
    "article-submission", "contribute", "submissions"
]

# Keywords indicating guidelines URLs or links
GUIDELINES_URL_KEYWORDS = [
    "guest-post-guidelines", "contributor-guidelines", "submission-guidelines",
    "editorial-guidelines", "write-for-us-guidelines", "guidelines",
    "guest-posting-rules", "writer-guidelines"
]

# Anchor text patterns for submission links
SUBMISSION_ANCHOR_PATTERNS = [
    r"\bsubmit\s+(?:your\s+)?(?:guest\s+post|article|pitch|story)\b",
    r"\bsubmission\s+form\b",
    r"\bfill\s+out\s+(?:our\s+)?(?:submission\s+)?form\b",
    r"\bcontributor\s+application\b",
    r"\bapply\s+to\s+(?:write|contribute)\b",
    r"\bsubmit\s+here\b",
]

# Anchor text patterns for guidelines links
GUIDELINES_ANCHOR_PATTERNS = [
    r"\bguest\s+post\s+guidelines\b",
    r"\bcontributor\s+guidelines\b",
    r"\bsubmission\s+guidelines\b",
    r"\beditorial\s+guidelines\b",
    r"\bwrite\s+for\s+us\b",
    r"\bguest\s+posting\s+guidelines\b",
    r"\bwriting\s+guidelines\b",
]

# Pricing / Fee patterns
FREE_PATTERNS = [
    r"\b(?:free\s+guest\s+posts?|submit\s+(?:for\s+)?free|no\s+(?:publishing\s+|submission\s+|editorial\s+)?fees?|no\s+charge|we\s+do\s+not\s+charge|completely\s+free\s+(?:to\s+publish|submission))\b",
]

PAID_PATTERNS = [
    r"\b(?:paid\s+guest\s+posts?|publishing\s+fees?|admin\s+fees?|editorial\s+fees?|sponsored\s+posts?|sponsored\s+articles?|paid\s+contributions?|insertion\s+fees?)\b",
]

PRICE_AMOUNT_PATTERN = re.compile(
    r"(?:[\$\€\£]\s*\d+(?:[\.,]\d{2})?(?:\s*(?:per\s+(?:post|article)|USD|EUR|GBP))?|\b\d+\s*(?:USD|EUR|GBP|dollars?|euros?)(?:\s+per\s+(?:post|article))?\b)",
    re.IGNORECASE
)


class ExtractedLink(BaseModel):
    """Represents an extracted HTML anchor or form action."""
    url: str
    anchor_text: str
    is_external_form: bool = False
    form_type: Optional[str] = None


class SubmissionExtractionResult(BaseModel):
    """Structured deterministic submission information extraction result."""
    submission_methods: List[str] = []
    primary_submission_method: Optional[str] = None
    submission_emails: List[str] = []
    primary_email: Optional[str] = None
    submission_urls: List[str] = []
    primary_submission_url: Optional[str] = None
    guidelines_urls: List[str] = []
    primary_guidelines_url: Optional[str] = None
    is_paid: Optional[bool] = None
    pricing_model: str = "unknown"  # "free", "paid", "unknown"
    price_amount: Optional[str] = None
    evidence_snippets: List[str] = []
    has_submission_channel: bool = False


def extract_html_links_and_forms(raw_html: str, base_url: Optional[str] = None) -> List[ExtractedLink]:
    """Parse HTML anchors and forms to extract URLs and anchor texts."""
    if not raw_html or not isinstance(raw_html, str):
        return []

    links: List[ExtractedLink] = []
    seen_urls: set[str] = set()

    # 1. Parse Anchor Tags <a href="...">text</a>
    anchor_pattern = re.compile(
        r'<a\s+[^>]*?href=["\'](.*?)["\'][^>]*?>(.*?)</a>',
        re.IGNORECASE | re.DOTALL
    )

    for match in anchor_pattern.finditer(raw_html):
        raw_href = match.group(1).strip()
        raw_text = match.group(2)

        # Clean anchor text
        clean_text = re.sub(r"<[^>]+>", " ", raw_text)
        clean_text = html_lib.unescape(clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        # Skip jump links, javascript, tel
        if not raw_href or raw_href.startswith("#") or raw_href.lower().startswith(("javascript:", "tel:")):
            continue

        # Resolve absolute URL
        absolute_url = urljoin(base_url or "", raw_href) if base_url else raw_href

        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)

        # Check external form providers
        is_ext = False
        form_type = None
        lower_url = absolute_url.lower()

        if any(d in lower_url for d in GOOGLE_FORM_DOMAINS):
            is_ext = True
            form_type = "google_form"
        elif any(d in lower_url for d in TYPEFORM_DOMAINS):
            is_ext = True
            form_type = "typeform"
        elif any(d in lower_url for d in OTHER_FORM_DOMAINS):
            is_ext = True
            form_type = "form"

        links.append(ExtractedLink(
            url=absolute_url,
            anchor_text=clean_text,
            is_external_form=is_ext,
            form_type=form_type
        ))

    # 2. Parse Form Actions <form action="...">
    form_pattern = re.compile(
        r'<form\s+[^>]*?action=["\'](.*?)["\'][^>]*?>',
        re.IGNORECASE | re.DOTALL
    )
    for match in form_pattern.finditer(raw_html):
        raw_action = match.group(1).strip()
        if raw_action and not raw_action.startswith("#"):
            abs_action = urljoin(base_url or "", raw_action) if base_url else raw_action
            if abs_action not in seen_urls:
                seen_urls.add(abs_action)
                links.append(ExtractedLink(
                    url=abs_action,
                    anchor_text="Embedded HTML Form",
                    is_external_form=False,
                    form_type="form"
                ))

    return links


def extract_submission_emails(raw_html: str, clean_text: str) -> Tuple[List[str], List[str]]:
    """Extract and validate submission/editorial email addresses from HTML and context."""
    raw_emails: List[str] = []
    evidence: List[str] = []
    seen: set[str] = set()

    # 1. Look for mailto: links in HTML
    mailto_pattern = re.compile(r'href=["\']mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', re.IGNORECASE)
    for match in mailto_pattern.finditer(raw_html):
        email = unquote(match.group(1)).strip().lower()
        if email not in seen:
            seen.add(email)
            raw_emails.append(email)

    # 2. Look for plain text emails
    for match in EMAIL_REGEX.finditer(clean_text):
        email = match.group(0).strip().lower()
        # Avoid non-email asset extensions
        if any(email.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".js", ".css"]):
            continue

        if email not in seen:
            seen.add(email)
            raw_emails.append(email)

    # Tiered ranking and filtering
    tier1_preferred: List[Tuple[str, str]] = []
    tier2_contextual: List[Tuple[str, str]] = []
    tier3_general: List[Tuple[str, str]] = []

    for email in raw_emails:
        prefix = email.split("@")[0].lower()
        if prefix in GENERIC_EMAIL_PREFIXES:
            # Completely filter out blacklisted administrative emails
            continue

        # Extract context window
        idx = clean_text.lower().find(email)
        context_window = ""
        if idx != -1:
            start_pos = max(0, idx - 60)
            end_pos = min(len(clean_text), idx + len(email) + 60)
            context_window = clean_text[start_pos:end_pos].strip()

        has_sub_kw = any(kw in context_window.lower() for kw in SUBMISSION_CONTEXT_KEYWORDS)
        evidence_str = f"...{context_window}..." if context_window else email

        if prefix in PREFERRED_EMAIL_PREFIXES:
            tier1_preferred.append((email, evidence_str))
        elif has_sub_kw:
            tier2_contextual.append((email, evidence_str))
        else:
            tier3_general.append((email, evidence_str))

    ranked_emails: List[str] = []
    for email_list in [tier1_preferred, tier2_contextual, tier3_general]:
        for email, ev_str in email_list:
            if email not in ranked_emails:
                ranked_emails.append(email)
                if ev_str and len(evidence) < 5 and ev_str not in evidence:
                    evidence.append(ev_str)

    return ranked_emails, evidence


def extract_submission_information(
    html: Optional[str],
    base_url: Optional[str] = None
) -> SubmissionExtractionResult:
    """Deterministically inspect crawled HTML to extract submission methods, channels, and pricing.

    Args:
        html: Raw HTML content from crawler.
        base_url: Current page URL for resolving relative links.

    Returns:
        Structured SubmissionExtractionResult with extracted emails, form URLs, guidelines, and pricing.
    """
    if not html or not isinstance(html, str):
        return SubmissionExtractionResult(
            submission_methods=["unknown"],
            has_submission_channel=False
        )

    clean_text = normalize_html_for_detection(html)
    extracted_links = extract_html_links_and_forms(html, base_url=base_url)

    evidence_snippets: List[str] = []
    submission_methods: List[str] = []

    # 1. Extract Emails
    emails, email_evidence = extract_submission_emails(html, clean_text)
    evidence_snippets.extend(email_evidence)

    if emails:
        if "email" not in submission_methods:
            submission_methods.append("email")

    # 2. Extract Submission URLs & Form Links
    submission_urls: List[str] = []
    guidelines_urls: List[str] = []

    for link in extracted_links:
        url_lower = link.url.lower()
        anchor_lower = link.anchor_text.lower()

        # External Form Providers
        if link.is_external_form:
            if link.url not in submission_urls:
                submission_urls.append(link.url)
            if link.form_type and link.form_type not in submission_methods:
                submission_methods.append(link.form_type)
            if link.anchor_text and len(evidence_snippets) < 5:
                evidence_snippets.append(f"Submission form: {link.anchor_text} ({link.url})")
            continue

        # Check Submission Form / Page Link
        is_sub_url = any(kw in url_lower for kw in SUBMISSION_URL_KEYWORDS)
        is_sub_anchor = any(re.search(pat, anchor_lower) for pat in SUBMISSION_ANCHOR_PATTERNS)

        if (is_sub_url or is_sub_anchor) and not url_lower.startswith("mailto:"):
            if link.url not in submission_urls:
                submission_urls.append(link.url)
            if "form" not in submission_methods and not any(m in submission_methods for m in ["google_form", "typeform"]):
                submission_methods.append("form")
            if link.anchor_text and len(evidence_snippets) < 5:
                evidence_snippets.append(f"Submission link: '{link.anchor_text}' -> {link.url}")

        # Check Guidelines URL
        is_guide_url = any(kw in url_lower for kw in GUIDELINES_URL_KEYWORDS)
        is_guide_anchor = any(re.search(pat, anchor_lower) for pat in GUIDELINES_ANCHOR_PATTERNS)

        if is_guide_url or is_guide_anchor:
            if link.url not in guidelines_urls and not url_lower.startswith("mailto:"):
                guidelines_urls.append(link.url)
                if link.anchor_text and len(evidence_snippets) < 5:
                    evidence_snippets.append(f"Guidelines link: '{link.anchor_text}' -> {link.url}")

    # Fallback to current URL for guidelines if current page is the guidelines page
    if not guidelines_urls and base_url:
        parsed_path = urlsplit(base_url).path.lower()
        if any(kw in parsed_path for kw in GUIDELINES_URL_KEYWORDS + ["write-for-us"]):
            guidelines_urls.append(base_url)

    # 3. Detect Paid / Free & Extract Explicit Price
    pricing_model = "unknown"
    is_paid: Optional[bool] = None
    price_amount: Optional[str] = None

    # Track Free spans
    free_spans: List[Tuple[int, int]] = []
    for pat in FREE_PATTERNS:
        for m in re.finditer(pat, clean_text, re.IGNORECASE):
            free_spans.append((m.start(), m.end()))

    def is_inside_free_span(start: int, end: int) -> bool:
        return any(f_s <= start and end <= f_e for f_s, f_e in free_spans)

    # Track Paid matches (excluding matches inside free phrases like "no publishing fee")
    paid_matches: List[Tuple[str, int, int]] = []
    for pat in PAID_PATTERNS:
        for m in re.finditer(pat, clean_text, re.IGNORECASE):
            if not is_inside_free_span(m.start(), m.end()):
                paid_matches.append((m.group(0), m.start(), m.end()))

    has_free = len(free_spans) > 0
    has_paid = len(paid_matches) > 0

    if has_free and not has_paid:
        pricing_model = "free"
        is_paid = False
        # Extract free evidence
        for f_start, f_end in free_spans:
            if len(evidence_snippets) < 5:
                start_pos = max(0, f_start - 30)
                end_pos = min(len(clean_text), f_end + 30)
                evidence_snippets.append(f"...{clean_text[start_pos:end_pos].strip()}...")
                break

    elif has_paid:
        pricing_model = "paid"
        is_paid = True
        # Extract paid evidence
        for p_str, p_start, p_end in paid_matches:
            if len(evidence_snippets) < 5:
                start_pos = max(0, p_start - 30)
                end_pos = min(len(clean_text), p_end + 30)
                evidence_snippets.append(f"...{clean_text[start_pos:end_pos].strip()}...")
                break

    # Look for explicit currency / price amount in clean text
    for price_match in PRICE_AMOUNT_PATTERN.finditer(clean_text):
        price_str = price_match.group(0).strip()
        p_start = max(0, price_match.start() - 60)
        p_end = min(len(clean_text), price_match.end() + 60)
        surrounding = clean_text[p_start:p_end].lower()

        if any(kw in surrounding for kw in ["post", "article", "guest", "fee", "publish", "sponsored", "submission", "charge", "insertion"]):
            price_amount = price_str
            pricing_model = "paid"
            is_paid = True
            if len(evidence_snippets) < 5:
                evidence_snippets.append(f"Price stated: {price_str} in context: '...{clean_text[p_start:p_end].strip()}...'")
            break

    # Set default unknown submission method if none detected
    if not submission_methods:
        submission_methods = ["unknown"]

    has_channel = bool(emails or submission_urls or any(m in submission_methods for m in ["email", "form", "google_form", "typeform"]))

    # Deduplicate and bound evidence snippets
    clean_evidence: List[str] = []
    for ev in evidence_snippets:
        if ev and ev not in clean_evidence and len(clean_evidence) < 5:
            clean_evidence.append(ev)

    return SubmissionExtractionResult(
        submission_methods=submission_methods,
        primary_submission_method=submission_methods[0] if submission_methods and submission_methods[0] != "unknown" else (submission_methods[0] if submission_methods else None),
        submission_emails=emails,
        primary_email=emails[0] if emails else None,
        submission_urls=submission_urls,
        primary_submission_url=submission_urls[0] if submission_urls else None,
        guidelines_urls=guidelines_urls,
        primary_guidelines_url=guidelines_urls[0] if guidelines_urls else None,
        is_paid=is_paid,
        pricing_model=pricing_model,
        price_amount=price_amount,
        evidence_snippets=clean_evidence,
        has_submission_channel=has_channel
    )


def extract_and_save_submission_info(
    db: Session,
    website_id: int
) -> Tuple[Optional[Website], SubmissionExtractionResult]:
    """Extract submission details from crawled website HTML and persist into GuestPostInformation.

    Args:
        db: SQLAlchemy database session.
        website_id: ID of the Website record.

    Returns:
        tuple of (Website entity, SubmissionExtractionResult)
    """
    website = db.get(Website, website_id)
    if not website:
        return None, SubmissionExtractionResult(
            submission_methods=["unknown"],
            has_submission_channel=False
        )

    # Execute deterministic extraction
    result = extract_submission_information(
        html=website.html_content,
        base_url=website.final_url or website.url
    )

    # Upsert GuestPostInformation record
    stmt = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
    gp_info = db.scalars(stmt).first()

    evidence_str = " | ".join(result.evidence_snippets) if result.evidence_snippets else None
    pricing_str = result.price_amount or (result.pricing_model if result.pricing_model != "unknown" else None)
    submission_method_str = ", ".join(result.submission_methods) if result.submission_methods else "unknown"

    if not gp_info:
        gp_info = GuestPostInformation(
            website_id=website.id,
            accepts_guest_posts=result.has_submission_channel,
            confidence=80 if result.has_submission_channel else 0,
            contact_email=result.primary_email,
            submission_url=result.primary_submission_url,
            guidelines_url=result.primary_guidelines_url or website.url,
            submission_method=submission_method_str,
            pricing=pricing_str,
            evidence=evidence_str,
            updated_at=datetime.now(timezone.utc)
        )
        db.add(gp_info)
    else:
        if result.primary_email:
            gp_info.contact_email = result.primary_email
        if result.primary_submission_url:
            gp_info.submission_url = result.primary_submission_url
        if result.primary_guidelines_url:
            gp_info.guidelines_url = result.primary_guidelines_url
        if submission_method_str != "unknown":
            gp_info.submission_method = submission_method_str
        if pricing_str:
            gp_info.pricing = pricing_str
        if evidence_str:
            gp_info.evidence = f"{gp_info.evidence} | {evidence_str}" if gp_info.evidence else evidence_str
        gp_info.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(website)

    return website, result
