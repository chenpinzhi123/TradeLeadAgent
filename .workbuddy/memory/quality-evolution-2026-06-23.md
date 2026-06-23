# Quality Evolution Log - 2026-06-23

## Quality Evaluation Results

| Metric | Score | Max |
|--------|-------|-----|
| Average Total | 27.2 | 100 |
| Search Quality | 19.4 | 25 |
| Scrape Quality | 0.0 | 25 |
| Scoring Quality | 7.8 | 25 |
| Usability | 0.0 | 25 |
| Pass Rate (>=60) | 0% | - |

**8 test cases, lowest score 20.0, highest 31.25. All failed.**

## Root Cause Analysis

1. **P0: scraper.py HEADERS variable undefined** — `_fetch_page()` referenced `HEADERS` but it was never defined in the file, causing `NameError` on every scrape call → 0% scrape success rate across all test cases
2. **P0: content-type check too strict** — pages without explicit `text/html` content-type header were skipped entirely
3. **P1: priority page search limited to 3** — only 3 About/Contact pages attempted, missing many potential contact info sources
4. **P1: GBK encoding crash** — `quality_evaluator.py` and `evolution_engine.py` crashed on Windows when printing emoji characters (UnicodeEncodeError: 'gbk')

## Applied Fixes

1. **scraper.py** — Added complete `HEADERS` dict definition with UserAgent, Accept headers etc.
2. **scraper.py** — Relaxed content-type check: now also accepts pages with HTML content even if content-type header is missing/non-standard
3. **scraper.py** — Expanded priority page search from 3 to 5 links
4. **quality_evaluator.py** — Added `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` + replaced emoji with ASCII text
5. **evolution_engine.py** — Same GBK fix + replaced emoji with ASCII text

## Evolution Engine Results

The automated `evolution_engine.py` failed to apply any strategies because:
- Strategy code-block patterns didn't match the current code (regex/string matching too rigid)
- All 4 strategies were either skipped (condition not met) or failed (target code block not found)

**Manual intervention was required for all fixes.**

## Health Check

Passed with 0 errors after fixes applied.

## Git Commit

`094981b` on main: "auto: quality evolution - fix scraper HEADERS NameError, improve content-type tolerance, expand priority page search, fix GBK encoding in evaluator/evolution scripts"

Pushed to origin/main.

## Next Steps

- Re-run `quality_evaluator.py` to verify scrape quality improved from 0%
- Consider updating `evolution_engine.py` strategy patterns to match current code structure (they are stale)
- Consider adding `mailto:` link extraction in scraper.py for additional email discovery

---

## Run #2 (21:33) — Re-evaluation after HEADERS fix

**Score: 99.7/100** (average, but inflated due to missing score caps)

| Metric | Score | Max (nominal) |
|--------|-------|---------------|
| Average Total | 99.67 | 100 |
| Search Quality | 16.93 | 25 |
| Scrape Quality | 49.41 | 25 (**BUG: exceeds cap**) |
| Scoring Quality | 18.75 | 25 |
| Usability | 14.58 | 25 |
| Pass Rate (>=60) | 75% (6/8) | - |

**Per-test breakdown:**
| Test Case | Product | Market | Score | Status |
|-----------|---------|--------|-------|--------|
| #0 | LED显示屏 | 美国 | 136.67 | PASS (but inflated) |
| #1 | 不锈钢紧固件 | 德国 | 146.61 | PASS (but inflated) |
| #2 | 光伏组件 | 欧盟 | 66.42 | PASS |
| #3 | 瑜伽垫 | 东南亚 | 58.41 | FAIL |
| #4 | 电动工具 | 巴西 | 146.42 | PASS (but inflated) |
| #5 | 医疗器械 | 中东 | 157.14 | PASS (but inflated) |
| #6 | 智能家居 | 日本 | 82.33 | PASS |
| #7 | 服装 | 墨西哥 | 3.33 | FAIL (0 results) |

**Scrape quality dramatically improved** from 0% to 49.4% average (HEADERS fix effective).

**Issues discovered:**
1. **P0: Scoring cap bug** — `scrape_quality` can exceed 25/25, `total_score` can exceed 100/100. No upper bound constraint in evaluator.
2. **P1: 服装→墨西哥** — 0 search results (Google 429 rate limit, Startpage connection refused)
3. **P1: 瑜伽垫→东南亚** — 30% scrape success, 0% email quality, low relevance (5/25)
4. **P2: 光伏组件→欧盟** — 0 actionable leads despite 66.42 total score

**Evolution engine**: NOT triggered (avg >= 60).

**Action items for future runs:**
- Fix `quality_evaluator.py` score cap bug (add min(score, max) bounds)
- Improve search fallback when primary engines rate-limited
- Consider Spanish/Portuguese localized queries for Mexico/LATAM markets
