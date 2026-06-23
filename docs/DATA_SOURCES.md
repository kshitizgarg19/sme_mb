# Data Collection Plan

Free sources first. Every source below is documented with **method · anti-bot ·
rate limits · fallback**, matching the brief. All requests pass through
`common/http.py`, which centralises politeness so individual scrapers stay thin.

> **Legality / ToS.** This scanner consumes *publicly disclosed* regulatory data
> (exchange filings, SEBI disclosures, statutory annual reports). Respect each
> site's `robots.txt` and Terms of Use, throttle conservatively (defaults below),
> cache aggressively, and never resell raw third-party data. Screener/Tickertape/
> Trendlyne content is for personal research use — we read public pages only and
> avoid authenticated export endpoints. For anything ambiguous, prefer the
> primary exchange/regulator source.

---

## A. Universe (which stocks exist)

### A1. NSE Emerge
- **Method.** Primary: parse the **daily SME bhavcopy** (zip→CSV) — ground truth
  for every symbol that traded. Union the last 3–5 sessions to catch illiquid
  names. Fallback: the **SME Emerge index constituents** JSON
  (`/api/equity-stockIndices?index=NIFTY SME EMERGE`).
- **Anti-bot.** NSE is behind Akamai. `NSEClient` first GETs the homepage +
  market-data landing page to seed cookies, then calls `/api/*` with a matching
  `Referer` and `X-Requested-With: XMLHttpRequest`. On 401/403 it rotates the
  user-agent, clears cookies and re-bootstraps.
- **Rate limits.** ~0.4 req/s per host (see `HostRateLimiter` overrides) +
  0.4–1.4 s jitter. Stay well under ~1 req/s sustained.
- **Fallback.** Bhavcopy archive → index endpoint → last-known universe in
  `companies` (so a bad NSE day reuses yesterday's list).

### A2. BSE SME
- **Method.** `BSEClient` → `ListofScripData/w` (segment=Equity, status=Active),
  filtered client-side to SME (group M/MT/XT or SME instrument flag). The numeric
  `scripcode` is the canonical join key for all other BSE feeds.
- **Anti-bot.** `api.bseindia.com` needs `Origin`/`Referer = www.bseindia.com`
  and a browser UA; no cookie handshake. Gentle pacing avoids throttling.
- **Rate limits.** ~0.5 req/s per host + jitter.
- **Fallback.** Published "List of Scrips" master CSV on the BSE site.

---

## B. Fundamentals (financials, balance sheet, cash flow)

### B1. Screener.in  *(primary)*
- **Method.** HTML GET `company/<SYMBOL>/consolidated/`; each statement is a
  `<section id="profit-loss|balance-sheet|cash-flow|quarters">` table parsed with
  pandas. Standalone path used when consolidated is absent.
- **Anti-bot.** Light. Real UA + ~3 s spacing. We use only public pages, never
  the logged-in Excel export, to respect ToS.
- **Rate limits.** ~0.33 req/s (1 company / 3 s). A full ~1,200-name universe ≈
  60–70 min; run nightly. Cache pages for 12 h.
- **Fallback.** On 404, retry with BSE `scripcode` path. If Screener is
  unreachable, fall back to **BSE financial-results feed** (B2) and **annual
  report PDF extraction** (C2) for the core P&L/BS lines.

### B2. BSE / NSE financial results  *(cross-check & fallback)*
- **Method.** BSE `CompanySearchData/w` and NSE corporate financial-results
  endpoints, keyed on scripcode/symbol.
- **Anti-bot / rate limits.** As A1/A2.
- **Fallback.** Each other; then PDF extraction from the result filing.

### B3. Paid (optional drop-in)
- Tickertape / Trendlyne / Tijori APIs or a vendor like Sensibull/Refinitiv.
  Same scraper interface, swapped behind a feature flag. Use when you need
  guaranteed SLAs or restated/standardised history.

---

## C. Disclosures & qualitative

### C1. Corporate announcements
- **NSE** `/api/corporate-announcements?index=equities&symbol=…`;
  **BSE** `AnnGetData/w` (date-windowed, returns PDF attachment names).
- **Method.** Pull the rolling window daily, classify headline → category
  (result / order-win / capex / rating / board-meeting), store PDF URL.
- **Anti-bot / rate limits.** Per exchange (A1/A2). Download PDFs lazily.
- **Fallback.** The two exchanges mirror most filings — if one feed misses, the
  other usually has it.

### C2. Annual reports / investor presentations / concalls
- **Method.** Discover PDF links from the announcement feed and the company's
  Investor-Relations page; download to `data/reports/`; extract MD&A/Directors'
  Report text with `pdfplumber`; structure with the local LLM
  (`ai/report_reader.py`) into segments / capex / moat / concentration / exports.
- **Anti-bot.** Company sites vary; standard UA + retries. Many IR pages are
  static PDFs — trivial.
- **Rate limits.** A handful per company per year; download off-peak.
- **Fallback.** BSE/NSE attachment mirror → exchange "Annual Reports" section →
  skip (business-quality score then leans on financial proxies only).

### C3. Shareholding pattern & promoter pledge
- **Method.** NSE `/api/corporate-shareholdings-patterns`, BSE
  `ShpPromoterNGroup/w`. Quarterly promoter %, pledge %, FII/DII/public.
- **Anti-bot / rate limits.** Per exchange.
- **Fallback.** Screener's shareholding section; the pledge disclosure in the
  announcement feed (PIT/SAST).

### C4. Insider / promoter trades (SEBI PIT, SAST)
- **Method.** NSE `/api/corporates-pit` → `insider_trades` (buy/sell/pledge,
  promoter flag, qty, value). Aggregate to a 12-month promoter net-buy used by
  the management score.
- **Fallback.** BSE insider-trading feed; SEBI's own disclosure pages.

### C5. Bulk & block deals  *(marquee-investor tracker)*
- **Method.** NSE `/api/historical/bulk-deals` (date-windowed), BSE bulk/block
  feed. Client names matched against a curated **marquee investor** list
  (Jhunjhunwala, Kedia, Kacholia, Mukul Agrawal, Dolly Khanna, …) → flagged in
  the dashboard.
- **Fallback.** Each exchange; Trendlyne/Chittorgarh aggregations.

### C6. Corporate actions (bonus / split / rights / pref / QIP / buyback)
- **Method.** NSE/BSE corporate-action feeds + **Chittorgarh** (excellent SME IPO
  & rights/pref coverage). Rights/pref/QIP flagged `is_dilutive` → feeds the
  "serial dilution" management penalty.
- **Fallback.** Announcement-feed parsing.

### C7. Credit ratings
- **Method.** Rating-agency sites (CRISIL/ICRA/CARE/India Ratings/Acuité)
  publish press releases; also surfaced in the announcement feed. Capture
  agency/instrument/rating/outlook/action.
- **Fallback.** Announcement feed → Trendlyne ratings aggregation.

### C8. MCA filings  *(where legally accessible)*
- **Method.** MCA21 "View Public Documents" is paywalled per-document; use only
  where you have a legitimate need and pay the statutory fee. Treated as an
  **optional manual enrichment**, not an automated scrape.
- **Fallback.** Statutory annual report (C2) carries most of the same financials.

---

## D. Prices (for valuation & backtest)

- **Method.** Daily close + market cap from the **exchange bhavcopy** (SME
  segment) — authoritative and free. For names with a Yahoo ticker, `yfinance`
  is a convenience fallback, but SME history there is sparse/unreliable, so
  bhavcopy is primary.
- **Backtest note.** Point-in-time prices are stored in `prices`; the backtest
  reads them with a filing-date lag so scores never use unpublished statements.

---

## Politeness defaults (global)

| Knob | Default | Where |
|------|--------:|-------|
| Per-host rate | 0.33–0.5 req/s | `HostRateLimiter._overrides` |
| Jitter | 0.4–1.4 s | `PoliteSession.jitter` |
| Retries | 4, backoff×1.5 | `PoliteSession` (urllib3 Retry) |
| Cache TTL | 12 h | `config.cache_ttl_hours` |
| UA rotation | per session, on block | `PoliteSession.rotate_identity` |

**Escalation order when a host hardens:** slow the rate → rotate UA + clear
cookies → add a residential/rotating proxy (set `HTTPS_PROXY`) → switch to the
documented fallback source. Endpoints marked `# VERIFY` in code should be
confirmed against the live site on first run; the fallback chain means a single
renamed path degrades coverage rather than breaking the pipeline.
