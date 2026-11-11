# Repository comparison — 2026-11-11

## Corrected user intent

A normal minimal Arch-style installation on Apple M3: text console, pacman and required hardware support. The owner will install Hyprland or another desktop and rice it later. Desktop packages are excluded from the initial image only, not prohibited on the resulting system. Avoid a custom distribution or configuration wizard unless the hardware genuinely requires one. No installation is authorized yet.

## Findings

- Official Arch Linux is x86-64. The native base for this Mac is the separate Arch Linux ARM port.
- Asahi Alarm already has a minimal image builder. Its base script installs standard console/admin/network tools plus Asahi firmware, boot and kernel packages. Desktop construction is a separate stage.
- Live Asahi Alarm installer_data.json lists Minimal, Minimal BTRFS and UEFI-only products with firmware 14.8.3. Current installer source explicitly lists j504ap with that firmware and expert_only=False. This proves source admission, not that a downloaded release/image is boot-qualified.
- Asahi Alarm kernel recipe follows AsahiLinux/linux. Asahi's M3 support table still lists GPU/full display as work in progress. A minimal console install and a usable accelerated Hyprland session are different milestones.
- Omarchy's hardware package recipes are separable from its desktop. linux-aurora, m1n1-aurora, uboot-aurora and mesa-aurora are the relevant comparison. m1n1-aurora's recipe explicitly constrains J504 handoff compatibility with linux-aurora >= 7.2.11.aurora16. These must not be arbitrarily mixed with stock packages.
- Omarchy's complete image builder adds its desktop, settings and first-boot runtime. It is not the right starting point when the objective is a conventional minimal system.

## Revised direction

First validate Asahi Alarm Minimal's actual published engine and payload for J504AP. Prefer the existing minimal product if sufficient, avoiding a new image builder. Audit Omarchy's extra J504 kernel/boot/GPU changes only where stock support falls short, particularly for the later desktop. Any custom work should be a small, maintainable hardware integration, not Omarchy minus its UI. Do not claim the published minimal image works based on metadata alone.

## Evidence paths

- https://archlinux.org/about/
- https://archlinuxarm.org/about
- https://github.com/asahi-alarm/asahi-alarm-builder/blob/main/scripts/base/10-base-packages.sh
- https://github.com/asahi-alarm/asahi-alarm-builder/blob/main/scripts/base/15-kernel.sh
- https://github.com/asahi-alarm/asahi-alarm-installer/blob/main/src/main.py
- https://asahi-alarm.org/installer_data.json
- https://github.com/asahi-alarm/PKGBUILDs/blob/main/linux-asahi/PKGBUILD
- https://asahilinux.org/docs/platform/feature-support/m3/
- https://github.com/omacom/omarchy-pkgs/blob/master/pkgbuilds/m1n1-aurora/PKGBUILD (use repository default branch if moved)
- https://github.com/omacom/omarchy-pkgs

## Inspected revisions

- Asahi Alarm image builder: 58cc158c7fda3ef6aeae36606f84a63b4b0867e7
- Asahi Alarm installer: 3cfef52bc372a7b84b59823027c75327e129d6ec
- Omarchy package recipes: 7046eaf2f528828c35b85e26f155662f9040618b
