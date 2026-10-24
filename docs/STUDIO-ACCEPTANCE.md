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
hashes. Every product pin must be present in the runner's copied `product`
metadata. The current image builder does not produce all Studio pins. Until
that producer contract lands, owners can declare pins on an adopted image
with `hornero-qa image adopt ... --product KEY=VALUE`; the gate does not infer
values from labels, environment descriptions, or branch names.

For bundle evidence, fixture approval includes a stable fixture ID and a
declared SHA256 for its owner-reviewed fixture manifest. Both values must
match the bundle's product metadata. At this stage the gate does not fetch or
hash the fixture manifest, so this equality is a declaration check. Review
evidence must link to a HorneroOS pull request, matching the accepted human
review reference; the gate does not query GitHub to validate the PR or its
reviews.

The gate validates that bundle files are present and internally consistent;
it does not authenticate them. `image adopt --product` records operator
declarations and does not prove that an image contains the declared commits
or catalogue. Screenshot sidecars and logs are not signed, and the gate does
not bind their contents to an immutable bundle digest. Owners must inspect
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
