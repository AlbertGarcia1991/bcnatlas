# Barcelona Atlas · v1.2.0

Explore Barcelona through municipal open data: stack heatmaps, inspect points, overlay cycling routes and polygons, colour geometry by source attributes, and browse the full dataset catalog.

## Run

Tested on Linux with Node.js 24 and Python 3.12. The Python resource reader uses POSIX process limits; Linux/macOS are supported for the API.

```sh
npm ci
npm run setup:api       # Creates .venv and installs pinned Python dependencies
npm run dev             # Starts local API :8000 and Vite :5173
```

Open **http://localhost:5173**. Dependencies are already installed in this workspace.

If you already have a Vite server running (for example on :4000), it can use the catalog through the configured `/api` proxy. Start the backend separately with `npm start`. `npm run dev:web` starts only Vite.

## Complete catalog coverage

The snapshot of [Open Data BCN](https://opendata-ajuntament.barcelona.cat/data/es/dataset), retrieved on 7 November 2026, contains **558 datasets and 6,825 resources**. All are searchable and linked to their official dataset pages and original downloads. Search matches titles, slugs, categories and tags; filters narrow by geographic metadata and file format.

**Catalog coverage is not the same as verified map compatibility.** 249 datasets are marked geographic by the publisher. 538 datasets offer at least one reader-supported format; actual compatibility is determined when the resource is opened. The other 20 have only specialist/service formats and remain available through their original links. We have not downloaded or verified all 6,825 resources.

| Resource type | Behavior |
| --- | --- |
| CSV | UTF-8/BOM, UTF-16/BOM and CP1252; delimiter detection; known WGS84 and explicit ETRS89/ED50 coordinate columns |
| JSON / GeoJSON | Record arrays, common wrappers, nested dictionary fields, geographic features and declared coordinate reference systems |
| GeoPackage (GPKG) | Selectable vector layers, CRS reprojection to WGS84; raster-only packages are not previewed |
| ZIP / KMZ | Selectable CSV, JSON, GeoJSON, GPKG, KML members; packaged shapefiles via GDAL |
| XLSX | Selectable worksheets and tabular preview |
| XML | Simple repeated-record tables; external entities are disabled |
| KML | Vector geometry through GDAL |
| WMS, WMTS, CAD, standalone SHP/sidecar files, 7z, rasters and other formats | Original-source links; no interactive parser/viewer in this release |

Sources with recognized points can become heatmaps or individual-point layers. Lines and polygons retain their geometry; they are not converted into invented point locations. Numeric source attributes can colour geometry with a labelled min–max scale. Missing attribute values are grey. **Interpret units and category definitions using the original dataset documentation.** Tables containing only district/neighbourhood codes are previewed as tables: no automatic polygon joins or synthetic centroids are created.

The browser displays at most the first 100 table records (20 per page), with search limited to those preview rows. Up to 100 discovered columns are exposed. This is explicitly a preview; the original download provides the full data.

## Using the app

1. Use the three **curated layers** for verified 2023–2025 accident and tree data.
2. Open **Dataset catalog** or **Browse the complete catalog**.
3. Search and select a dataset. Choose its published year and resource, then **Preview resource**.
4. If provided, choose a worksheet, archive member, GPKG layer or year found inside the records.
5. Add supported geographic data to the map. Up to six catalog overlays can be active, alongside curated layers.
6. Use each overlay card to hide/remove it, change point rendering, colour by an attribute, inspect attribution or export GeoJSON.

Catalog overlays have **independent periods**. The bottom timeline controls only curated layers. A resource without a year in its filename remains labelled **Undated / current**; retrieval/publication dates are never substituted for observation years. A filename year is a discovery hint, not proof of a full-year observation period. Record-year filters use recognized year columns (`Any`, `Year`, `NK_Any`, `Any_data`).

District filters apply to curated layers and catalog overlays with recognized district codes. Other overlays remain city-wide and explicitly say so. Clicking the map provides nearby curated counts; clicking a catalog point/line/polygon in geometry view also shows source attributes. The footer’s record counts are for curated layers; catalog feature counts appear in their own cards.

Share URLs preserve curated settings and catalog resource/member/year selections, visibility, metric and rendering style. Reloading a shared catalog view downloads the referenced resources again through the cached API; source availability is required. Camera position is not shared. GeoJSON exports include the selected geometry, applicable district filter and provenance. Curated CSV exports remain separate.

## Data integrity and provenance

Catalog metadata is in `public/data/catalog.json`; curated provenance is in `public/data/manifest.json`. Each resource preview shows its resource ID, source SHA-256, actual download/cache date, original record count, selected record count, mapped count and rejected/missing geometry counts. GeoJSON exports embed publisher, dataset/resource URLs, license, timestamp, checksum and processing notes.

Published sources are attributed to Ajuntament de Barcelona, with the source author/department and original license retained. The CKAN “organization” describes a thematic category, not the publisher. Catalog sources retain their own license metadata; no license is inferred for an unknown resource.

The source defines municipal scope. A broad Barcelona envelope (longitude 2.04–2.24, latitude 41.30–41.49) excludes invalid/outside geometry; it is **not** a municipal-boundary polygon clip. Catalog line/polygon geometry is clipped to that envelope and simplified by 0.00001 degrees (roughly one metre). Geometry is reprojected only when the CRS is declared or explicit coordinate-column names identify it. Unknown projected coordinates are not guessed.

No records are sampled or deduplicated. Multiple source records may refer to the same location or entity; counts indicate records/features, not necessarily unique places. Heatmaps show relative record density, not accident risk, canopy cover or a causal relationship. Colours across layers are not quantitatively comparable. Radius, intensity, zoom and opacity affect appearance.

### Curated snapshots

All nine curated files were imported without coordinate exclusions. Tree datasets are Q4 inventory snapshots; accident datasets cover the calendar year. Each record has equal weight within its layer (0.1 for accidents, 0.025 for dense tree inventories).

| Year | Accident records | Street trees | Park trees |
| --- | ---: | ---: | ---: |
| 2023 | 7,724 | 147,914 | 35,546 |
| 2024 | 7,536 | 146,268 | 34,809 |
| 2025 | 7,741 | 145,706 | 32,776 |

Official datasets: [traffic accidents](https://opendata-ajuntament.barcelona.cat/data/en/dataset/accidents-gu-bcn), [street trees](https://opendata-ajuntament.barcelona.cat/data/en/dataset/arbrat-viari), [park trees](https://opendata-ajuntament.barcelona.cat/data/en/dataset/arbrat-parcs). Curated data is CC BY 4.0, adapted by Barcelona Atlas. Curated data is approximately 13 MiB and loads on demand from the configured datastore.

See [resource-validation.json](docs/resource-validation.json) for the representative live resource checks performed for this release. It is a validation sample, not a claim that every catalog resource has been tested.

## Refresh data

```sh
npm run catalog:refresh # Re-fetch every catalog metadata page, validate pagination, replace snapshot
npm run data:refresh    # Rebuild the original nine curated snapshots
npm test
npm run build
```

Do this as a maintenance/build step, not against an actively served production directory. Restart the production server after deploying a changed catalog/build. In local mode, raw catalog resource downloads live in `.cache/resources/`, keyed by resource ID and modification timestamp. Remove that directory to force fresh downloads when upstream content changes without an updated timestamp. Curated raw downloads live directly in `.cache/` and are also reused until removed. No background recurring refresh is configured.

## R2 data hosting

The workspace is configured through ignored `.env.local` with `BCN_DATA_SOURCE=r2`. Copy `.env.example` for another deployment and provide the S3 endpoint, access key ID and secret on the **server**. Local credentials are loaded from ignored `.env.secrets`; never put credentials in a `VITE_` variable.

- Private raw archive: `bcn-atlas-raw/snapshots/initial-2026-11-07/raw/{dataset}/{resource}/source`.
- Catalog, provenance and nine curated assets: `bcn-atlas-public/app/v1.2.0/data/`.
- Derived previews: `bcn-atlas-public/processed/v2/`, generated on first request and reused until the source ETag or parser version changes.
- The frozen plan contains **6,793 downloadable resources**. Another **32 WMS/WMTS references** are retained as metadata; a service endpoint is not an archive file.

```sh
npm run r2:publish   # Upload assets and verify each with a SHA-256 round trip
npm run r2:verify    # Inventory raw objects; publish status and write missing-only CSV
npm run r2:mirror   # Resume missing resources with bounded retries and a single-job lock
```

Progress and errors are in `.cache/r2-mirror/upload.log`, `mirror-job.json` and `verification.json`. `missing-resources.csv` is the resumable transfer plan. The verifier checks object presence and nonzero size; differences from publisher-declared byte sizes are reported separately, since live sources may have changed. It does not certify that every file can be mapped. Never infer archive completeness from rclone's percentage: that reflects bytes currently discovered, not the entire resource count.

The configured rclone remote is **`bcnatlasCloudflareR2:`**, not `r2:`. The supervisor permits four missing-only passes and records any unresolved source failures instead of reporting success. Rerunning it resumes without overwriting existing objects. Keep the machine awake and connected while it runs. No recurring schedule is installed.

### Optional public domain

Reserve `bcnatlas.com` for the website and connect **`data.bcnatlas.com`** to `bcn-atlas-public` in R2 → Settings → Custom Domains. Set bucket CORS to allow GET/HEAD from `https://bcnatlas.com` and `https://www.bcnatlas.com` (paste the array in `docs/r2-cors.json` into the dashboard CORS editor). The custom domain is connected and serves verified objects. Initial CORS checks allowed all origins, but fresh responses subsequently omitted CORS headers. Direct browser access remains disabled pending a consistent policy for the website origins. Current object-storage credentials do not have bucket-domain/CORS management access. The default same-origin API data route works without either configuration.

After CORS is verified, set `VITE_DATA_BASE_URL=https://data.bcnatlas.com/app/v1.2.0/data` in the production build environment (or ignored `.env.production.local`). Until then, all environments use the working same-origin API route. This is a public URL, not a credential. Keep `bcn-atlas-raw` private. For deployment, run the Python API on a Linux host/container with the pinned dependencies and forward `/api` from the website domain. The website itself has not been deployed by these data migration scripts.

## Backend and operating limits

A small FastAPI service reads catalog-listed resources from R2 (or municipal sources in local mode); this avoids browser CORS restrictions and provides one bounded normalization path. There is no arbitrary URL endpoint: the dataset/resource pair must exist in the catalog. Downloads and redirects must use HTTPS on the official Open Data BCN host. R2 credentials remain exclusively on the API server. In R2 mode, missing objects produce explicit errors without silently falling back to local or municipal downloads.

- Two concurrent parser processes, with 120-second total request timeouts.
- Downloads: up to 64 MiB, up to three attempts with backoff; expanded archives/workbooks: 192 MiB.
- At most 250,000 parsed rows and 150,000 mapped features; processed responses: at most 48 MiB.
- Parser process: 2 GiB address-space limit and 100 seconds of CPU time.
- Unknown structures, missing geolocation, unsupported formats, excessive sizes and source failures produce explicit messages and source links. No fake or silently sampled map substitutes are produced.

The API is intended for a trusted local or privately hosted installation. Before an untrusted public deployment, add access controls/rate limiting, a bounded disk-cache retention policy and reverse-proxy resource controls. In local mode the disk download cache grows as new resources are opened. R2 mode stores derived previews in R2, keyed by raw-object ETag, parser version, archive member and year. No public deployment is configured.

## Verify

```sh
npm test                       # TypeScript helpers, data integrity and Python readers/API tests
npx playwright install chromium
npm run test:e2e                # Curated + catalog workflows, real official resources, mobile QA
npm run build                  # TypeScript check + optimized client output
TEST_PRODUCTION=1 npm run test:e2e # Browser workflows against dist/ (POSIX shell)
npm audit
```

Playwright starts/reuses the backend and frontend independently, and stops servers it owns. Live catalog tests require the selected datastore: mirrored resources in R2 mode, or municipal resources/their local cache in local mode. Screenshots are saved to `test-results/`. Headless Chromium uses software WebGL.

## Production/local preview

```sh
npm run build
npm start
```

Open **http://127.0.0.1:8000**. FastAPI serves both `dist/` and `/api`. `npm run preview` also works while the API is running on port 8000. The production client contains **no datasets**. By default all data uses the same-origin `/api/data` route, which reads R2 server-side. Static hosting requires either `/api` forwarding or an explicitly configured public R2 URL for curated assets; **on-demand resource previews always require the Python API**. Cloudflare Pages alone cannot run this Python/GDAL service.

The standard OpenStreetMap basemap requires internet and has no SLA. Follow its [tile usage policy](https://operations.osmfoundation.org/policies/tiles/): keep attribution/Referer, respect browser caching and do not bulk-download or prefetch. Select a suitable tile provider before high-volume public hosting. Map attribution: © OpenStreetMap contributors. Fonts load from Google Fonts with system fallbacks. Map rendering uses MapLibre GL JS. This is an independent project, not an official municipal service.

## Structure

```text
src/App.tsx                 Curated explorer, catalog selection and share state
src/CatalogExplorer.tsx     Complete catalog, resource selection, table and provenance UI
src/OverlayPanel.tsx        Independent catalog layer controls and exports
src/Map.tsx                 WebGL heatmaps, points, lines, polygons and attribute popups
src/catalog.ts              Catalog contracts, loader and attributed GeoJSON exports
src/data.ts                 Curated configuration and spatial/URL helpers
src/dataSource.ts           Public asset URL configuration
server/storage.py           Server-only R2 reads and derived preview caching
server/app.py               Bounded API and production static hosting
server/worker.py            Isolated resource parser process
server/loader.py            Format readers, coordinate normalization and source caching
scripts/sync_catalog.py     Complete CKAN metadata snapshot
scripts/import_data.py      Curated data ingestion
public/data/                Import/publish inputs (excluded from dist/)
public/static/              Small static client assets
scripts/r2_*.py             Verified asset publishing, mirror inventory and retries
requirements.txt            Pinned API/parser dependencies
```
