# Analytics release · 7 November 2026

Evidence release: `analytics/v1-20261107-a1`. Generated 2026-11-07T18:33:40.054823+00:00. Open [the dashboard](https://bcnatlas.com/?view=analytics).

## Coverage

- 284 retained map datasets, 2,194 audited resources and 2,285 member/year editions; no extraction failures. Nine prepared accident/tree snapshots supply supplementary density variables.
- 31,193 field appearances screened and 82,624 distinct area/year/category measurements retained in the full inventory.
- 43,496 nonconstant measurements meet comparison coverage; 22,717,222 cross-layer comparisons were computed.
- 5,236,664 eligible neighbourhood comparisons received 9,999 Moran spectral randomizations and one global Benjamini–Yekutieli correction.
- **0 comparisons meet q ≤ 0.05.** Strong descriptive associations exist, but none passes this release's spatial test plus full-family correction. This is not evidence that all relationships are absent: the broad search, dependent measures, conservative adjustment and finite p-value resolution limit power.

Coverage is conditional on usable geography, dates and numeric semantics. Identifiers, constants and unsupported numeric codes are not silently treated as outcomes. Sparse strata and excluded/descriptive variables are documented in the downloadable ledger; this is not a claim that every source column has a scientifically validated interpretation.

## Worked examples: 2023 neighbourhood income

These four interpretable examples were chosen to address the greenery question and illustrate sensitivity, not selected as confirmed discoveries. Income is the within-neighbourhood median of source census-section disposable-income-per-capita values. All pairs have 73 matched neighbourhoods.

| Compared with income | Spearman ρ | Pearson r | District-adjusted rank association | Spatial p | Global BY q |
| --- | ---: | ---: | ---: | ---: | ---: |
| Recorded park trees / km² | 0.122 | -0.023 | 0.129 | 0.2173 | 1.0000 |
| Recorded street trees / km² | 0.051 | 0.011 | 0.169 | 0.7448 | 1.0000 |
| Recorded accidents / km² | 0.410 | 0.281 | 0.341 | 0.0345 | 1.0000 |
| Average dwelling floor area | 0.746 | 0.870 | 0.490 | 0.0002 | 0.1282 |

Park-tree and street-tree density show weak rank associations with income. These inventories measure recorded trees per municipal boundary area, not canopy cover or access to green space; the results cannot establish whether greenery affects income.

Average dwelling floor area has a stronger positive association with income, which attenuates after district adjustment. This is an exploratory area-level pattern, consistent with several possible mechanisms including residential sorting; the data and analysis do not identify a causal mechanism. The accident-density association also does not measure individual accident risk, because exposure is not in its denominator.

The dashboard exposes every eligible pair through measure selectors, while its ranked preview shows up to 200 comparisons per cohort. Additional block-bootstrap and leave-one-area-out diagnostics are limited to the leading 12 inferential pairs per cohort and explicitly marked unavailable elsewhere. See [methods and limitations](analytics-methodology.md), [spatial simulation checks](analytics-validation.json) and [independent bundle validation](analytics-bundle-validation.json).

## Verification

The release passed 37 frontend/edge unit tests, 60 Python tests, all 20 browser tests, the production build and the Worker deployment dry run. A separate browser check used the real evidence bundle to exercise linked charts, CSV export, descriptive district/undated cohorts, the source ledger and mobile layout. Statistical validation includes numerical invariants, known-signal/negative-control tests and 1,000 spatial null simulations; it is not external validation of each municipal measure.
