# Shared map timeline

Every enabled layer follows the year at the bottom of the map. Layer cards retain breakdown, worksheet, category and style controls, but no separate year selectors. The catalog's preview-year selectors remain inspection tools: adding a preview to the map applies the shared map year.

## Dates and coverage

- Verified years inside the records take precedence over years in filenames.
- An all-years audit preview is not an undated edition when the same worksheet has verified dated cases.
- Filename years apply when no record-year cases exist.
- Current / undated resources are assigned to **2026** for navigation. Their original undated provenance remains visible; this is not an inferred observation date.
- Coverage is scoped to the chosen dataset breakdown and worksheet, using the existing rendering audit allowlist. The compact curated snapshots cover 2023–2025; verified catalog editions extend their range.
- The timeline includes every intervening year through 2026, including gaps. Its range is the union of active layer coverage. Hidden layers do not contribute.

Blue filled dots indicate all active layers have a verified edition, gold dots indicate partial coverage, and red outlined dots indicate no coverage. Selection has a separate navy ring. Counts, tooltips and a missing-layer list provide the same information in text. Coverage describes available editions, not whether a category filter returns any rows or whether a network request succeeds.

## Switching years

Missing layers stay enabled but are hidden, never carried forward from another year. They return when a covered year is selected. While an edition loads, the old edition is hidden. Year-dependent replacement requests are cancelled on subsequent year changes and stale responses cannot replace current state. A failed load offers a retry without disabling the layer.

Category filters and compatible colour attributes/render modes survive year changes. The shared URL includes the global year and layer selections; restoration reapplies the timeline to every layer. Cached old data is retained only to identify the active layer and its settings; it is not rendered or offered for export as the selected year.

## Validation

Unit checks cover record-year precedence, all-years previews, undated assignment, filename dates, missing-year gaps, partial coverage and stale edition matching. Browser checks cover real annual data, shared URLs, current-only layers, mixed coverage, absent years, mobile overflow and source dialogs outside the curated snapshot range.

Prepared snapshot fallback: when a raw annual file did not pass the audit, the timeline can return an unfiltered traffic layer (or a Q4 tree series) to its existing 2023–2025 prepared snapshot. The card identifies this as a curated snapshot. A snapshot is never substituted for another quarter or for an active category-filter selection, since those filters cannot be applied to the compact snapshot. Its presentation uses the shared curated appearance controls.
