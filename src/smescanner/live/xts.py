"""
XTS **market-data** client — read-only.

Deliberately scoped to the market-data REST API only: login with an appKey +
secretKey, then pull live quotes (LTP/OHLC), 5-level market depth, and historical
candles for charts. It NEVER touches the interactive/trading API — no orders, no
positions, no funds. Credentials come from the environment (`SME_XTS_*`), never
hard-coded, so secrets stay out of the repo.

Works against any Symphony-XTS deployment (Share India, Symphony developers, etc.)
— only the root URL changes. xtsMessageCode reference:
  1501 touchline (LTP, OHLC, %chg, volume) · 1502 market depth (5 bid/ask levels)
  1505 candle · 1510 open interest · 1512 LTP-only
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

import requests

# XTS timestamps are seconds since 1980-01-01; add this to get a UNIX epoch.
XTS_EPOCH_OFFSET = 315532800

log = logging.getLogger("smescanner.live.xts")

# Symphony XTS numeric exchange segments.
SEGMENT = {
    "NSECM": 1, "NSEFO": 2, "NSECD": 3,
    "BSECM": 11, "BSEFO": 12,
    "MCXFO": 51, "NSECO": 13,
}


class XTSError(RuntimeError):
    pass


class XTSMarketData:
    def __init__(
        self,
        app_key: str | None = None,
        secret_key: str | None = None,
        root: str | None = None,
        source: str = "WEBAPI",
    ) -> None:
        self.app_key = app_key or os.getenv("SME_XTS_APP_KEY", "")
        self.secret = secret_key or os.getenv("SME_XTS_SECRET_KEY", "")
        self.root = (root or os.getenv("SME_XTS_ROOT", "https://developers.symphonyfintech.in")).rstrip("/")
        self.source = source or os.getenv("SME_XTS_SOURCE", "WEBAPI")
        self.token: str | None = None
        self.user_id: str | None = None
        self.s = requests.Session()
        self.s.headers["Content-Type"] = "application/json"

    # -- auth --------------------------------------------------------------
    def login(self) -> dict:
        if not self.app_key or not self.secret:
            raise XTSError("XTS market-data appKey/secretKey not set (SME_XTS_APP_KEY / SME_XTS_SECRET_KEY)")
        r = self.s.post(
            f"{self.root}/apimarketdata/auth/login",
            json={"appKey": self.app_key, "secretKey": self.secret, "source": self.source},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("type") != "success":
            raise XTSError(f"XTS login failed: {data}")
        res = data["result"]
        self.token = res["token"]
        self.user_id = res.get("userID")
        self.s.headers["authorization"] = self.token
        log.info("XTS market-data login ok (user=%s)", self.user_id)
        return res

    def _ensure(self) -> None:
        if not self.token:
            self.login()

    # -- quotes / depth ----------------------------------------------------
    def quotes(self, instruments: Iterable[tuple[str | int, int]], code: int = 1501) -> dict:
        """instruments: iterable of (segment, exchangeInstrumentID).
        Returns the parsed `result` (quotes list under `listQuotes`)."""
        self._ensure()
        instr = [
            {
                "exchangeSegment": SEGMENT.get(seg, seg) if isinstance(seg, str) else seg,
                "exchangeInstrumentID": int(iid),
            }
            for seg, iid in instruments
        ]
        r = self.s.post(
            f"{self.root}/apimarketdata/instruments/quotes",
            json={"instruments": instr, "xtsMessageCode": code, "publishFormat": "JSON"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("result", {})

    def touchline(self, instruments: Iterable[tuple[str | int, int]]) -> dict[int, dict]:
        """Clean LTP/OHLC/%chg/volume/best-bid-ask keyed by instrumentID.

        The 1501 response carries these at the top level of each quote (NOT under
        a nested 'Touchline' key), so we flatten to a stable shape for the UI."""
        res = self.quotes(instruments, code=1501)
        out: dict[int, dict] = {}
        for q in res.get("listQuotes", []):
            d = json.loads(q)
            bid, ask = d.get("BidInfo") or {}, d.get("AskInfo") or {}
            out[d["ExchangeInstrumentID"]] = {
                "ltp": d.get("LastTradedPrice"),
                "pct_change": d.get("PercentChange"),
                "open": d.get("Open"), "high": d.get("High"),
                "low": d.get("Low"), "close": d.get("Close"),
                "volume": d.get("TotalTradedQuantity"),
                "bid": bid.get("Price"), "bid_qty": bid.get("Size"),
                "ask": ask.get("Price"), "ask_qty": ask.get("Size"),
                "last_trade_unix": (d.get("LastTradedTime", 0) or 0) + XTS_EPOCH_OFFSET,
            }
        return out

    def depth(self, segment: str | int, instrument_id: int) -> dict:
        """5-level market depth for one instrument.

        The 1502 response carries top-level ``Bids`` / ``Asks`` arrays (each
        level: Size, Price, TotalOrders), with LTP under ``Touchline``."""
        res = self.quotes([(segment, instrument_id)], code=1502)
        lq = res.get("listQuotes", [])
        if not lq:
            return {"bids": [], "asks": [], "ltp": None}
        d = json.loads(lq[0])

        def levels(arr):
            return [{"price": lvl.get("Price"), "qty": lvl.get("Size"),
                     "orders": lvl.get("TotalOrders")} for lvl in (arr or [])]

        tl = d.get("Touchline") or {}
        return {
            "bids": levels(d.get("Bids")),
            "asks": levels(d.get("Asks")),
            "ltp": tl.get("LastTradedPrice"),
        }

    # -- historical candles (charts) --------------------------------------
    def ohlc(self, segment: str | int, instrument_id: int, start: str, end: str,
             compression: int = 60) -> str:
        """start/end format: 'MMM DD YYYY HHMMSS' (XTS convention).
        compression: seconds per candle (60=1m, 900=15m, 3600=1h, 86400=1d).
        Returns the raw `dataReponse` string (comma/pipe rows) for the caller to parse."""
        self._ensure()
        params = {
            "exchangeSegment": SEGMENT.get(segment, segment) if isinstance(segment, str) else segment,
            "exchangeInstrumentID": instrument_id,
            "startTime": start,
            "endTime": end,
            "compressionValue": compression,
        }
        r = self.s.get(f"{self.root}/apimarketdata/instruments/ohlc", params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("result", {}).get("dataReponse", "")

    # -- instrument master (symbol -> instrumentID mapping) ---------------
    def master(self, segments: Iterable[str] = ("NSECM", "BSECM")) -> str:
        """Returns the raw pipe-delimited master dump. Parse with parse_master()."""
        self._ensure()
        r = self.s.post(
            f"{self.root}/apimarketdata/instruments/master",
            json={"exchangeSegmentList": list(segments)},
            timeout=90,
        )
        r.raise_for_status()
        return r.json().get("result", "")


def parse_master(raw: str) -> list[dict]:
    """Parse the XTS master dump into rows.

    Each line is pipe-delimited; the leading columns are stable across XTS:
      ExchangeSegment | ExchangeInstrumentID | InstrumentType | Name |
      Description | Series | NameWithSeries | ...
    We keep what we need to map our SME universe (symbol/series -> instrumentID).
    SME equity lives in NSECM series SM/ST and BSECM groups M/MT/MS.
    """
    rows: list[dict] = []
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 7:
            continue
        rows.append({
            "segment": parts[0].strip(),
            "instrument_id": parts[1].strip(),
            "instrument_type": parts[2].strip(),
            "name": parts[3].strip(),
            "description": parts[4].strip(),
            "series": parts[5].strip(),
            "name_with_series": parts[6].strip(),
        })
    return rows
