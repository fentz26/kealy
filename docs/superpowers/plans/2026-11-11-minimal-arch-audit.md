# Minimal Arch M3 validation and build plan

> **For agentic workers:** Execute inline using superpowers:executing-plans. Track evidence and blockers in docs/progress.md.

**Goal:** Produce a verified minimal Arch Linux ARM route or custom payload for J504AP, without installing it.

**Architecture:** Prefer the existing Asahi Alarm minimal payload when its shipped files satisfy board/boot requirements. Compare Aurora only for actual gaps. Keep desktop installation a normal later pacman operation.

**Tech Stack:** Python standard library, Arch Linux ARM, Asahi installer and hardware packages, disposable aarch64 Linux build environment.

**Spec:** ../specs/2026-11-11-arch-m3-design.md as corrected by ../../repository-comparison.md and the user's instruction to proceed with substantive work.

## Global Constraints

- No physical disk, partition or boot policy changes; no installation.
- Target Mac15,3 / J504AP / T8122, aarch64.
- No preinstalled desktop or Omarchy runtime; later Hyprland remains supported in principle, subject to hardware validation.
- Preserve signatures and distinguish source admission, artifact inspection, VM checks and real hardware validation.

## Review Focus

- Source revision and actual published binaries can differ.
- Firmware support does not prove GPU support.
- Kernel/bootloader/device tree versions must agree.
- Image inspection must not mount or write host devices.
- Package signatures and payload transport hashes have different trust meanings.

### Task 1: Establish published artifact evidence

- [x] Record source revisions, live installer metadata and transport headers.
- [x] Inspect the published installer for J504AP admission and firmware contract.
- [x] Download the minimal payload, record its local digest, inspect contents offline.

### Task 2: Add reproducible artifact audit tooling

- [x] Write failing tests for unsafe archive members, missing device tree/kernel/bootloader, desktop packages and mismatched artifact identity.
- [x] Implement a read-only auditor and evidence report. Never execute image content on macOS.
- [x] Run tests and audit the real payload; record all gaps.

### Task 3: Resolve smallest required integration

- [x] Compare stock Asahi kernel/m1n1/U-Boot/GPU recipes with Aurora for J504AP.
- [x] If stock payload satisfies console needs, retain it rather than inventing a new distribution.
- [x] If not, define and implement a minimal hardware-only image adaptation with tests, preserving upstream package trust and boot contracts.
- [x] Validate package closure and payload format in disposable Linux storage when runner permits; report any unmet requirement explicitly.

### Task 4: Review and deliver

- [x] Fresh review of source, tests, conclusions and evidence.
- [x] Fix important findings, run final checks and provide exact artifact status and outstanding physical-device validation.

## Completion boundary

All steps completed for an evaluation image. Hardware-specific boot/peripheral qualification and a model-guarded installer are not claimed. Stock Asahi support sufficed for artifact-level console preparation, so the optional Aurora adaptation was not needed or implemented. Full generic VM boot was replaced by explicit userspace tests because the stock kernel lacks the generic virt serial driver; see ledger ruling.
