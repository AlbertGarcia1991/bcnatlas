# Publish Barcelona Atlas on Cloudflare from GitHub

The complete application uses **Cloudflare Workers with static assets, Cloudflare Containers, and the existing R2 buckets**. Create a **Worker**, not a Pages project. This supersedes the earlier Pages-only frontend recommendation and avoids needing another hosting provider for Python/GDAL.

```text
GitHub main → Workers Builds → bcnatlas.com
                              ├─ /                  React/static assets
                              ├─ /api/data/*        R2 binding (no browser CORS)
                              └─ /api/resource/*    Python container → R2 raw + processed data
```

The data files stay in R2. Secrets never enter GitHub, the frontend build, or the Docker image. The existing `data.bcnatlas.com` can remain attached to R2, but this deployment does not depend on its CORS policy.

## 1. Enable the required Cloudflare plan

Use the Cloudflare account containing `bcnatlas.com`, `bcn-atlas-raw` and `bcn-atlas-public`. Enable the **Workers Paid plan** and Containers in that account if prompted. Containers require paid Workers: currently a $5/month base subscription plus usage beyond included allowances. This is separate from purchasing the domain. See [current pricing](https://developers.cloudflare.com/containers/platform/pricing/).

The configuration caps the API at **one `standard-1` container**, runs one parser at a time, and sleeps the container after five idle minutes. This limits concurrency, not total spending. First previews after idle can take longer while the container starts. The frontend and curated layers do not wake it. Sustained traffic can incur additional charges; check Workers/Containers usage in the dashboard.

## 2. Confirm GitHub has the deployment files

Open `AlbertGarcia1991/bcnatlas`, branch `main`. Confirm these files exist:

- `wrangler.jsonc`
- `Dockerfile` and `.dockerignore`
- `cloudflare/index.ts` and `cloudflare/router.ts`
- `.github/workflows/checks.yml`

Open the repository's **Actions** tab. Enable Actions if the repository asks, and check the latest **Check application** run. It runs unit tests, builds the frontend/Worker, validates the Worker bundle, builds the Docker image, and checks container startup. Optional local dataset integrity tests are skipped on a fresh checkout because dataset files are deliberately excluded from Git.

## 3. Connect GitHub to Cloudflare Workers

1. Open Cloudflare → **Workers & Pages** → **Create application**.
2. Choose the Git repository / **Import a repository** option for **Workers**. Do not choose Pages or upload static assets manually.
3. Connect GitHub and authorize the Cloudflare GitHub application for **only `AlbertGarcia1991/bcnatlas`**, unless you deliberately want broader access.
4. Select that repository and configure:

| Setting | Value |
| --- | --- |
| Worker/project name | `bcnatlas` — must match `wrangler.jsonc` |
| Production branch | `main` |
| Root directory | Repository root (`/` or leave empty) |
| Build command | `npm run build:cloudflare` |
| Deploy command | `npm run deploy:cloudflare` |
| Build variable | `NODE_VERSION=22` |
| Non-production branch builds | Disable initially |

There is no Pages “build output directory” field to configure here. `wrangler.jsonc` already selects `dist/`. Leave the default automatic dependency installation enabled. Do not set `NODE_ENV=production` during dependency installation; the build needs development dependencies. Do not add any `VITE_*` credentials or public-data URL override: the Cloudflare build uses `/api/data` on the website's own origin.

5. Save and deploy. Cloudflare's automatically generated **Workers Builds deployment token** is separate from your R2 object-storage credentials. Do not substitute the R2 token for it.
6. Wait for the deployment and container-image build to finish. Docker builds run inside Workers Builds; Docker does not need to run on your laptop for this path. On first deployment container provisioning can take several additional minutes.

At this point the homepage and curated layers can load using the R2 binding. Catalog previews deliberately return a configuration error until step 4 is complete. If a build fails, inspect its log rather than changing the deployment command to a static-only upload.

## 4. Add the three runtime secrets

Open **Workers & Pages → bcnatlas → Settings → Variables and Secrets**. Add these as **Secret** values, using the existing values in your local `.env.secrets`:

| Runtime secret name | Local value to copy |
| --- | --- |
| `CLOUDFLARE_R2_S3_ENDPOINT` | The full `https://…r2.cloudflarestorage.com` endpoint |
| `CLOUDFLARE_R2_ACCESS_KEY_ID` | Existing R2 access key ID |
| `CLOUDFLARE_R2_ACCESS_KEY_SECRET` | Existing R2 secret access key |

Save/deploy the secret changes. These belong in **runtime Variables and Secrets**, not **Build variables and secrets**. The separate `CLOUDFLARE_R2_TOKEN` is not used by this application.

The S3 credentials must read `bcn-atlas-raw` and read/write `bcn-atlas-public` (write access stores derived previews). The currently working upload credentials already have object access. The Worker passes only these server settings to the container at runtime.

The following nonsecret settings and bindings are managed by `wrangler.jsonc`; do not duplicate or rename them in the dashboard:

- `PUBLIC_DATA` → existing `bcn-atlas-public` bucket.
- `ATLAS_API` → the container Durable Object.
- `PREVIEW_LIMITER` → 30 preview/readiness requests per IP per minute, enforced locally by Cloudflare's rate limiter.
- `BCN_R2_APP_PREFIX=app/v1.2.0` and `BCN_R2_RAW_PREFIX=snapshots/initial-2026-11-07`.
- Both bucket-name variables.

## 5. Verify the workers.dev deployment

Open the Worker URL shown in the dashboard (`https://bcnatlas.<your-workers-subdomain>.workers.dev`). Check:

1. The map loads, the 2025 accident layer shows 7,741 records, and changing years works.
2. `/api/health` returns JSON identifying `bcnatlas-edge`.
3. `/api/data/manifest.json` and `/api/data/catalog.json` return JSON, not the homepage HTML.
4. `/api/ready` returns `status: ok`, `dataSource: r2`, and `datasets: 558`. This wakes the container and verifies its catalog access. If it initially returns 503, wait for provisioning and retry.
5. In **Dataset catalog**, search `sanitat-farmacies`, preview it and add it to the map. This checks raw-data reads, the Python parser, and processed-preview storage.
6. Open `/api/data/mirror-status.json` for archive availability. Uploading the application does not finish the separate bulk archive transfer; missing resources remain explicitly marked until mirrored.

## 6. Attach bcnatlas.com

In **Workers & Pages → bcnatlas → Settings → Domains & Routes**, choose **Add → Custom Domain**:

1. Add `bcnatlas.com`.
2. Add `www.bcnatlas.com` if you want both addresses to serve the app.
3. Confirm the DNS/certificate changes Cloudflare presents and wait for the domain status to become active.
4. Repeat the map, catalog preview, and `/api/ready` checks at `https://bcnatlas.com`.

Do not attach `data.bcnatlas.com` to this Worker; it remains the R2 domain. The repository deliberately omits `routes` from Wrangler configuration so custom domains can be managed in the dashboard. If an existing DNS record or Pages project owns the apex/www hostname, resolve that specific conflict before attaching it; leave unrelated DNS records intact.

## 7. Future releases

Push application changes to `main`; Cloudflare builds and deploys them automatically. A change to the Python code also builds and rolls out the container image. The GitHub Actions checks and Workers Builds are separate systems: a successful frontend build does not prove the live container is ready, so check `/api/ready` and a real preview after each release.

Keep non-production branch builds disabled for this initial setup. Containers/Durable Objects do not provide ordinary full-app version preview URLs; use a separately configured staging Worker for isolated deployment testing. Do not use a feature-branch full deploy against the production Worker.

Data refreshes are separate from code deployments. Use the existing catalog/import and R2 publishing scripts to publish a consistent snapshot, then update the configured prefixes when intentionally promoting a new snapshot. This release does not install a recurring import job or a public refresh endpoint.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Build cannot find Worker | Project name must be `bcnatlas`, root must be the repository root |
| R2 binding error | Both buckets must exist in the same account as the Worker |
| Missing backend configuration | Add the three runtime secrets and deploy the changes |
| `/api/health` works, `/api/ready` fails | Container provisioning, runtime secrets, object permissions and container logs |
| One preview reports missing resource | Check mirror status; that raw file may still be pending |
| 429 | Wait a minute; preview request rate limit was reached |
| Busy/503 preview | Another parser is active, or the container is starting; retry shortly |
| Unsupported/oversized resource | Existing preview limits apply; the official source download remains linked |
| Container build error | Read Workers Builds Docker output; do not publish only `dist/` as a workaround |
| Secret rotation has not taken effect | Stop the running instance in the Containers dashboard, then let the next request restart it with current secrets |

Local validation commands:

```sh
npm ci
npm run setup:api
npm test
npm run build:cloudflare
npm run check:deploy
# With a running Docker engine:
docker build -t bcnatlas-api:check .
```

`check:deploy` validates the Worker/assets bundle with `--dry-run --containers-rollout=none`; it does not build, deploy or validate the container image. The Docker check in GitHub Actions covers image build/startup. Local live-data/browser tests additionally require your ignored `.env.local`/`.env.secrets` and the R2 snapshots.

References: [Workers Builds](https://developers.cloudflare.com/workers/ci-cd/builds/), [container deployment from Git](https://developers.cloudflare.com/containers/guides/deploy/), [custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/), [container pricing](https://developers.cloudflare.com/containers/platform/pricing/).
