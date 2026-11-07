# Barcelona Atlas Analytics

This is an exploratory, observational analysis of cross-layer associations. It does not estimate the causal effect of greenery, income, services or any other city characteristic. Statistical support is conditional on a specified spatial null model and is not external validation.

## Scope and reproducibility

The input is the existing map-render audit allowlist, not an arbitrary subset of convenient datasets. Every approved resource/member/record-year edition is screened. All-year previews are omitted when dated versions of that member exist, avoiding duplicate pooled observations. Prepared 2023–2025 accident and tree snapshots provide supplementary count-density variables. Tree density is not canopy cover.

Run the existing map audit first to materialize the versioned catalog, municipal geographic reference and prepared payloads under `.cache/map-audit`. Configure R2 credentials as documented in the project's storage setup; raw rows are fetched only when needed to undo the map preview's mixed-category averages. Credentials are never included in the evidence bundle.

```sh
.venv/bin/pip install -r requirements-analytics.txt
npm run analytics:extract
npm run analytics:build
.venv/bin/python -m scripts.analytics.verify
npm test
npm run analytics:publish
```

The extraction and analysis commands are resumable. The analysis checks the variable identity set before reusing period checkpoints. Changes to the statistical algorithm require invalidating the relevant `.cache/analytics/pairs-*.json` checkpoints. The production application only reads versioned derived assets; it does not run expensive model searches on user requests.

`config/analytics-release.json` pins the public R2 object prefix. Publish to a new prefix for future releases. The publisher sends the manifest last. The edge serves a strict allowlist of files from that prefix. Public files include:

- `manifest.json`: coverage, test-family size, settings, source snapshot hashes, areas and processing outcomes.
- `variables/<period>-<area-level>.json`: the complete usable measurement catalog for that cohort.
- `variables.json.gz`: all screened area measurements with source links, hashes, aggregation, values and counts. Only comparison-eligible variables have a pairwise index; constant/sparse measurements retain their screening metadata.
- `variable-inventory.json.gz`: every source field, its assigned role and edition processing outcomes, including excluded variables.
- `pairs/<period>-<area-level>-<partition>.json`: every computed cross-layer comparison, partitioned by the lower variable index modulo 32.
- `top-associations.json`: a navigation preview of at most 200 comparisons per cohort, not the scope of the statistical search.
- `diagnostics.json`: additional sensitivity checks for the 12 leading inferential comparisons in each cohort.

Pair rows have the schema: X index, Y index, matched-area count, Spearman rho, Pearson r, covariate-adjusted rank association, spatial p-value, global BY-adjusted q-value. Indexes refer to the measurement files. Null p/q means inference was not performed, not that a result passed.

## Measurement construction

1. **Field inventory.** Coordinates, contact details, identifiers, processing metadata and time axes are not quantitative outcomes. Constant or insufficiently numeric fields are recorded in the inventory. Numeric codes without a validated interpretation remain descriptive. Wide numeric year columns are reshaped to year-specific measurements.
2. **Unmixing categories.** The map reader may average multiple source rows at one location. Analytics returns to the original rows, verifies the source hash, and constructs category-specific strata. Unresolved coded dimensions prevent inferential eligibility. No total is fabricated by adding overlapping demographic categories.
3. **Area values.** The common units are 73 neighbourhoods or 10 districts, using the versioned municipal reference. Numeric observations become medians within each area and source stratum. Thus the income example is a median of source census-section income values, not a population-weighted resident mean. A district-only statistic remains a district observation; it is never copied into its constituent neighbourhoods.
4. **Point inventories.** Mapped source features are counted per municipal boundary area in square kilometres. Nominal categories can become within-inventory percentages. Counts describe records, not necessarily unique facilities, completeness of service provision or exposure-adjusted risk. Category shares are compositional; shared denominators and overlapping source records can create mechanical correlations across layers.
5. **Geometry.** Source codes take priority. Valid point locations or lower-level municipal references can be assigned to neighbourhoods. Non-point geometry without validated common geographic support is assigned by representative point for descriptive summaries only and does not receive inferential tests. Historical observations use the current reference boundaries; this is a limitation of the snapshot.
6. **Dates.** Record years take precedence over filename years; explicit wide-year columns carry their own dates. Undated sources are never treated as measured in 2026 simply because the map uses that navigation label. They form a separate descriptive cohort.
7. **Missingness and coverage.** Missing measurements remain null. No measurement imputation is performed. Selective missingness can bias the complete-case associations. A zero inventory count means no mapped records in that area, not proof of absence. Sparse strata, constants and exact duplicate variable vectors are screened and counted. Usable comparisons require at least 30 neighbourhoods or eight districts; inferential eligibility additionally requires five distinct values, a known year and validated geographic/measurement support.

## Association and spatial inference

Spearman rank correlation is the primary effect measure. Pearson correlation is a linear-association sensitivity check. Pairwise complete areas are used, and the matched-area count is always reported. The pair family excludes within-dataset comparisons and prepared/raw versions of the same dataset, reducing trivial self-comparisons.

An ordinary correlation p-value would assume exchangeable observations, which adjacent city areas often are not. The primary p-value instead uses **Moran spectral randomization**, following [Wagner & Dray (2015)](https://doi.org/10.1111/2041-210X.12407). A symmetric binary five-nearest-neighbour matrix is built from projected area centroids, on the complete-case subset. Its full centred eigensystem defines the spatial basis. The singleton procedure flips spectral coefficient signs while preserving the ranked variable's norm and Moran quadratic form. The observed absolute rank correlation is compared with 9,999 such randomizations; `(exceedances + 1) / 10,000` is reported. The deterministic seed is recorded in the run manifest.

This is a conditional spatial-spectrum null model. It does not prove independence from all spatial processes, remove unmeasured confounding, or establish causality. The choice of graph, area scale and missing-area subset matters. The finite randomization count limits p-value resolution to 0.0001; conservative adjustment can make the search underpowered for isolated effects.

All eligible cross-layer spatial tests across all years belong to **one testing family**. The [Benjamini–Yekutieli adjustment](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html) is applied to that family, allowing dependence among tests. The displayed support threshold is q ≤ 0.05. Failure to meet it is not proof of no relationship. District-level comparisons have only ten possible observations and remain descriptive.

## Sensitivity checks

- Rank association after district fixed effects, adding population-density rank only where a matching-year measure with complete covariate coverage is available. This is a sensitivity statistic, not an adjusted causal effect or an additional significance claim.
- For the leading 12 eligible comparisons per cohort, a 1,999-replicate district-block percentile bootstrap and leave-one-area-out Spearman range.
- Moran's I on each ranked variable for those same leading comparisons.

The bootstrap has at most ten district blocks and assumes sufficient independence across those blocks. Its intervals are exploratory, not simultaneous, and are not corrected for selecting leading comparisons. All other comparisons explicitly show diagnostics as not estimated. These limitations are displayed in the dashboard.

## Validation

The test suite compares rank correlation against SciPy with ties; verifies surrogate mean, variance and Moran-energy preservation; checks randomization symmetry, reproducibility, bounds, a known signal and an independent negative control; verifies district adjustment and block intervals; and prevents district totals from becoming artificial neighbourhood observations. Browser tests exercise navigation, source/error states, downloads, mobile layout and restoration from a shared Analytics URL.

The statistical and data-construction code is available under `scripts/analytics`. The complete raw measurement semantics cannot be inferred from numeric appearance alone: codebook-dependent or geometrically ambiguous variables are explicitly withheld from inference rather than presented as validated findings.

The deterministic spatial negative-control experiment is recorded in [analytics-validation.json](analytics-validation.json): 60 of 1,000 independently generated spatial pairs crossed the nominal 5% threshold (exact 95% binomial interval 4.61%–7.66%). That interval includes 5%; it supports this particular simulation check, not universal calibration on every municipal variable. The experiment also verifies preservation of the chosen spatial invariants to numerical precision. Reproduce with `.venv/bin/python -m scripts.analytics.validate`.

The completed bundle is also checked independently by `scripts.analytics.verify`: every comparison is checked for index, sample-size and probability integrity, family totals are reconciled, and a deterministic sample from every partition is recomputed against SciPy. [analytics-bundle-validation.json](analytics-bundle-validation.json) records the result, manifest hash, analysis-code hashes and geographic-reference hash.
