"""
Annual-report reader: PDF -> text -> structured business facts.

Downloads the report PDF, extracts the Management Discussion & Analysis section
(where business model, capex, segments and concentration actually live), and asks
the local LLM to return a strict JSON object. Output feeds ``annual_reports`` and
the business-quality engine.

We extract only the MD&A / Directors' Report pages (not the full 200-page PDF) to
keep the local model's context manageable and the extraction grounded.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from ..config import REPORTS_DIR
from ..common.http import PoliteSession
from .llm import LocalLLM

log = logging.getLogger("smescanner.ai.report_reader")

EXTRACTION_SYSTEM = (
    "You extract structured facts from an Indian company's annual report. "
    "Return ONLY valid JSON with these keys: business_summary (<=80 words, plain "
    "English), revenue_segments (list), competitive_advantage (string), "
    "capex_plans (string), capacity_expansion (bool), export_pct (number or null), "
    "top_customer_pct (number or null), customer_concentration (string), "
    "supplier_concentration (string), moat_notes (string). Use null when the "
    "report does not say. Never guess numbers."
)

# Section markers we slice around to find MD&A / business content.
SECTION_HINTS = [
    "management discussion and analysis", "directors' report", "director's report",
    "business overview", "our business", "operational review",
]


class ReportReader:
    def __init__(self, session: PoliteSession | None = None, llm: LocalLLM | None = None) -> None:
        self.s = session or PoliteSession()
        self.llm = llm or LocalLLM()

    def download(self, url: str, company_id: int, fiscal_year: int) -> Optional[Path]:
        dest = REPORTS_DIR / f"{company_id}_AR_{fiscal_year}.pdf"
        if dest.exists():
            return dest
        try:
            resp = self.s.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("AR download failed %s: %s", url, exc)
            return None

    def extract_text(self, pdf_path: Path, max_chars: int = 24000) -> str:
        """Pull text, prioritising MD&A / business pages."""
        try:
            import pdfplumber
        except ImportError:
            log.error("pdfplumber not installed")
            return ""
        pages_text: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                pages_text.append(page.extract_text() or "")
        full = "\n".join(pages_text)
        sliced = self._slice_relevant(full, max_chars)
        return sliced

    def _slice_relevant(self, text: str, max_chars: int) -> str:
        low = text.lower()
        for hint in SECTION_HINTS:
            idx = low.find(hint)
            if idx != -1:
                return text[idx : idx + max_chars]
        return text[:max_chars]

    def analyse(self, pdf_path: Path) -> Optional[dict]:
        text = self.extract_text(pdf_path)
        if not text:
            return None
        if not self.llm.available():
            log.info("LLM offline — returning raw extracted text only")
            return {"business_summary": _first_paragraph(text), "extracted_text": text[:4000]}
        result = self.llm.complete_json(
            f"Annual report excerpt:\n\n{text}\n\nReturn the JSON object.",
            system=EXTRACTION_SYSTEM,
        )
        if result is not None:
            result["extracted_text"] = text[:8000]
        return result


def _first_paragraph(text: str) -> str:
    para = re.split(r"\n\s*\n", text.strip(), maxsplit=1)[0]
    return para[:600]
