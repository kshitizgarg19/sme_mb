"""
FastAPI live-data bridge.

Wraps the read-only XTS market-data client and serves live quotes / depth /
candles to the Next.js dashboard, keyed by our own ``company_id`` (the frontend
never needs to know XTS instrument IDs). One long-lived market-data session is
shared across requests and silently re-logged-in if the token expires.

Run:  uvicorn smescanner.live.service:app --host 127.0.0.1 --port 8088
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from ..config import ROOT
from ..db.session import get_engine
from ..scrapers.nse_corp import NSECorpScraper
from .xts import XTSMarketData

# Load SME_XTS_* (and DB url) before the client reads them at instantiation.
load_dotenv(ROOT / ".env")

log = logging.getLogger("smescanner.live.service")

_xts = XTSMarketData()
_lock = threading.Lock()
_map: dict[int, tuple[int, int]] = {}  # company_id -> (segment, instrumentID)
_nse_corp: NSECorpScraper | None = None  # lazy (cookie handshake is slow)
_news_cache: dict[int, tuple[float, list]] = {}
NEWS_TTL = 1800  # 30 min — announcements don't change minute-to-minute
_deals_cache: tuple[float, list] | None = None
DEALS_TTL = 3600  # 1 hr — bulk/block deals are a once-a-day CSV


def _load_map() -> None:
    global _map
    with get_engine().connect() as c:
        rows = c.execute(text(
            "SELECT company_id, xts_segment, xts_instrument_id "
            "FROM companies WHERE xts_instrument_id IS NOT NULL"
        ))
        _map = {r[0]: (r[1], r[2]) for r in rows}
    log.info("loaded %d instrument mappings", len(_map))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _xts.login()
        _load_map()
    except Exception as exc:  # noqa: BLE001 — start anyway; /health shows status
        log.error("startup: %s", exc)
    yield


app = FastAPI(title="SME Scanner — Live Data", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3030", "http://127.0.0.1:3030"],
    allow_methods=["*"], allow_headers=["*"],
)


def _retry(fn):
    """Run fn; on any failure assume token expiry, re-login once, retry."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        with _lock:
            _xts.login()
        return fn()


@app.get("/health")
def health():
    return {"ok": bool(_xts.token), "mapped": len(_map), "user": _xts.user_id}


@app.get("/live/quotes")
def quotes(ids: str = Query(..., description="comma-separated company_ids")):
    cids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    instruments = [_map[c] for c in cids if c in _map]
    if not instruments:
        return {}
    data = _retry(lambda: _xts.touchline(instruments))
    id2c = {_map[c][1]: c for c in cids if c in _map}
    return {str(id2c[iid]): v for iid, v in data.items() if iid in id2c}


@app.get("/live/quote/{company_id}")
def quote(company_id: int):
    if company_id not in _map:
        raise HTTPException(404, "no XTS mapping for this company")
    seg, iid = _map[company_id]
    data = _retry(lambda: _xts.touchline([(seg, iid)]))
    return data.get(iid, {})


@app.get("/live/depth/{company_id}")
def depth(company_id: int):
    if company_id not in _map:
        raise HTTPException(404, "no XTS mapping")
    seg, iid = _map[company_id]
    return _retry(lambda: _xts.depth(seg, iid))


@app.get("/live/ohlc/{company_id}")
def ohlc(company_id: int, days: int = 120, compression: int = 86400):
    """Historical candles. compression seconds: 86400=1d, 3600=1h, 900=15m."""
    if company_id not in _map:
        raise HTTPException(404, "no XTS mapping")
    seg, iid = _map[company_id]
    end = dt.datetime.now()
    start = end - dt.timedelta(days=days)
    fmt = "%b %d %Y %H%M%S"
    raw = _retry(lambda: _xts.ohlc(seg, iid, start.strftime(fmt), end.strftime(fmt), compression))
    return {"candles": _parse_ohlc(raw)}


@app.get("/news/{company_id}")
def news(company_id: int):
    """Corporate announcements (NSE SME feed) for a company, cached 30 min.
    First call per company does the NSE cookie handshake (~slow); then cached."""
    now = time.time()
    hit = _news_cache.get(company_id)
    if hit and now - hit[0] < NEWS_TTL:
        return {"items": hit[1]}
    with get_engine().connect() as c:
        row = c.execute(text(
            "SELECT nse_symbol FROM companies WHERE company_id = :id"), {"id": company_id}).first()
    items: list[dict] = []
    if row and row[0]:
        global _nse_corp
        try:
            if _nse_corp is None:
                _nse_corp = NSECorpScraper()
            for a in _nse_corp.announcements(row[0])[:25]:
                items.append({
                    "headline": (a.get("headline") or "")[:240],
                    "category": a.get("category"),
                    "pdf_url": a.get("pdf_url"),
                    "at": a.get("announced_at"),
                })
        except Exception as exc:  # noqa: BLE001 — empty feed beats a 500
            log.warning("news %s: %s", company_id, exc)
    _news_cache[company_id] = (now, items)
    return {"items": items}


@app.get("/bulk-deals")
def bulk_deals():
    """Latest-session bulk + block deals, marquee-flagged, with SME-universe
    company_id attached where the symbol is one of ours. Cached 1 hr."""
    global _deals_cache, _nse_corp
    now = time.time()
    if _deals_cache and now - _deals_cache[0] < DEALS_TTL:
        return {"deals": _deals_cache[1]}
    deals: list[dict] = []
    try:
        if _nse_corp is None:
            _nse_corp = NSECorpScraper()
        with get_engine().connect() as c:
            sme = {r[0]: r[1] for r in c.execute(text(
                "SELECT nse_symbol, company_id FROM companies WHERE nse_symbol IS NOT NULL"))}
        for d in _nse_corp.bulk_block_deals():
            d["company_id"] = sme.get(d["symbol"])
            d["in_sme_universe"] = d["company_id"] is not None
            deals.append(d)
    except Exception as exc:  # noqa: BLE001
        log.warning("bulk deals: %s", exc)
    _deals_cache = (now, deals)
    return {"deals": deals}


@app.get("/bulk-deals/{company_id}")
def bulk_deals_for(company_id: int):
    return {"deals": [d for d in bulk_deals()["deals"] if d.get("company_id") == company_id]}


def _parse_ohlc(raw: str) -> list[dict]:
    """XTS dataReponse: bars separated by ',', fields by '|' -> ts|o|h|l|c|v|oi.
    OHLC bar timestamps are already UNIX epoch (unlike quote LastTradedTime)."""
    out: list[dict] = []
    for bar in (raw or "").split(","):
        f = bar.split("|")
        if len(f) >= 6:
            try:
                out.append({
                    "t": int(f[0]),
                    "o": float(f[1]), "h": float(f[2]),
                    "l": float(f[3]), "c": float(f[4]), "v": float(f[5]),
                })
            except ValueError:
                continue
    return out
