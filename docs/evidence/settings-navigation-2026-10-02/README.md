# Settings navigation baseline

These screenshots were captured by the passing `personalization/baseline-settings`
scenario at 1280×800. The sidecars retain run IDs, exact product SHAs and image
hashes.

| Stage | Shell | Evidence |
|---|---|---|
| Before pane discovery metadata | `b2f27e6` | [Settings overview](before-settings.png) |
| With canonical pane metadata | `0a18b16` | [Appearance entry](after-appearance.png) |

The second capture follows a real pointer click and waits for the Settings
window title to report Appearance before capturing. The current pane still
contains dense appearance details and is a baseline for follow-up UX work; this
change only establishes the shared pane-discovery metadata and category model.
