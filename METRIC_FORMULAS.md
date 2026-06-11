# Health OS — Metric Formulas, Evidence & Modelling Principles

Last audited: 2026-06-11. This document describes every computed metric, the evidence behind it, and the modelling decisions — including known limitations. Health OS provides lifestyle guidance, not medical advice or diagnosis.

## Modelling principles applied

The system follows six principles after the 2026-06 audit:

**Personal baselines over population norms where the science demands it.** HRV is scored against your own Garmin baseline (balanced range), because between-person HRV differences are largely genetic and absolute thresholds are not interpretable (Plews 2013; Task Force of ESC/NASPE 1996). Population scoring is used only as a fallback when no baseline exists.

**Guideline-anchored targets.** Activity targets follow WHO 2020 physical-activity guidelines exactly: ≥150 min/week moderate activity or ≥75 min/week vigorous, with 1 vigorous minute counted as 2 moderate minutes. The app converts this to a 30-day MVPA-equivalent target of 645 minutes. The previous targets (150 min Zone 1–3 per 30 days) understated WHO by roughly 4× and were corrected.

**Hazard ratios mapped to age-equivalents via Gompertz.** All-cause mortality roughly doubles every 8–10 years of adult age (Gompertz law). A risk factor with hazard ratio HR is therefore equivalent to ln(HR)/ln(2) × ~8–10 years of ageing. The age model uses 10×ln(HR), i.e. a 10-year doubling assumption — conservative within the literature range.

**Caps and saturation everywhere.** Every per-metric age delta is capped (e.g. VO₂max contribution capped at −2/+3 years), the total delta is capped at ±8 years, and nutrient coverage saturates at 100% of RDA (no credit for megadosing). Uncapped linear extrapolation is a classic composite-score failure mode.

**Correlated inputs are not naively summed.** Sleep duration, consistency, score and stages share variance; the ±8y total cap and per-metric caps limit double-counting. This is an acknowledged approximation — a principled fix would require a fitted joint model (see Limitations).

**Missing data is neutral, never penalised.** Any metric without data contributes 0 to the age model and is excluded from domain averages. The app distinguishes "no data" from "bad value" throughout.

## Data sources (verified live 2026-06-11)

| Variable | Garmin endpoint | Status |
|---|---|---|
| Sleep duration/stages/score | get_sleep_data (30 nights) | ✅ |
| Overnight HRV | get_sleep_data top-level `avgOvernightHrv` | ✅ fixed 2026-06-11 (was dropped by a parsing bug) |
| HRV personal baseline | get_hrv_data (weekly avg, balanced range, status) | ✅ added 2026-06-11 |
| Resting HR | get_rhr_day + daily stats | ✅ |
| Body battery + stress drain | get_body_battery (30d, with events) | ✅ |
| Daily steps | get_daily_steps (30d) | ✅ |
| Activities + HR zones | get_activities (100) → server-computed 30d zone minutes | ✅ |
| VO₂max | get_max_metrics scanned over last 30 days (Garmin only writes it on GPS-run days) | ✅ added 2026-06-11 |
| All-day stress (0–100) | get_stats per day (7d) | ✅ added 2026-06-11 |
| Body composition | get_body_composition (90d) | ✅ |
| Nutrition | AI-analysed food log (15 nutrients vs DRI/WHO/EFSA RDAs) | ✅ |

## Scoring functions (0–100)

**HRV** — personal baseline: ≥balanced-upper → 90–100; within balanced range → 70–90 (linear); below balanced-low → 70×(value/low). Fallback (no baseline): linear 25→65 ms. Rationale: HRV-guided training literature uses individual rolling baselines (Kiviniemi 2007; Plews 2013).

**VO₂max** — age-adjusted: norms decline ~0.35 ml/kg/min/year after 25 (ACSM/Cooper data). Score = (value − poor)/(excellent − poor)×100 where poor = 35 − adj, excellent = 53 − adj. Evidence: cardiorespiratory fitness is the strongest single mortality predictor, with no observed upper benefit limit (Mandsager 2018 JAMA; Kodama 2009 JAMA: each 1-MET ≈ 13% mortality difference).

**Resting HR** — linear 55 bpm→100, 85→0. Evidence: +10 bpm RHR ≈ +16% all-cause mortality (Zhang 2016 CMAJ meta-analysis).

**All-day stress** — Garmin 0–100 scale (FirstBeat HRV-derived): score = 110 − 1.3×level. Anchors: 25 ("rest") → 77; 50 → 45; 75 ("high") → 12.

**Sleep duration** — value/8h×100. Target 7–9 h (Watson 2015 AASM/SRS consensus).

**Sleep consistency** — 100 − 0.67×SD(bedtime minutes), computed in local time (UTC bug fixed 2026-06-11). Evidence: sleep irregularity predicts metabolic syndrome and CVD independent of duration (Huang 2020 JACC); regularity outpredicts duration for mortality (Windred 2024 Sleep).

**Sleep stages** — min(50, deep%/18×50) + min(50, rem%/22×50), each component capped. Targets: deep ≥15–20%, REM ≥20–25% of night.

**Aerobic zones** — MVPA-equivalent = Zone1–3 minutes + 2×Zone4–5 minutes over 30 days; score = eq/645×100 capped at 100 (WHO 2020).

**Strength** — ≥60 min/30d → 95; ≥30 → 75; ≥15 → 50; else 25. Evidence: 30–60 min/week resistance training → 10–17% lower all-cause mortality, J-shaped curve (Momma 2022 BJSM).

**Lean mass %** — (value − 55)/25×100 for men. Evidence: muscle mass independently predicts survival (Srikanthan 2014).

**Nutrient coverage** — 7-day mean daily intake / RDA ×100, capped at 100. RDAs from NIH DRI / WHO / EFSA tables.

## Healthspan age model

Chronological age + Σ capped per-metric deltas (total capped ±8y). Deltas (years):

| Metric | Rule | Evidence anchor |
|---|---|---|
| Sleep duration | <7h: 10·ln(1.12)·(7−h), capped 3.5 | HR ≈1.12 per lost hour vs 7h reference (Cappuccio 2010 meta) |
| Sleep consistency | ≥70: −1.4; 50–70: +1.8; <50: +3.9 | Irregularity HRs 1.2–1.5 (Huang 2020; Windred 2024) |
| Steps | <8k: 10·ln(1.20)·(deficit/1000)·0.7, cap 3.5 | Paluch 2022 Lancet pooled dose-response |
| Aerobic (WHO-eq) | ≥645: −0.5; 320–645: +0.3; <320: +1.2 | WHO 2020; Arem 2015 |
| Vigorous | ≥300/30d: −0.4; ≥120: 0; else +0.6 | Vigorous activity adds benefit beyond moderate (Gebel 2015) |
| Strength | ≥60: −0.7 … <15: +1.13 | Momma 2022 |
| VO₂max | (42 − value)×0.3, capped [−2, +3] | Mandsager 2018; Kodama 2009 |
| Resting HR | ≤55: −0.6 … >70: (RHR−70)/5×0.9 | Zhang 2016 |
| Lean mass | ≥75%: −0.3; 70–75: +0.2; <70: +0.8 | Srikanthan 2014 |

Pace of aging = 1 + (total delta)/10, floored at 0.4. This is a display heuristic, not a validated biological-age clock (see Limitations).

## Domain scores and nutrition blending

Each of 15 health systems averages the 0–100 scores of its mapped metrics (mapping table in METRIC_REGISTRY). Where ≥1 day of analysed food logs exists in the past 7 days, the Garmin-derived score is blended with a nutrition score: final = Garmin×(1−w) + nutrition×w, where w = 0.15–0.35 per domain (inflammation and bone highest, sleep lowest). The nutrient→domain weight matrix encodes consensus nutrition science (e.g. magnesium → stress/sleep/muscle; omega-3 → cardiac/cognitive/inflammation). These weights are expert priors, not fitted parameters — they are documented, fixed, and auditable rather than estimated from this n=1 dataset, which would overfit.

## Known limitations (honest list)

Wrist-derived sleep staging agrees with polysomnography only ~69–88% per epoch; REM detection is weakest — stage-based scores inherit this noise. Garmin HRV/stress/body-battery are proprietary FirstBeat algorithms; they are internally consistent but not interchangeable with chest-strap RMSSD. The healthspan age is a transparent heuristic composite, not a validated clock (unlike PhenoAge/DunedinPACE, which are fitted to biomarker/mortality data); treat trends as meaningful and absolute values as illustrative. Hazard ratios borrowed from cohort studies are population averages applied to n=1 — individual causal effects will differ. Correlated metrics are handled by capping, not joint modelling. Nutrition values are LLM estimates with ±30–50% typical error on micronutrients; coverage below 70% should be read as "probably low", not as measured deficiency. The recommendation engine is rule-based with citation anchors; rules fire on thresholds, not individualized causal inference.
