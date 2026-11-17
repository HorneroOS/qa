# Installer (Calamares) pages, preview32 ISO

VM evidence, 2026-11-17, signed preview32 ISO (sha256 b8cd0f86..., GPG good), rootless user QEMU/KVM + OVMF, throwaway 40G disk, 4 GiB guest (one-off orchestrator exception to the 3 GiB cap; Calamares `requiredRam: 4.0`). Never pressed Install. The ISO predates Signal.

- `preview32-1280x800-*`: live boot, Welcome closed, Calamares Welcome, Location, Keyboard, Partitions (erase disk, unencrypted), Users, Edition, Summary.
- `preview32-1920x1080-*`: live boot, Welcome, Calamares Welcome only (the click-through driver uses 1280x800 fractions; at 1080p the Calamares window is not scaled and the Hornero Welcome overlaps it).

Observed: dark Signal-ish sidebar and banner with a light stock Qt content area; banner repeated on the Welcome page; at 1920x1080 the Calamares window stays 1280-class and is clipped by the Welcome window; the live shell shows pre-Signal chrome and icon ligature names as text (installer#101). Driver: qa-mission scratch script `install-pages.py`.
