# Bluetooth acceptance (hardware-free)

Status: **the doctor shipped; the QA-harness scenarios are NOT TESTED
yet.** The doctor shipped in v0.2.0-preview30 and passed on installed Desktop/Studio VMs with honest no-adapter results (Preview 30 release checklist, HorneroOS/hornero); the probe scenarios here are still scheduled for the next approved KVM QA window and no hardware PASS is claimed. This document and the tests
below pin the expected contracts; nothing here is a hardware PASS.

## Automated without hardware (this repo)

| Contract | Test | Fixture |
|---|---|---|
| Catalogue/package presence (bluez, bluez-utils; no blueman) | `tests/test_bluetooth_acceptance_contracts.py` | `tests/fixtures/bluetooth-acceptance.json` |
| Service enablement (bluetooth.service, non-mandatory, preset) | same | same |
| BlueZ config (dual mode, JustWorksRepairing=never) | same | `tests/fixtures/bluetooth/main.conf` |
| Power persistence (rfkill + systemd-rfkill, AutoEnable=true) | same | same |
| WirePlumber policy (codec order, mSBC, autoswitch, no global autosuspend disable) | same | `tests/fixtures/bluetooth/51-hornero-bluetooth.conf` |
| Doctor JSON (adapter / no-adapter / rfkill-blocked states) | `tests/test_bluetooth_doctor_contract.py` | `tests/fixtures/bluetooth-doctor-contract.json` |
| VM scenarios (no-adapter, service-down, power-toggle honesty) | `tests/test_bluetooth_scenarios.py` | `scenarios/connectivity/bluetooth-*.yaml` |

Run: `uv run pytest tests/test_bluetooth_doctor_contract.py tests/test_bluetooth_acceptance_contracts.py tests/test_bluetooth_scenarios.py`

## NOT TESTED — physical hardware required

Never mark these PASS from the contracts above:

- Pairing: passkey confirmation/rejection, MITM protection, PIN entry.
- Audio: A2DP codec negotiation (LDAC/aptX/SBC-XQ/AAC), HFP mSBC calls,
  autoswitch to headset profile on a real device.
- Suspend/resume and reboot power persistence on a real adapter.
- Autosuspend quirks for specific USB VID:PID adapters.
- Dongle hotplug, multi-adapter behaviour, device battery reporting.

These need a vhci virtual-adapter fixture or a hardware lab, neither of
which exists in this repo today. The VM scenarios in
`scenarios/connectivity/` are likewise NOT TESTED until a horneroctl
tag ships the doctor command; see `docs/scenario-triage.yaml`.

The pairing agent `hornero-bt-agent` ships with the shell/hornero
Bluetooth PRs, not with this QA repo. The doctor `bluetooth-agent`
check (the `agent` field pinned in
`tests/fixtures/bluetooth-doctor-contract.json`) requires that agent
to be present and running; physical pairing remains NOT TESTED until
that agent ships and a real adapter is available.
