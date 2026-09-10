"""CSV export service for website opportunities and saved websites (Step 20)."""

import csv
import io
from typing import List, Sequence
from fastapi.responses import Response
from app.models.website import Website


CSV_HEADERS: List[str] = [
    "Website Name",
    "Domain",
    "Niche",
    "Guest Post Status",
    "Pricing",
    "Submission Method",
    "Relevance Score",
    "Content Quality Score",
    "Quality Score",
    "Verification Status",
    "AI Confidence",
    "Submission URL",
    "Guidelines URL",
]


def generate_websites_csv(websites: Sequence[Website]) -> str:
    """Serialize a list of Website entities into an RFC 4180-compliant CSV string.

    Args:
        websites: Sequence of Website ORM entities with analysis and guest_post_info loaded.

    Returns:
        Formatted CSV string with headers.
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)

    for w in websites:
        analysis = w.analysis
        gp = w.guest_post_info

        # Deterministic guest post status label
        status_str = "pending"
        if gp:
            if gp.accepts_guest_posts is True:
                status_str = "accepting"
            elif gp.accepts_guest_posts is False:
                status_str = "not_accepting"
            elif gp.verification_status:
                status_str = gp.verification_status

        row = [
            w.name or "",
            w.domain or "",
            (analysis.primary_niche if analysis and analysis.primary_niche else "") or "",
            status_str,
            (gp.pricing if gp and gp.pricing else "") or "",
            (gp.submission_method if gp and gp.submission_method else "") or "",
            str(analysis.relevance_score) if analysis and analysis.relevance_score is not None else "",
            str(analysis.content_quality_score) if analysis and analysis.content_quality_score is not None else "",
            str(analysis.quality_score) if analysis and analysis.quality_score is not None else "",
            (gp.verification_status if gp and gp.verification_status else "unverified") or "unverified",
            str(gp.ai_confidence) if gp and gp.ai_confidence is not None else "",
            (gp.submission_url if gp and gp.submission_url else "") or "",
            (gp.guidelines_url if gp and gp.guidelines_url else "") or "",
        ]
        writer.writerow(row)

    return output.getvalue()


def create_csv_response(csv_content: str, filename: str) -> Response:
    """Wrap CSV content in a FastAPI Response with appropriate headers for attachment download.

    Args:
        csv_content: String content of the CSV.
        filename: Proposed download filename (e.g. 'guest_posting_opportunities.csv').

    Returns:
        FastAPI Response with UTF-8 BOM encoding for broad spreadsheet compatibility.
    """
    # Use UTF-8 BOM (utf-8-sig) so Microsoft Excel, Google Sheets, LibreOffice cleanly render UTF-8 characters
    encoded_bytes = csv_content.encode("utf-8-sig")

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    return Response(
        content=encoded_bytes,
        media_type="text/csv",
        headers=headers,
    )
