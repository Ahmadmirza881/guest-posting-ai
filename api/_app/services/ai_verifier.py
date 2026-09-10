"""AI Semantic Verification Module (Step 15).

Integrates Google Gemini to semantically verify and cross-validate deterministic detection
and extraction results (from Steps 13 and 14) against crawled page text.

CRITICAL CONSTRAINTS:
- Semantic verification ONLY (NO web crawling, NO discovering websites).
- Anti-hallucination protections: strict validation against supplied content; NEVER invent data.
- Distinguish past guest-post mentions from active contributor invitations.
- Honor negative/closed submission statements.
- Configurable model & secure backend-only API key handling.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.website import Website
from app.models.guest_post import GuestPostInformation
from app.utils.cache import app_cache, generate_cache_key
from app.utils.rate_limiter import get_ai_limiter
from app.utils.retry import execute_with_retry
from app.services.crawler import extract_html_title
from app.services.guest_post_detector import (
    detect_guest_post_opportunity,
    normalize_html_for_detection,
)
from app.services.submission_extractor import extract_submission_information

logger = logging.getLogger(__name__)


class AIVerificationInput(BaseModel):
    """Structured input payload prepared for Gemini semantic verification."""
    website_url: str
    page_title: Optional[str] = None
    cleaned_page_text: str
    step13_detected: bool
    step13_confidence: int
    step13_signals: List[str] = []
    step13_evidence: List[str] = []
    step14_submission_methods: List[str] = []
    step14_email: Optional[str] = None
    step14_submission_url: Optional[str] = None
    step14_guidelines_url: Optional[str] = None
    step14_pricing: Optional[str] = None
    step14_evidence: List[str] = []


class AIVerificationResult(BaseModel):
    """Structured semantic verification result returned by Gemini."""
    verification_status: str  # "verified", "rejected", "uncertain"
    accepts_guest_posts: Optional[bool] = None
    confidence: int  # 0 to 100
    reason: str
    guest_post_evidence: Optional[str] = None
    submission_method: Optional[str] = None
    submission_email: Optional[str] = None
    submission_url: Optional[str] = None
    guidelines_url: Optional[str] = None
    pricing: Optional[str] = None
    corrections: List[str] = []
    raw_model_response: Optional[str] = None


class GeminiAPIError(Exception):
    """Exception raised when Gemini API call fails or returns error status."""
    pass


def build_verification_prompt(data: AIVerificationInput) -> str:
    """Construct a clean, structured verification prompt for Gemini."""
    text_snippet = data.cleaned_page_text[:4000]

    return f"""You are an expert editorial auditor verifying whether a website actively accepts guest posts or contributor submissions.

TASK:
Audit the provided webpage text and cross-validate the heuristic detection data.

INPUT DATA:
- Website URL: {data.website_url}
- Page Title: {data.page_title or "N/A"}
- Rule-Based Detection: {"Accepted/Detected" if data.step13_detected else "Not Detected"} (Confidence: {data.step13_confidence}%)
- Matched Signals: {', '.join(data.step13_signals) if data.step13_signals else "None"}
- Step 13 Evidence: {' | '.join(data.step13_evidence) if data.step13_evidence else "None"}
- Extracted Email: {data.step14_email or "None"}
- Extracted Submission URL: {data.step14_submission_url or "None"}
- Extracted Guidelines URL: {data.step14_guidelines_url or "None"}
- Extracted Pricing: {data.step14_pricing or "None"}
- Extracted Methods: {', '.join(data.step14_submission_methods) if data.step14_submission_methods else "None"}

CLEANED WEBPAGE CONTENT:
\"\"\"
{text_snippet}
\"\"\"

CRITICAL AUDIT RULES:
1. "verified": The page contains clear, active invitations or guidelines for guest contributors to submit content (e.g. "Write for Us", submission guidelines, active form/email).
2. "rejected": The page explicitly states guest posts are closed/not accepted, or mentions a past guest author without offering an open submission channel.
3. "uncertain": The page mentions writing or guest posts ambiguously without clear submission instructions or guidelines.
4. ANTI-HALLUCINATION: Base your decision ONLY on the provided text. NEVER invent emails, URLs, prices, or policies not present in the text. Return null for unverified fields.
5. If the deterministic extraction extracted an incorrect email (e.g. privacy/sales email) or incorrect price, note it in "corrections" and set the field to null or the correct value.

OUTPUT FORMAT:
Respond with ONLY a valid JSON object matching this exact schema:
{{
  "verification_status": "verified" | "rejected" | "uncertain",
  "accepts_guest_posts": true | false | null,
  "confidence": 0-100,
  "reason": "Brief explanation of verification decision",
  "guest_post_evidence": "Exact quoted sentence from text or null",
  "submission_method": "email" | "form" | "google_form" | "typeform" | null,
  "submission_email": "validated email or null",
  "submission_url": "validated url or null",
  "guidelines_url": "validated guidelines url or null",
  "pricing": "validated pricing or null",
  "corrections": ["List of correction descriptions if any"]
}}
"""


async def call_gemini_api(
    prompt: str,
    client: Optional[httpx.AsyncClient] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None
) -> dict:
    """Call Google Gemini REST API with structured JSON output request.

    Enforces:
    - Shared AI rate limiter / concurrency guard (Step 24).
    - Exponential backoff retry for transient Gemini/network errors (Step 24).

    Args:
        prompt: Formatted verification prompt.
        client: Optional shared httpx.AsyncClient.
        api_key: Optional Gemini API key override.
        model: Optional model name override.
        timeout: Optional request timeout.

    Returns:
        Parsed JSON dictionary response from model.
    """
    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise GeminiAPIError("GEMINI_API_KEY is not configured in backend environment variables.")

    model_name = model or settings.GEMINI_MODEL
    timeout_sec = timeout if timeout is not None else settings.GEMINI_TIMEOUT_SECONDS

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec))
        should_close = True

    async def _post_gemini() -> httpx.Response:
        resp = await client.post(
            api_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if resp.status_code in (429, 500, 502, 503, 504):
            raise GeminiAPIError(f"Gemini transient status {resp.status_code}: {resp.text[:300]}")
        return resp

    try:
        response = await execute_with_retry(
            _post_gemini,
            limiter=get_ai_limiter(),
            operation_name="Gemini API GenerateContent",
        )

        if response.status_code != 200:
            err_msg = f"Gemini API returned status {response.status_code}: {response.text[:300]}"
            logger.error(err_msg)
            raise GeminiAPIError(err_msg)

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise GeminiAPIError("Gemini returned empty candidates list.")

        first_candidate = candidates[0]
        content_parts = first_candidate.get("content", {}).get("parts", [])
        if not content_parts:
            raise GeminiAPIError("Gemini response candidate missing text parts.")

        raw_text = content_parts[0].get("text", "").strip()

        # Parse JSON from response
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            # Attempt regex extraction if model included markdown wrappers
            match = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise GeminiAPIError(f"Failed to parse Gemini response as JSON: {raw_text[:200]}")

    except httpx.TimeoutException:
        raise GeminiAPIError(f"Gemini API request timed out after {timeout_sec} seconds.")
    except httpx.NetworkError as e:
        raise GeminiAPIError(f"Network error connecting to Gemini API: {str(e)}")
    finally:
        if should_close:
            await client.aclose()


async def verify_guest_post_opportunity(
    input_data: AIVerificationInput,
    client: Optional[httpx.AsyncClient] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> AIVerificationResult:
    """Execute AI semantic verification for a candidate guest posting page.

    Enforces:
    - In-memory TTL caching (Step 24).
    - Rate-limited and retried Gemini API calls (Step 24).

    Args:
        input_data: Structured AIVerificationInput payload.
        client: Optional shared httpx client.
        api_key: Optional API key.
        model: Optional model name.

    Returns:
        Structured AIVerificationResult.
    """
    if not input_data.cleaned_page_text:
        return AIVerificationResult(
            verification_status="uncertain",
            accepts_guest_posts=None,
            confidence=0,
            reason="Empty or missing webpage text.",
            corrections=[]
        )

    # Cache Lookup (Step 24)
    cache_key = generate_cache_key(
        "ai_verify",
        input_data.website_url,
        input_data.cleaned_page_text[:4000],
        input_data.step13_detected,
        input_data.step13_confidence,
        input_data.step13_signals,
        input_data.step14_submission_methods,
        input_data.step14_email,
        input_data.step14_pricing,
    )
    cached_result = await app_cache.get(cache_key)
    if cached_result is not None and isinstance(cached_result, AIVerificationResult):
        logger.debug(f"Cache hit for AI verification: {input_data.website_url}")
        return cached_result

    prompt = build_verification_prompt(input_data)

    try:
        raw_json = await call_gemini_api(
            prompt=prompt,
            client=client,
            api_key=api_key,
            model=model
        )

        status = str(raw_json.get("verification_status", "uncertain")).lower()
        if status not in ("verified", "rejected", "uncertain"):
            status = "uncertain"

        accepts = raw_json.get("accepts_guest_posts")
        if isinstance(accepts, str):
            accepts = accepts.lower() == "true"
        elif not isinstance(accepts, bool):
            accepts = True if status == "verified" else (False if status == "rejected" else None)

        conf = int(raw_json.get("confidence", 0))
        conf = max(0, min(100, conf))

        reason = str(raw_json.get("reason", "Verification completed."))
        evidence = raw_json.get("guest_post_evidence")
        method = raw_json.get("submission_method")
        email = raw_json.get("submission_email")
        sub_url = raw_json.get("submission_url")
        guide_url = raw_json.get("guidelines_url")
        pricing = raw_json.get("pricing")
        corrections = raw_json.get("corrections", [])
        if not isinstance(corrections, list):
            corrections = [str(corrections)] if corrections else []

        verification_result = AIVerificationResult(
            verification_status=status,
            accepts_guest_posts=accepts,
            confidence=conf,
            reason=reason,
            guest_post_evidence=str(evidence) if evidence else None,
            submission_method=str(method) if method else None,
            submission_email=str(email) if email else None,
            submission_url=str(sub_url) if sub_url else None,
            guidelines_url=str(guide_url) if guide_url else None,
            pricing=str(pricing) if pricing else None,
            corrections=[str(c) for c in corrections if c],
            raw_model_response=json.dumps(raw_json)
        )

        # Cache successful verification outcome
        await app_cache.set(cache_key, verification_result)

        return verification_result

    except GeminiAPIError as e:
        logger.warning(f"AI Verification fallback due to Gemini error: {e}")
        return AIVerificationResult(
            verification_status="uncertain",
            accepts_guest_posts=None,
            confidence=0,
            reason=f"AI verification unavailable: {str(e)}",
            corrections=[]
        )
    except Exception as e:
        logger.error(f"Unexpected error in AI Verification: {e}")
        return AIVerificationResult(
            verification_status="uncertain",
            accepts_guest_posts=None,
            confidence=0,
            reason=f"AI verification error: {str(e)}",
            corrections=[]
        )


async def verify_website_record(
    db: Session,
    website_id: int,
    client: Optional[httpx.AsyncClient] = None,
    api_key: Optional[str] = None
) -> Tuple[Optional[Website], AIVerificationResult]:
    """Load website record, execute Gemini semantic verification, and persist results in database.

    Args:
        db: SQLAlchemy database session.
        website_id: ID of the Website record.
        client: Optional shared httpx client.
        api_key: Optional Gemini API key.

    Returns:
        tuple of (Website entity, AIVerificationResult)
    """
    website = db.get(Website, website_id)
    if not website:
        return None, AIVerificationResult(
            verification_status="uncertain",
            accepts_guest_posts=None,
            confidence=0,
            reason=f"Website #{website_id} not found in database.",
            corrections=[]
        )

    if not website.html_content:
        return website, AIVerificationResult(
            verification_status="uncertain",
            accepts_guest_posts=None,
            confidence=0,
            reason="Website has not been crawled yet. No HTML content available.",
            corrections=[]
        )

    # 1. Run / load Step 13 detection
    step13_res = detect_guest_post_opportunity(
        html_content=website.html_content,
        url=website.final_url or website.url
    )

    # 2. Run / load Step 14 extraction
    step14_res = extract_submission_information(
        html=website.html_content,
        base_url=website.final_url or website.url
    )

    clean_text = normalize_html_for_detection(website.html_content)
    page_title = website.name or extract_html_title(website.html_content)

    # 3. Prepare verification input payload
    verification_input = AIVerificationInput(
        website_url=website.final_url or website.url,
        page_title=page_title,
        cleaned_page_text=clean_text,
        step13_detected=step13_res.detected,
        step13_confidence=step13_res.confidence,
        step13_signals=step13_res.all_positive_signals + step13_res.negative_signals,
        step13_evidence=step13_res.evidence_snippets,
        step14_submission_methods=step14_res.submission_methods,
        step14_email=step14_res.primary_email,
        step14_submission_url=step14_res.primary_submission_url,
        step14_guidelines_url=step14_res.primary_guidelines_url,
        step14_pricing=step14_res.price_amount or (step14_res.pricing_model if step14_res.pricing_model != "unknown" else None),
        step14_evidence=step14_res.evidence_snippets
    )

    # 4. Execute AI Verification
    verification_res = await verify_guest_post_opportunity(
        input_data=verification_input,
        client=client,
        api_key=api_key
    )

    # 5. Persist into GuestPostInformation model
    stmt = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
    gp_info = db.scalars(stmt).first()

    now_utc = datetime.now(timezone.utc)

    if not gp_info:
        gp_info = GuestPostInformation(
            website_id=website.id,
            accepts_guest_posts=bool(verification_res.accepts_guest_posts) if verification_res.accepts_guest_posts is not None else step13_res.detected,
            confidence=verification_res.confidence if verification_res.verification_status != "uncertain" else step13_res.confidence,
            verification_status=verification_res.verification_status,
            ai_confidence=verification_res.confidence,
            ai_reason=verification_res.reason,
            ai_evidence=verification_res.guest_post_evidence,
            verified_at=now_utc,
            contact_email=verification_res.submission_email or step14_res.primary_email,
            submission_url=verification_res.submission_url or step14_res.primary_submission_url,
            guidelines_url=verification_res.guidelines_url or step14_res.primary_guidelines_url or website.url,
            pricing=verification_res.pricing or step14_res.price_amount,
            submission_method=verification_res.submission_method or (", ".join(step14_res.submission_methods) if step14_res.submission_methods else None),
            evidence=" | ".join(step13_res.evidence_snippets + step14_res.evidence_snippets),
            updated_at=now_utc
        )
        db.add(gp_info)
    else:
        gp_info.verification_status = verification_res.verification_status
        gp_info.ai_confidence = verification_res.confidence
        gp_info.ai_reason = verification_res.reason
        gp_info.ai_evidence = verification_res.guest_post_evidence
        gp_info.verified_at = now_utc

        if verification_res.verification_status == "verified":
            gp_info.accepts_guest_posts = True
            gp_info.confidence = verification_res.confidence
            if verification_res.submission_email:
                gp_info.contact_email = verification_res.submission_email
            if verification_res.submission_url:
                gp_info.submission_url = verification_res.submission_url
            if verification_res.guidelines_url:
                gp_info.guidelines_url = verification_res.guidelines_url
            if verification_res.pricing:
                gp_info.pricing = verification_res.pricing
            if verification_res.submission_method:
                gp_info.submission_method = verification_res.submission_method
        elif verification_res.verification_status == "rejected":
            gp_info.accepts_guest_posts = False

        gp_info.updated_at = now_utc

    db.commit()
    db.refresh(website)

    return website, verification_res
