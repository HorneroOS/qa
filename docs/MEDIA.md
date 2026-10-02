# Certified media

Hornero QA is the source of product screenshots for the website. A picture
is publishable only when a passing run produced it and its provenance says
which composition it shows.

## Rules

- Only screenshots named in a scenario's `media:` list are candidates.
- Only bundles whose `result.json` verdict is `pass` are exported.
- Every frame carries a `hornero.qa.screenshot/1` sidecar (run id,
  scenario, product SHAs, environment, SHA-256); export re-hashes the file
  and refuses a mismatch.
- The website consumes media **at build time** from a committed export.
  Pages never fetch from QA runs or this repository at runtime.

## Export

```sh
uv run hornero-qa media export \
  ~/.local/share/hornero/qa/runs/<passing-run> [...] \
  --out ../website/src/assets/certified
```

Output:

```text
<out>/
  manifest.json                       hornero.qa.media/1: file, sha256, scenario, run_id, product
  <scenario-id>/<media-name>.png
  <scenario-id>/<media-name>.json     original screenshot sidecar
```

The website can then show provenance next to an image ("Hornero shell
`25d2206`, config `dae2255`, Hornero QA run …") and its build can fail when a
file's hash does not match the manifest.
