# Changelog

## Cloudflare deployment support — 2026-11-07

- Add GitHub-connected Workers deployment with static assets, same-origin R2 reads and a Python/GDAL container.
- Add preview rate limits, bounded parser admission, readiness checks and a container image excluding local secrets/data.
- Add GitHub checks for clean-checkout tests, frontend/Worker builds and container startup.
- Document paid-plan activation, runtime secrets, custom domains and end-to-end verification.


## 1.2.0 — 2026-11-07

- Read catalog, curated snapshots and raw resources from Cloudflare R2 with server-only credentials.
- Cache derived previews in R2 by source ETag and parser/member/year identity.
- Exclude datasets from the frontend build; support a public data domain or same-origin API reads.
- Add verified asset publication, resumable raw-mirror retries and explicit inventory reports.
- Preserve municipal attribution and source checksums; missing mirrored resources show a clear error.

## 1.1.0 — 2026-11-07

- Index the entire municipal catalog: 558 datasets and 6,825 resources, with search, geography/format filters and source links.
- Add on-demand CSV, JSON/GeoJSON, GPKG, ZIP, KMZ, KML, XML and XLSX readers, with CRS conversion, archive/layer/sheet selection and actual record-year filters.
- Add up to six independent catalog overlays: point heatmaps, individual points, source lines and polygons, numeric attribute colouring, source-property popups and attributed GeoJSON export.
- Preserve independent periods, unknown-year labels and source licenses; keep non-geographic resources as tables and specialist formats linked to source.
- Persist catalog selections in share URLs and restore them on reload.
- Add a bounded local Python API, download caching, retries, parser isolation, size/time limits and complete catalog refresh tooling.
- Extend tests to cover readers, provenance, source limits, projections, full catalog integrity, desktop/mobile workflows, tables, exports and restoration.

## 1.0.0 — 2026-11-07

Initial release with three Open Data BCN datasets and nine 2023–2025 snapshots, layered WebGL heatmaps, point views, district filters, nearby record inspection, shareable filters, CSV export, source attribution, responsive controls and a reproducible importer.
