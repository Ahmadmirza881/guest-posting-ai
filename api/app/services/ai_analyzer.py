"""AI Semantic Website Analysis Module (Step 16).

Integrates Google Gemini to evaluate website niche, topic breadth, content quality,
relevance against the search query, trust signals, and editorial standards from crawled page text.

CRITICAL CONSTRAINTS:
- Semantic analysis ONLY (NO final scoring calculation; Step 17 is separate).
- Anti-hallucination protections: evaluate strictly against supplied content and search keyword.
- Normalize and clamp all scores to 0–100 integers.
- Configurable model & secure backend-only API key handling.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.website import Website
from app.models.search import Search
from app.models.search_result import SearchResult
from app.models.website_analysis import WebsiteAnalysis
from app.models.guest_post import GuestPostInformation
from app.utils.cache import app_cache, generate_cache_key
from app.services.guest_post_detector import (
    detect_guest_post_opportunity,
    normalize_html_for_detection,
)
from app.services.crawler import extract_html_title
from app.services.submission_extractor import extract_submission_information
from app.services.ai_verifier import call_gemini_api, GeminiAPIError

logger = logging.getLogger(__name__)


def clamp_score(value: Optional[int], default: int = 0) -> int:
    """Clamp an analysis score to a safe integer in the 0-100 range."""
    if value is None:
        return default
    try:
        int_val = int(value)
        return max(0, min(100, int_val))
    except (ValueError, TypeError):
        return default


class AIAnalysisInput(BaseModel):
    """Structured input payload for Gemini semantic website analysis."""
    website_url: str
    domain: str
    page_title: Optional[str] = None
    search_keyword: Optional[str] = None
    cleaned_page_text: str
    step13_detected: bool = False
    step13_confidence: int = 0
    step14_methods: List[str] = []
    step14_pricing: Optional[str] = None
    step15_status: Optional[str] = None
    step15_confidence: Optional[int] = None
    step15_reason: Optional[str] = None


class AIAnalysisResult(BaseModel):
    """Structured semantic website analysis result returned by Gemini."""
    primary_niche: Optional[str] = None
    topics: List[str] = []
    niche_confidence: int = 0
    relevance_score: int = 0
    relevance_reason: str = ""
    content_quality_score: int = 0
    content_quality_reason: str = ""
    trust_signals: List[str] = []
    editorial_standards: List[str] = []
    strengths: List[str] = []
    weaknesses: List[str] = []
    analysis_confidence: int = 0
    evidence: List[str] = []
    warnings: List[str] = []
    analysis_status: str = "completed"  # "completed", "partial", "failed"
    raw_model_response: Optional[str] = None


def build_analysis_prompt(data: AIAnalysisInput) -> str:
    """Construct an editorial analysis prompt for Gemini."""
    text_snippet = data.cleaned_page_text[:4500]

    return f"""You are an expert editorial auditor and web quality analyst evaluating a website for content outreach and guest posting opportunities.

TASK:
Analyze the provided webpage content and evaluate its niche, topic breadth, content quality, relevance to the target search query, trust signals, and editorial standards.

INPUT CONTEXT:
- Target Search Keyword/Niche: {data.search_keyword or "General Web"}
- Website URL: {data.website_url}
- Domain: {data.domain}
- Page Title: {data.page_title or "N/A"}
- Guest Post Verification Status: {data.step15_status or "Unknown"} (Confidence: {data.step15_confidence or 0}%)
- Extracted Submission Method: {', '.join(data.step14_methods) if data.step14_methods else "None"}
- Pricing/Fee Statement: {data.step14_pricing or "Unstated"}

CLEANED WEBPAGE CONTENT:
\"\"\"
{text_snippet}
\"\"\"

ANALYSIS GUIDELINES:
1. PRIMARY NICHE & TOPICS: Identify the overarching industry/niche and key topics covered. If indeterminate, return null/empty.
2. CONTENT QUALITY (0-100): Evaluate depth, writing standard, readability, and usefulness. Provide a concise reason.
3. NICHE RELEVANCE (0-100): Score how relevant this website's focus is to the searched keyword: \"{data.search_keyword or 'General'}\". If completely unrelated, score low.
4. TRUST SIGNALS: Extract visible indicators of legitimacy (e.g., About info, author bylines, contact details, editorial disclosures, organization info).
5. EDITORIAL STANDARDS: Extract visible contributor policies, editorial requirements, or content standards.
6. STRENGTHS & WEAKNESSES: List 1-4 concrete, evidence-based strengths and weaknesses supported by the content.
7. ANTI-HALLUCINATION RULES:
   - Base all observations strictly on the provided content.
   - Do NOT invent metrics, traffic numbers, domain authority, author names, or email addresses not in the text.
   - Do NOT calculate a final overall website score (this is analysis only).
   - Scores must be integers from 0 to 100.

OUTPUT FORMAT:
Respond with ONLY a valid JSON object matching this exact schema:
{{
  "primary_niche": "string or null",
  "topics": ["topic1", "topic2"],
  "niche_confidence": 0-100,
  "relevance_score": 0-100,
  "relevance_reason": "Brief explanation of relevance to searched keyword",
  "content_quality_score": 0-100,
  "content_quality_reason": "Brief explanation of content quality evaluation",
  "trust_signals": ["signal1", "signal2"],
  "editorial_standards": ["standard1", "standard2"],
  "strengths": ["strength1", "strength2"],
  "weaknesses": ["weakness1"],
  "analysis_confidence": 0-100,
  "evidence": ["Exact quoted phrase or sentence from text"],
  "warnings": []
}}
"""


async def analyze_website_content(
    input_data: AIAnalysisInput,
    client: Optional[httpx.AsyncClient] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> AIAnalysisResult:
    """Execute Gemini semantic website analysis.

    Args:
        input_data: Structured AIAnalysisInput payload.
        client: Optional shared httpx client.
        api_key: Optional Gemini API key.
        model: Optional model name override.

    Returns:
        Structured AIAnalysisResult.
    """
    if not input_data.cleaned_page_text or len(input_data.cleaned_page_text.strip()) < 10:
        return AIAnalysisResult(
            primary_niche=None,
            topics=[],
            niche_confidence=0,
            relevance_score=0,
            relevance_reason="Webpage content is empty or insufficient for semantic analysis.",
            content_quality_score=0,
            content_quality_reason="No readable content found on crawled page.",
            trust_signals=[],
            editorial_standards=[],
            strengths=[],
            weaknesses=["Insufficient text content on crawled page."],
            analysis_confidence=0,
            evidence=[],
            warnings=["Content too brief for reliable evaluation."],
            analysis_status="failed"
        )

    # Cache Lookup (Step 24)
    cache_key = generate_cache_key(
        "ai_analyze",
        input_data.website_url,
        input_data.search_keyword or "",
        input_data.cleaned_page_text[:4500],
        input_data.step13_detected,
        input_data.step13_confidence,
        input_data.step14_methods,
        input_data.step15_status,
    )
    cached_result = await app_cache.get(cache_key)
    if cached_result is not None and isinstance(cached_result, AIAnalysisResult):
        logger.debug(f"Cache hit for AI analysis: {input_data.website_url}")
        return cached_result

    prompt = build_analysis_prompt(input_data)

    try:
        raw_json = await call_gemini_api(
            prompt=prompt,
            client=client,
            api_key=api_key,
            model=model
        )

        niche = raw_json.get("primary_niche")
        topics = raw_json.get("topics", [])
        if not isinstance(topics, list):
            topics = [str(topics)] if topics else []

        niche_conf = clamp_score(raw_json.get("niche_confidence"), default=0)
        rel_score = clamp_score(raw_json.get("relevance_score"), default=0)
        rel_reason = str(raw_json.get("relevance_reason", "Relevance evaluated."))
        cq_score = clamp_score(raw_json.get("content_quality_score"), default=0)
        cq_reason = str(raw_json.get("content_quality_reason", "Quality evaluated."))

        trust_signals = raw_json.get("trust_signals", [])
        if not isinstance(trust_signals, list):
            trust_signals = [str(trust_signals)] if trust_signals else []

        editorial_standards = raw_json.get("editorial_standards", [])
        if not isinstance(editorial_standards, list):
            editorial_standards = [str(editorial_standards)] if editorial_standards else []

        strengths = raw_json.get("strengths", [])
        if not isinstance(strengths, list):
            strengths = [str(strengths)] if strengths else []

        weaknesses = raw_json.get("weaknesses", [])
        if not isinstance(weaknesses, list):
            weaknesses = [str(weaknesses)] if weaknesses else []

        analysis_conf = clamp_score(raw_json.get("analysis_confidence"), default=0)

        evidence = raw_json.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [str(evidence)] if evidence else []

        warnings = raw_json.get("warnings", [])
        if not isinstance(warnings, list):
            warnings = [str(warnings)] if warnings else []

        analysis_result = AIAnalysisResult(
            primary_niche=str(niche) if niche else None,
            topics=[str(t) for t in topics if t],
            niche_confidence=niche_conf,
            relevance_score=rel_score,
            relevance_reason=rel_reason,
            content_quality_score=cq_score,
            content_quality_reason=cq_reason,
            trust_signals=[str(s) for s in trust_signals if s],
            editorial_standards=[str(e) for e in editorial_standards if e],
            strengths=[str(st) for st in strengths if st],
            weaknesses=[str(w) for w in weaknesses if w],
            analysis_confidence=analysis_conf,
            evidence=[str(ev) for ev in evidence if ev],
            warnings=[str(wg) for wg in warnings if wg],
            analysis_status="completed",
            raw_model_response=json.dumps(raw_json)
        )

        # Cache completed analysis result
        await app_cache.set(cache_key, analysis_result)

        return analysis_result

    except GeminiAPIError as e:
        logger.warning(f"AI Website Analysis fallback due to Gemini error: {e}")
        return AIAnalysisResult(
            primary_niche=None,
            topics=[],
            niche_confidence=0,
            relevance_score=0,
            relevance_reason=f"AI analysis unavailable: {str(e)}",
            content_quality_score=0,
            content_quality_reason=f"AI analysis unavailable: {str(e)}",
            trust_signals=[],
            editorial_standards=[],
            strengths=[],
            weaknesses=[],
            analysis_confidence=0,
            evidence=[],
            warnings=[f"Gemini API error: {str(e)}"],
            analysis_status="failed"
        )
    except Exception as e:
        logger.error(f"Unexpected error in AI Website Analysis: {e}")
        return AIAnalysisResult(
            primary_niche=None,
            topics=[],
            niche_confidence=0,
            relevance_score=0,
            relevance_reason=f"Analysis error: {str(e)}",
            content_quality_score=0,
            content_quality_reason=f"Analysis error: {str(e)}",
            trust_signals=[],
            editorial_standards=[],
            strengths=[],
            weaknesses=[],
            analysis_confidence=0,
            evidence=[],
            warnings=[f"Analysis error: {str(e)}"],
            analysis_status="failed"
        )


async def analyze_website_record(
    db: Session,
    website_id: int,
    search_keyword: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    api_key: Optional[str] = None
) -> Tuple[Optional[Website], AIAnalysisResult]:
    """Load website record, run Gemini semantic analysis, and persist in database.

    Args:
        db: SQLAlchemy database session.
        website_id: ID of the Website record.
        search_keyword: Optional search keyword override.
        client: Optional shared httpx client.
        api_key: Optional Gemini API key.

    Returns:
        tuple of (Website entity, AIAnalysisResult)
    """
    website = db.get(Website, website_id)
    if not website:
        return None, AIAnalysisResult(
            relevance_reason=f"Website #{website_id} not found in database.",
            content_quality_reason="Website not found.",
            analysis_status="failed",
            warnings=["Website record not found."]
        )

    if not website.html_content:
        return website, AIAnalysisResult(
            relevance_reason="Website has not been crawled yet. No HTML content available.",
            content_quality_reason="No HTML content.",
            analysis_status="failed",
            warnings=["Website must be crawled before running AI analysis."]
        )

    # 1. Infer search keyword if not provided
    keyword = search_keyword
    if not keyword:
        # Check associated Search records
        stmt = (
            select(Search.keyword)
            .join(SearchResult, SearchResult.search_id == Search.id)
            .where(SearchResult.website_id == website.id)
            .order_by(Search.created_at.desc())
        )
        found_kw = db.scalars(stmt).first()
        if found_kw:
            keyword = found_kw

    # 2. Gather Step 13, Step 14, and Step 15 information
    step13_res = detect_guest_post_opportunity(
        html_content=website.html_content,
        url=website.final_url or website.url
    )
    step14_res = extract_submission_information(
        html=website.html_content,
        base_url=website.final_url or website.url
    )

    gp_stmt = select(GuestPostInformation).where(GuestPostInformation.website_id == website.id)
    gp_info = db.scalars(gp_stmt).first()

    clean_text = normalize_html_for_detection(website.html_content)
    page_title = website.name or extract_html_title(website.html_content)

    # 3. Prepare analysis payload
    analysis_input = AIAnalysisInput(
        website_url=website.final_url or website.url,
        domain=website.domain,
        page_title=page_title,
        search_keyword=keyword,
        cleaned_page_text=clean_text,
        step13_detected=step13_res.detected,
        step13_confidence=step13_res.confidence,
        step14_methods=step14_res.submission_methods,
        step14_pricing=step14_res.price_amount or (step14_res.pricing_model if step14_res.pricing_model != "unknown" else None),
        step15_status=gp_info.verification_status if gp_info else None,
        step15_confidence=gp_info.ai_confidence if gp_info else None,
        step15_reason=gp_info.ai_reason if gp_info else None
    )

    # 4. Execute Semantic AI Analysis
    analysis_res = await analyze_website_content(
        input_data=analysis_input,
        client=client,
        api_key=api_key
    )

    # 5. Persist into WebsiteAnalysis model
    wa_stmt = select(WebsiteAnalysis).where(WebsiteAnalysis.website_id == website.id)
    wa_record = db.scalars(wa_stmt).first()

    now_utc = datetime.now(timezone.utc)

    # Calculate trust indicator score from trust signals count
    trust_score = min(100, len(analysis_res.trust_signals) * 25) if analysis_res.trust_signals else None

    if not wa_record:
        wa_record = WebsiteAnalysis(
            website_id=website.id,
            primary_niche=analysis_res.primary_niche,
            topics=json.dumps(analysis_res.topics),
            niche_confidence=analysis_res.niche_confidence,
            niche_relevance=analysis_res.relevance_score,
            relevance_score=analysis_res.relevance_score,
            relevance_reason=analysis_res.relevance_reason,
            content_quality=analysis_res.content_quality_score,
            content_quality_score=analysis_res.content_quality_score,
            content_quality_reason=analysis_res.content_quality_reason,
            website_trust=trust_score,
            trust_signals=json.dumps(analysis_res.trust_signals),
            editorial_standards=json.dumps(analysis_res.editorial_standards),
            strengths=json.dumps(analysis_res.strengths),
            weaknesses=json.dumps(analysis_res.weaknesses),
            analysis_evidence=json.dumps(analysis_res.evidence),
            warnings=json.dumps(analysis_res.warnings),
            analysis_confidence=analysis_res.analysis_confidence,
            analysis_status=analysis_res.analysis_status,
            analyzed_at=now_utc
        )
        db.add(wa_record)
    else:
        wa_record.primary_niche = analysis_res.primary_niche
        wa_record.topics = json.dumps(analysis_res.topics)
        wa_record.niche_confidence = analysis_res.niche_confidence
        wa_record.niche_relevance = analysis_res.relevance_score
        wa_record.relevance_score = analysis_res.relevance_score
        wa_record.relevance_reason = analysis_res.relevance_reason
        wa_record.content_quality = analysis_res.content_quality_score
        wa_record.content_quality_score = analysis_res.content_quality_score
        wa_record.content_quality_reason = analysis_res.content_quality_reason
        if trust_score is not None:
            wa_record.website_trust = trust_score
        wa_record.trust_signals = json.dumps(analysis_res.trust_signals)
        wa_record.editorial_standards = json.dumps(analysis_res.editorial_standards)
        wa_record.strengths = json.dumps(analysis_res.strengths)
        wa_record.weaknesses = json.dumps(analysis_res.weaknesses)
        wa_record.analysis_evidence = json.dumps(analysis_res.evidence)
        wa_record.warnings = json.dumps(analysis_res.warnings)
        wa_record.analysis_confidence = analysis_res.analysis_confidence
        wa_record.analysis_status = analysis_res.analysis_status
        wa_record.analyzed_at = now_utc

    db.commit()
    db.refresh(website)

    return website, analysis_res
