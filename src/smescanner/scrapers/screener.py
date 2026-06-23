"""
Screener.in scraper — the single richest free source of standardised Indian
financials (P&L, balance sheet, cash flow, ratios, shareholding).

Method: plain HTML GET of ``/company/<SYMBOL>/`` (standalone) and
``/company/<SYMBOL>/consolidated/``. Screener renders every statement as an
HTML ``<table>`` inside a ``<section id="...">`` block, so we locate sections by
id and parse with pandas. No JS execution needed.

Anti-bot: Screener is light — a real User-Agent + ~3s spacing (set in the host
rate-limiter) is sufficient. We avoid the logged-in Excel export to stay within
their terms; the public pages carry everything the scoring engine needs.

Fallback: if a SYMBOL 404s (SME tickers sometimes differ), retry with the BSE
scripcode path (``/company/<scripcode>/``), which Screener also serves.

Returns dicts shaped for the ``annual_results`` / ``quarterly_results`` tables.
"""
from __future__ import annotations

import logging
import re
from io import StringIO
from typing import Optional

from bs4 import BeautifulSoup

from ..common.http import PoliteSession

log = logging.getLogger("smescanner.scrapers.screener")
BASE = "https://www.screener.in/company"

# Screener row label -> our canonical field. Labels are fuzzy-matched (substring,
# case-insensitive) because Screener varies them slightly across companies.
PL_MAP = {
    "sales": "revenue", "revenue": "revenue",
    "expenses": "_expenses",
    "operating profit": "ebitda",
    "other income": "other_income",
    "interest": "interest",
    "depreciation": "depreciation",
    "profit before tax": "pbt",
    "tax %": "_tax_pct",
    "net profit": "net_profit",
    "eps in rs": "eps",
}
BS_MAP = {
    "equity capital": "equity_capital",
    "reserves": "reserves",
    "borrowings": "total_debt",
    "other liabilities": "other_liabilities",
    "total liabilities": "total_liabilities",
    "fixed assets": "net_fixed_assets",
    "investments": "investments",
    "other assets": "other_assets",
    "total assets": "total_assets",
    "receivables": "receivables",
    "inventory": "inventory",
    "cash": "cash",
}
CF_MAP = {
    "cash from operating activity": "operating_cash_flow",
    "cash from investing activity": "investing_cash_flow",
    "cash from financing activity": "financing_cash_flow",
}


class ScreenerScraper:
    def __init__(self, session: PoliteSession | None = None) -> None:
        self.s = session or PoliteSession(rate_per_host=0.33)

    def fetch(self, symbol: str, consolidated: bool = True) -> Optional[dict]:
        path = f"{BASE}/{symbol}/" + ("consolidated/" if consolidated else "")
        resp = self.s.get(path)
        if resp.status_code == 404 and consolidated:
            return self.fetch(symbol, consolidated=False)
        if resp.status_code != 200:
            log.warning("Screener %s -> %s", symbol, resp.status_code)
            return None
        return self.parse(resp.text, symbol)

    # -- parsing -----------------------------------------------------------
    def parse(self, html: str, symbol: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        out: dict = {"symbol": symbol, "annual": [], "quarterly": []}

        pl = self._section_table(soup, "profit-loss")
        bs = self._section_table(soup, "balance-sheet")
        cf = self._section_table(soup, "cash-flow")
        qr = self._section_table(soup, "quarters")

        annual = self._merge_statements(pl, bs, cf, PL_MAP, BS_MAP, CF_MAP)
        out["annual"] = annual
        out["quarterly"] = self._parse_quarters(qr)
        out["ratios"] = self._top_ratios(soup)
        out["shareholding"] = self._parse_shareholding(self._section_table(soup, "shareholding"))
        return out

    def _parse_shareholding(self, sh) -> list[dict]:
        """Quarterly promoter / FII / DII / public holding from Screener's
        shareholding section. Promoter trend + pledge feed the management score."""
        if sh is None:
            return []
        out = []
        for col in [c for c in sh.columns if c != "label"]:
            pe = _col_to_period_end(col)
            if not pe:
                continue
            rec = {"period_end": pe, "source": "screener"}
            for _, row in sh.iterrows():
                label = str(row["label"]).lower()
                v = _num(row.get(col))
                if "promoter" in label:
                    rec["promoter_pct"] = v
                elif "fii" in label or "foreign" in label:
                    rec["fii_pct"] = v
                elif "dii" in label or "domestic" in label:
                    rec["dii_pct"] = v
                elif "government" in label:
                    rec["govt_pct"] = v
                elif "public" in label:
                    rec["public_pct"] = v
                elif "shareholder" in label:
                    rec["num_shareholders"] = int(v) if v is not None else None
            if rec.get("promoter_pct") is not None:
                out.append(rec)
        return out

    def _section_table(self, soup: BeautifulSoup, section_id: str):
        sec = soup.find("section", id=section_id)
        if not sec:
            return None
        table = sec.find("table")
        if not table:
            return None
        import pandas as pd

        try:
            raw = pd.read_html(StringIO(str(table)))[0]
        except ValueError:
            return None
        cols = list(raw.columns)
        cols[0] = "label"
        raw.columns = cols
        # Build the cleaned label column via .assign on a fresh frame — avoids the
        # pandas copy-on-write chained-assignment FutureWarning from in-place set.
        return raw.assign(
            label=raw.iloc[:, 0].astype(str).str.strip().str.rstrip("+").str.strip()
        )

    def _merge_statements(self, pl, bs, cf, pl_map, bs_map, cf_map) -> list[dict]:
        """Build one record per fiscal-year column present across statements."""
        if pl is None:
            return []
        year_cols = [c for c in pl.columns if c != "label"]
        records: dict[str, dict] = {}
        for col in year_cols:
            fy = _col_to_fy(col)
            if fy is None:
                continue
            rec: dict = {"fiscal_year": fy, "is_consolidated": True, "source": "screener"}
            self._pull(pl, col, pl_map, rec)
            if bs is not None and col in bs.columns:
                self._pull(bs, col, bs_map, rec)
            if cf is not None and col in cf.columns:
                self._pull(cf, col, cf_map, rec)
            _derive(rec)
            records[fy] = rec
        return list(records.values())

    def _pull(self, df, col, mapping, rec):
        for _, row in df.iterrows():
            label = str(row["label"]).lower()
            for needle, field in mapping.items():
                if needle in label:
                    rec[field] = _num(row.get(col))
                    break

    def _parse_quarters(self, qr) -> list[dict]:
        if qr is None:
            return []
        records = []
        for col in [c for c in qr.columns if c != "label"]:
            rec = {"fiscal_label": str(col), "source": "screener"}
            for _, row in qr.iterrows():
                label = str(row["label"]).lower()
                if "sales" in label or "revenue" in label:
                    rec["revenue"] = _num(row.get(col))
                elif "net profit" in label:
                    rec["net_profit"] = _num(row.get(col))
                elif "operating profit" in label:
                    rec["ebitda"] = _num(row.get(col))
            records.append(rec)
        return records

    def _top_ratios(self, soup) -> dict:
        """The header ratio strip (Market Cap, P/E, ROCE, etc.)."""
        ratios = {}
        for li in soup.select("#top-ratios li"):
            name = li.select_one(".name")
            val = li.select_one(".value")
            if name and val:
                ratios[name.get_text(strip=True)] = val.get_text(" ", strip=True)
        return ratios


# --------------------------------------------------------------------------- #
def _derive(rec: dict) -> None:
    """Fill derived fields Screener doesn't give directly."""
    if rec.get("equity_capital") is not None and rec.get("reserves") is not None:
        rec["equity"] = (rec["equity_capital"] or 0) + (rec["reserves"] or 0)
    if rec.get("ebitda") is not None and rec.get("depreciation") is not None:
        rec["ebit"] = rec["ebitda"] - (rec["depreciation"] or 0)
    if rec.get("revenue") is not None and rec.get("_expenses") is not None:
        # Screener 'Expenses' ~ operating expenses; COGS proxy.
        rec["cogs"] = rec["_expenses"]
    if rec.get("pbt") is not None and rec.get("_tax_pct") is not None:
        rec["tax"] = rec["pbt"] * (rec["_tax_pct"] or 0) / 100.0


def _num(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "-", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _col_to_fy(col) -> Optional[int]:
    """Screener columns look like 'Mar 2024' -> 2024."""
    m = re.search(r"(19|20)\d{2}", str(col))
    return int(m.group(0)) if m else None


_MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
           "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
_EOM = {"01": "31", "02": "28", "03": "31", "04": "30", "05": "31", "06": "30",
        "07": "31", "08": "31", "09": "30", "10": "31", "11": "30", "12": "31"}


def _col_to_period_end(col) -> Optional[str]:
    """'Mar 2024' -> '2024-03-31' (quarter-end date for the shareholding key)."""
    m = re.search(r"([A-Za-z]{3})\s*'?\s*(\d{2,4})", str(col))
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    yr = m.group(2)
    if len(yr) == 2:
        yr = "20" + yr
    return f"{yr}-{mon}-{_EOM[mon]}"
