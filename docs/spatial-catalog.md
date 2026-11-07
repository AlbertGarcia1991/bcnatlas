# Spatial catalog and municipal joins

The map uses source coordinates/geometry first, then exact municipal references.
The publisher's `geographic` flag is not a reliable exclusion rule: many statistical
tables marked non-geographic have valid district, neighbourhood or census codes.

## Supported location references

| Location | Representation |
| --- | --- |
| District code/name | Official polygon, 10 districts |
| Neighbourhood code/name | Union of current official census polygons, 73 neighbourhoods |
| District + census-section code | Official polygon, 1,068 sections; section IDs are scoped to district |
| AEB code | Official polygon, 233 statistical areas |
| Street code or unambiguous official/short name | Lines connecting official road-graph nodes, 4,034 streets |
| Street and postal number/letter, or full street address | Exact unambiguous municipal address point; 171,708 matches |
| Postal code | Official address points covered by that postcode, not a guessed boundary or individual observations |
| Traffic-count site ID | Join `aforaments-detall` to the official `aforaments-descriptiu` locations |
| Weather-station code | Join `mesures-estacions-meteorologiques` to the official station metadata |

Sources: [administrative boundaries](https://opendata-ajuntament.barcelona.cat/data/en/dataset/20170706-districtes-barris),
[postal addresses](https://opendata-ajuntament.barcelona.cat/data/en/dataset/taula-direle),
[street names](https://opendata-ajuntament.barcelona.cat/data/en/dataset/carrerer),
[road graph](https://opendata-ajuntament.barcelona.cat/data/en/dataset/mapa-graf-viari-carrers-wms),
[traffic-count sites](https://opendata-ajuntament.barcelona.cat/data/en/dataset/aforaments-descriptiu),
[weather stations](https://opendata-ajuntament.barcelona.cat/data/en/dataset/metadades-estacions-meteorologiques).
Attribution: Ajuntament de Barcelona, CC BY 4.0. Source file checksums are embedded
in the reference bundle and exported GeoJSON provenance.

The versioned reference lives in the public bucket at
`references/spatial-v2.json.gz`; it is read server-side, not downloaded on page load.
`npm run spatial:build` rebuilds it from cached inputs or their R2 originals.
Publish with `.venv/bin/python -m scripts.build_spatial_reference --publish` only
after validation. A reference refresh must use a new `SPATIAL_REFERENCE_KEY`;
that key participates in the processed-preview cache identity. The application
release is 1.3.0; the existing curated data snapshot prefix remains `app/v1.2.0`.

## Record selection and aggregation

Choose a record year and category filters before adding an overlay. Filters are
exact-value matches, validated by the API, and preserved in share URLs, exports
and the R2 processed-cache identity. Categories with more than 40 distinct values
are not offered as dropdowns. At most 12 category filters may be submitted.

Native source geometry keeps one feature per source row. Reference joins create
one feature per matched location. Repeated matched rows use the arithmetic mean
of numeric fields and `_records` counts the matched rows. This is deliberately
labelled; it is not an inferred sum, weighted rate or population total. The table
preview retains original rows and values. Filter categories before interpreting
means across demographic groups or measurement types.

Current boundaries and station locations are used for historical observations;
historical boundary reconstruction is not provided. Exact unmatched or ambiguous
locations are counted and omitted. No third-party bulk geocoder, approximate
address matching, postcode hulls or artificial area centroids are used.

## Curation and storage removal

`config/catalog-exclusions.json` is the reviewed removal list, with the inspected
resource and fields for each decision. `config/catalog-spatial-evidence.json`
records schema evidence. `scripts/curate_catalog.py` applies the exclusions on
every catalog refresh. Uninspected resources remain stored; they are not treated
as proven non-spatial. The browser withholds datasets without any identified
location field or spatial metadata.

On 7 November 2026, 36 datasets / 296 resource references were excluded and 223
existing raw objects were removed. The retained catalog has 522 datasets / 6,529
resources, including 32 service references. The mirror plan has 6,497 downloads.
The map-candidate count is computed from the retained catalog, not hardcoded.

To inspect future cleanup: `.venv/bin/python -m scripts.prune_nonspatial`.
Stop this project's mirror supervisor **and its active rclone transfer** before
using `--apply`. The script takes the mirror lock, updates the transfer plan and
both catalogs, deletes only exact reviewed dataset prefixes and resource caches,
then verifies that no excluded objects remain. The machine-local result is
`.cache/r2-mirror/nonspatial-removal-result.json`. Metadata is retained for an
audit; excluded raw source files are not backed up into another bucket.

## Remaining coverage limits

This is broad location support, not a claim that all municipal files are map-ready.
Some sources remain unmirrored, unavailable or require dedicated schemas, foreign
key joins, service viewers or specialist readers. Unstructured place descriptions
cannot always be matched. Existing download, row, feature, memory and response
limits still apply. The catalog distinguishes spatial candidates from proven
successful previews; failed probes never authorize deletion.
