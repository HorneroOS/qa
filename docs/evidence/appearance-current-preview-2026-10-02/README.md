# Appearance current-look preview

These 1280×800 captures show the Appearance journey on one package-faithful Hornero QA image. `before-appearance.png` shows the prior empty preview and metadata-heavy gallery. `after-appearance.png` shows the same Hornero Dark state after the preview/gallery changes. `after-light.png` records pointer-driven selection of Hornero Light and confirms the current-look preview follows the applied theme.

The interaction scenario is [`themes/appearance-apply-light.yaml`](../../../scenarios/themes/appearance-apply-light.yaml). It selects the theme through the UI, then verifies ID, mode, GTK, icons, GTK color-scheme, shell liveness and absence of QML runtime errors. Full run IDs, hashes, source/config pins and environment are in [`provenance.json`](provenance.json).
