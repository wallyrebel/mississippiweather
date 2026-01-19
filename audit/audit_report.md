# Mississippi Weather Desk — Audit Report (2026-01-19)

## 1) Executive Summary (5–10 bullets)
- PASS/FAIL A (required sections, order, non-empty): NO — sections are not enforced and a sample output lacks required headings.
- PASS/FAIL B (all 8 regions + 82 counties): NO — 82 counties exist, but required region names are NW/NE/SW while config uses “Northwest/Northeast/Southwest,” so output will not match required names.
- PASS/FAIL C (includes active NWS watches/warnings/advisories): NO — there is no dedicated “Watches/Warnings” section in prompt or fallback.
- PASS/FAIL D (avoid brittle HTML scraping): YES — uses official JSON/APIs and NOAA MapServer endpoints, no scraping.
- PASS/FAIL E (schedules 3x/day America/Chicago): NO — GitHub Actions cron is fixed UTC and does not adjust for CDT; no gating logic in code.
- Email content contract relies entirely on LLM compliance; parser does not validate required headings or non-empty sections.
- Fallback article structure does not match required sections and omits “Watches/Warnings.”
- County coverage exists (82 counties across 8 configured regions), but required region labels do not match mandated abbreviations.

## 2) System Overview (inferred architecture + ASCII data-flow diagram)
- Orchestrator: run_once() in src/run.py loads env, calls build_briefing() → generate_article() → send_email().
- Data fetchers: NWS alerts + gridpoint forecast (src/fetch_nws.py); SPC outlooks (src/fetch_spc.py); WPC ERO (src/fetch_wpc.py); NHC storms (src/fetch_nhc.py).
- Geospatial intersection: county polygons/centroids in src/geo.py using data/ms_counties.geojson and config/ms_counties.json.
- LLM generation + parsing: src/llm.py.
- Email rendering + SMTP send: src/emailer.py.

ASCII data flow:
NWS/NOAA/NHC APIs
   |        |         |
   v        v         v
[fetch_nws] [fetch_spc] [fetch_wpc] [fetch_nhc]
          \      |        /
           v     v       v
        [geo intersections]
               |
               v
         [analyze.build_briefing]
               |
               v
           [llm.generate_article]
               |
               v
        [emailer.send_email (HTML+text)]

## 3) Data Sources & Endpoints (list all endpoints/file feeds used; confirm “no keys” for gov sources except OpenAI)
- NWS API (no key):
  - Alerts: https://api.weather.gov/alerts/active?area=MS in fetch_active_alerts() in src/fetch_nws.py.
  - Points: https://api.weather.gov/points/{lat},{lon} in get_point_metadata() in src/fetch_nws.py.
  - Forecast: forecastUrl from NWS points metadata in fetch_grid_forecast() in src/fetch_nws.py.
  - Grid data: forecastGridDataUrl from NWS points metadata in fetch_grid_forecast() in src/fetch_nws.py.
- SPC MapServer (no key): https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/SPC_wx_outlks/MapServer in fetch_spc_layer() in src/fetch_spc.py.
- WPC MapServer (no key): https://mapservices.weather.noaa.gov/vector/rest/services/outlooks/wpc_qpf/MapServer in fetch_ero_layer() in src/fetch_wpc.py.
- NHC Current Storms JSON (no key): https://www.nhc.noaa.gov/CurrentStorms.json in fetch_tropical_systems() in src/fetch_nhc.py.
- OpenAI (key required): OPENAI_API_KEY used in get_client() in src/llm.py.
- SMTP (credentials required): SMTP_* and EMAIL_* in get_smtp_config() in src/emailer.py.

## 4) Email Output Contract Verification (MANDATORY)
- Exact template/renderer used:
  - HTML renderer: build_html_email() → markdown_to_html() in src/emailer.py.
  - Plain-text renderer: build_plain_text_email() in src/emailer.py.
  - Article generation: build_llm_prompt() + generate_article() + parse_article_response() in src/llm.py.

Required sections verification (order + non-empty + statewide/8-region coverage):
1) Current Conditions
   - Code location: build_llm_prompt() instructs “## Current Conditions” in src/llm.py.
   - Data source: regional_summaries from fetch_anchor_forecasts() → NWS gridpoint forecasts in build_briefing() in src/analyze.py and src/fetch_nws.py.
   - Non-empty proof: NOT VERIFIED. No validation of presence or non-empty content in parse_article_response() in src/llm.py. Sample output lacks this section: test_output.txt.
   - Statewide/8-region proof: NOT VERIFIED (LLM instruction only, no enforcement).
2) Today’s Forecast
   - Code location: build_llm_prompt() includes “## Today’s Forecast” in src/llm.py.
   - Data source: NWS gridpoint forecast periods via fetch_grid_forecast() in src/fetch_nws.py.
   - Non-empty proof: NOT VERIFIED; sample output does not include this section.
3) 3-Day Outlook
   - Code location: build_llm_prompt() includes “## 3-Day Outlook” in src/llm.py.
   - Data source: extract_daily_forecasts() from NWS periods in src/analyze.py.
   - Non-empty proof: NOT VERIFIED; sample output lacks this section.
4) 7-Day Forecast
   - Code location: build_llm_prompt() includes “## 7-Day Forecast” in src/llm.py.
   - Data source: extract_daily_forecasts() from NWS periods in src/analyze.py.
   - Non-empty proof: NOT VERIFIED; no enforcement in parser; sample output lacks this section.
5) Regional Details
   - Code location: build_llm_prompt() includes “## Regional Details” in src/llm.py.
   - Data source: build_regional_summaries() and anchor forecasts in src/analyze.py and src/fetch_nws.py.
   - Non-empty proof: PARTIAL — fallback output contains “## By Region” but not the required heading or order (test_output.txt).
6) Watches/Warnings (active NWS watches/warnings/advisories)
   - Code location: NO dedicated section in prompt or fallback. Evidence: build_llm_prompt() and generate_fallback_article() in src/llm.py.
   - Data source available: fetch_active_alerts() → alerts in build_briefing() in src/fetch_nws.py and src/analyze.py.
   - Non-empty proof: NOT VERIFIED and not required by prompt.
   - Result: ❌ BLOCKER.

Section order and headings stability:
- NOT VERIFIED. Order is only implied in prompt; parse_article_response() does not validate headers or section sequence in src/llm.py.

Example output snippet (artifact):
- Sample output in test_output.txt contains “## Overview” and “## By Region,” which does not match the required six sections or ordering.

## 5) Mississippi Coverage Verification
- 82 counties present: VERIFIED by config (count=82) in config/ms_counties.json.
- 8 regions present: VERIFIED (count=8) in config/ms_counties.json and config/anchors.json.
- Each region has at least one county: VERIFIED by counts (e.g., “Gulf Coast East: 2”) in config/ms_counties.json.
- Required region names (NW/NE/Delta/Central/Pine Belt/SW/Gulf Coast West/Gulf Coast East): NOT VERIFIED — config uses “Northwest/Northeast/Southwest,” not the mandated abbreviations.

## 6) Correctness Checks
- NWS: User-Agent present, retries, timeouts, and rate limiting
  - User-Agent: USER_AGENT in src/fetch_nws.py.
  - Retries: Retry(total=3, backoff_factor=1, status_forcelist=...) in get_session() in src/fetch_nws.py.
  - Timeouts: timeout=30 in NWS requests in src/fetch_nws.py.
  - Rate limiting: REQUEST_DELAY = 1.0 and time.sleep() usage in src/fetch_nws.py.
- Alerts: grouping, timing, official vs guidance labeling
  - Grouping by event: group_alerts_by_type() in src/fetch_nws.py.
  - Timing captured but not surfaced in output: onset/expires parsed into Alert but not enforced in LLM prompt (src/fetch_nws.py, src/llm.py).
  - Official vs guidance separation: instruction only in SYSTEM_PROMPT, not validated (src/llm.py).
- SPC/WPC: layer selection, CRS handling, intersections, edge cases
  - Layer selection: fixed layer IDs for SPC; discovery for WPC (src/fetch_spc.py, src/fetch_wpc.py).
  - CRS handling: no explicit CRS transformation for MapServer geometries before Shapely intersection (src/geo.py).
  - Edge cases: if Shapely missing, fallback to centroid point-in-polygon (less accurate) (src/geo.py).
- NHC: inclusion criteria and MS relevance
  - Uses distance threshold (400 miles) and includes up to 600 miles if distance known (src/fetch_nhc.py).

## 7) Reliability & Failure Modes
- Partial failures: each source fetch is wrapped in try/except and adds to data_gaps (src/analyze.py).
- LLM failure: fallback content generated by generate_fallback_article() in src/llm.py.
- SMTP failure: send_email() returns False with error logging; no retry (src/emailer.py).
- “Data gaps” path: HTML email includes a “Data Gaps” block if data_gaps is non-empty (src/emailer.py).

## 8) Scheduling & Timezone (America/Chicago)
- Scheduled 3x/day in GitHub Actions via UTC cron (12:30, 19:30, 02:30) in .github/workflows/weather.yml.
- DST drift risk: comments acknowledge CST/CDT mismatch but cron is fixed UTC; no gating logic in runtime to adjust (weather.yml, src/analyze.py).
- Intended local times (6:30am, 1:30pm, 8:30pm CT) are not guaranteed during CDT.

## 9) Security & Secrets
- Secrets are loaded from environment in production and GitHub Actions secrets (src/run.py, src/llm.py, src/emailer.py, .github/workflows/weather.yml).
- No keys required for government sources (fetchers).

## 10) Test Coverage & Gaps
- Present tests: geospatial point-in-polygon and region grouping, SPC parsing, NWS grouping (tests/test_geo.py, tests/test_spc.py, tests/test_nws.py).
- Missing tests: LLM prompt compliance, email section order, region label requirements, watches/warnings section, scheduling correctness, data-gaps email rendering.

## 11) Findings Table (MANDATORY)
| ID | Severity | Area | Evidence (file path + function) | Why it matters | Recommendation |
|---|---|---|---|---|---|
| F-001 | BLOCKER | Email Output Contract | src/llm.py build_llm_prompt(), generate_fallback_article(); test_output.txt | Required sections are not enforced; sample output lacks mandated headings and order. | Add explicit post-generation validation and regenerate or fallback to a compliant template. |
| F-002 | BLOCKER | Watches/Warnings Section | src/llm.py build_llm_prompt() | No dedicated “Watches/Warnings” section in prompt or fallback. | Add required section and populate with NWS alerts. |
| F-003 | BLOCKER | Region Naming Compliance | config/ms_counties.json, config/anchors.json | Required region labels are NW/NE/SW; config uses “Northwest/Northeast/Southwest.” | Normalize region labels to required names in output contract. |
| F-004 | MAJOR | Scheduling/DST Accuracy | .github/workflows/weather.yml | Fixed UTC cron leads to incorrect local send times during CDT. | Add DST-aware scheduling or runtime gating against America/Chicago local time. |
| F-005 | MAJOR | Section Non-Empty Guarantee | src/llm.py parse_article_response() | No validation that each required section is non-empty or present. | Enforce section presence and minimum content length. |
| F-006 | MINOR | CRS Handling for GIS Intersections | src/geo.py intersect_counties_with_polygon_shapely() | Potential CRS mismatch risk with MapServer geometries; centroid fallback can under/overcount. | Document CRS assumptions and validate geometries or reproject. |

## 12) Recommended Next Steps (prioritized, minimal changes only)
1) Enforce the six required sections (headings + order + non-empty) in a deterministic renderer; use LLM only for prose within each section.
2) Add a mandatory “Watches/Warnings” section populated from NWS alerts and ensure statewide coverage.
3) Normalize region labels to required names (NW, NE, SW) in outputs while retaining internal canonical names if needed.
4) Make scheduling DST-safe via UTC cron adjustments or runtime gating to only send at 6:30am/1:30pm/8:30pm America/Chicago.
5) Add tests that validate required section order, non-empty content, region coverage, and alert inclusion.
