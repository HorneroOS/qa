# Web lane

Browser journeys and product-truth checks for the public site
(<https://website-zcra.vercel.app> by default). Runs in Chromium through
Playwright, an optional dependency group:

```sh
uv run --group web hornero-qa web                      # every journey in web/journeys/
uv run --group web hornero-qa web site-health --base http://127.0.0.1:4321
```

Chromium comes from `$HORNERO_QA_CHROMIUM` or the Playwright browser
cache (`~/.cache/ms-playwright/chromium-*`); QUIC is disabled because it
fails on some networks. Evidence lands in the same bundles as VM runs
(`lane: web` in `run.json`), with a full-page screenshot of every failing
page.

## Journeys (`web/journeys/*.yaml`)

| Key | Meaning |
| --- | --- |
| `pages` | `sitemap` (every page in `/sitemap-index.xml`) or a list of paths |
| `viewports` | `phone` (390x844), `desktop` (1366x860) |
| `checks` | `status` (HTTP < 400), `third_party` (no request to another host), `console` (no console or page errors), `overflow` (no sideways scroll) |
| `steps` | `visit`, `click: {role, name, exact}`, `expect_url`, `expect_text` |
| `truth` | named product-truth checks (below) |

## Product-truth checks

They compare the site with the product repositories' current `main`, so a
stale site fails instead of drifting quietly:

| Check | Fails when |
| --- | --- |
| `layouts_match_shell_main` | `/layouts` does not list exactly the presets in HorneroOS/shell `presets/` |
| `themes_match_config_main` | `/themes` does not list exactly the packs in HorneroOS/config `profiles/themes/` |
| `latest_tag_matches_hornero` | "Latest tagged" on `/releases` is not the newest `v*-previewN` tag of HorneroOS/hornero |
| `no_download_claims` | `/install` links to an image (`.iso`, `.img`, `.qcow2`) |

Set `GITHUB_TOKEN` to avoid the anonymous API rate limit.

## First findings (2026-10-02)

`site-health` caught two docs pages scrolling sideways on phones (inline
code with long paths), fixed in HorneroOS/website#21.
