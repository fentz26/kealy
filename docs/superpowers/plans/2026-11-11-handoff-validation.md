# Minimal Arch M3 handoff validation

> Execute inline; continue local reversible preparation. No disk/boot mutation or installer launch.

Goal: validate the payload with the published Asahi engine, add a fail-closed model/artifact preflight and improve startup evidence if the same kernel can boot QEMU virt.

Constraints: J504AP/Mac15,3/T8122 only; preserve payload bytes; no sudo, partition APIs, installer main, network downloads from a preflight, or fabricated physical-boot claim. The external project disk is exFAT; extract framework symlinks only to disposable POSIX storage, not onto exFAT.

- [x] Try same-kernel QEMU boot using virtio console, disposable disk snapshot, bounded timeout and logs. Inspect transport modules first; record failure honestly if not compatible.
- [x] Add tested preflight validating host model/board/native architecture, pinned installer/payload hashes, metadata paths/root sizes, firmware-copy and boot contracts. Preflight never invokes install.sh/main.py/sudo or changes disk state.
- [x] Exercise published OSInstaller.load_package and sizing on the real local payload in a separate process with disk operations and network explicitly forbidden; use original engine sources from the pinned tar.
- [x] Produce a handoff manifest and instructions with explicit manual-install boundary. No launch wrapper is enabled before physical-install authorization.
- [x] Fresh code review, focused tests and evidence/documentation updates.

Completion: handoff preparation and contract checks complete; both bounded VM experiments unsuccessful and documented, including the failing tests/integration_vm.py fixture. Physical installation remains unauthorized.
