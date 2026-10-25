# Studio acceptance evidence gate

`studio-acceptance.yaml` is QA's evidence index for Studio promotion decisions.
It links each required outcome to its issue owners, fixture decision, evidence
bundles, status, and human review. The canonical edition catalogue and release
checklist remain owned by Hornero; QA reports evidence and never changes product
maturity or publishes a Preview claim.

Run the local gate with:

```sh
uv run hornero-qa studio-gate
```

The command returns a failing exit code while any required item is pending,
partial, unsupported, failed, missing evidence, or lacks an owner-approved
fixture and human review. An accepted item needs a complete PASS bundle under
the QA state `runs/` directory. The bundle must match the reviewed scenario
digest, contain valid action/assertion records and nonempty logs, and include
PNG screenshots with matching `hornero.qa.screenshot/1` sidecars and content
hashes. The runner also hashes the exact QCOW2 image bytes before each set of
repeated attempts and records that digest in `run.json`; the acceptance pins
must include the same `image_sha256`. Every other product pin must be present
in the runner's copied `product` metadata. The current image builder does not
produce all Studio pins. Until
that producer contract lands, owners can declare pins on an adopted image
with `hornero-qa image adopt ... --product KEY=VALUE`; the gate does not infer
values from labels, environment descriptions, or branch names.

For bundle evidence, fixture approval includes a stable fixture ID, a
relative path, and the SHA256 of its owner-reviewed fixture manifest. The
gate reads that file, rejects unsafe paths and duplicate YAML keys, validates
its schema and ID, and checks its content hash. The run must declare the same
fixture ID and hash. This verifies the recorded fixture specification, but
does not independently observe the physical hardware or installed software.
Review evidence must link to a HorneroOS pull request, matching the accepted
human review reference; the gate does not query GitHub to validate the PR or
its reviews.

Before adding an accepted bundle to the index, compute its deterministic content
digest with `uv run hornero-qa studio-gate --bundle-digest <run-id>` (use
`--runs-dir` for an archived evidence directory). Add the printed SHA256 as
`bundle_sha256` beside that bundle's `run_id`. The digest covers every regular
file by relative path and content, including screenshots, sidecars, logs,
actions, assertions, scenario, run metadata, and result. The gate rejects a
missing digest, changed file, or symlink found in the bundle. The digest lets a
reviewer compare the bundle with the expected bytes recorded in the current
index. Reviewers must inspect the exact index commit and evidence together; the
gate does not verify which index revision was reviewed. The digest is not a
signature and does not authenticate who produced the bundle.

The gate validates that bundle files are present and internally consistent;
it does not authenticate them. `image adopt --product` records operator
declarations and does not prove that an image contains the declared commits
or catalogue. Screenshot sidecars and logs are not signed. Owners must inspect
the referenced evidence and verify its relevance to the outcome before
accepting review. `eligible_for_owner_review` only reports readiness for that
manual inspection. It is not a release or edition promotion decision.

Numeric performance thresholds stay disabled until QA and product owners
review the fixture, kernel/driver/app versions, measurement method, baseline,
and repeatability. Unsupported hardware remains explicitly unsupported or
partial and cannot satisfy a required outcome. Keep run bundles free of user
media, stream keys, private configuration, and credentials.

The initial matrix deliberately has no accepted fixtures or evidence. The
documentation row uses a HorneroOS review reference rather than pretending a
document review is a synthetic VM run.
