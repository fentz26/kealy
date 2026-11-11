# Minimal Arch Linux ARM for an M3 Mac

Status: superseded in direction by the user clarification and docs/repository-comparison.md. Prefer validating an existing normal minimal install before building a custom image. The user subsequently directed substantive work to proceed; the selected implementation is the small stock-image derivative described in docs/qualification.md, rather than a new kernel/distribution build.

## Intent

Build a console-only Arch Linux ARM system for the owner's MacBook Pro Mac15,3 (base Apple M3; ioreg confirms J504AP / apple,j504). The owner wants pacman and control over every optional desktop and application. The project lives at /Volumes/Fentz_SSD_A/Coding/arch-m3. Preparing source and disposable image artifacts is authorized; installing Linux, resizing partitions and changing boot policy are not.

## Goals and exclusions

- Boot to a local text login, with working keyboard, storage and networking.
- Provide pacman, package trust configuration, a normal administrator account, sudo and a small console editor.
- Preserve model-specific Apple firmware handling, compatible kernel/device trees, m1n1, U-Boot and boot-update hooks.
- Preserve speaker protection if an audio stack is included. Initial image may omit audio entirely; it must not enable unprotected speakers.
- Initially ship no Hyprland, GNOME, KDE, graphical login manager, browser, AI agent, Omarchy desktop runtime, themes or developer application bundle. The owner explicitly intends to install Hyprland and rice later; do not prevent normal future package installation.
- Do not invent kernel drivers or mix incompatible boot and graphics packages.
- No installation, host disk modifications, public release, production signing or claims of physical boot validation in this phase.

## Approaches

1. Selected by owner: build a clean minimal image using Arch Linux ARM as the base and the necessary Apple hardware packages. Replace desktop-dependent first-boot/configuration logic with a minimal implementation. This is more work initially but gives the desired ownership and package set.
2. Rejected: strip a full Omarchy image. Its runtime owns first boot, setup and parts of boot maintenance; removing the desktop does not remove those dependencies cleanly.
3. Not selected: use Asahi Alarm Minimal unchanged. It is the closest existing product, but M3 model admission and sufficient support must be demonstrated rather than inferred from the name.

## Upstream comparison and evidence

Inspected Omarchy Mac Installer commit c07e54c2134a8ec1415e7e2b917589ae1d3d7dc9 in a temporary read-only research checkout.

- AsahiLinux/asahi-installer is a distribution-neutral installer with downstream metadata/image support. It prepares the bespoke Apple boot environment; it is not the Arch root filesystem.
- Asahi Alarm publishes minimal Arch Linux ARM images and manual console setup. Its live metadata, model support, boot package revisions and root image build source need comparison before any reuse is selected.
- Omarchy's image-builder/bin/build-mac-image already starts from an Arch Linux ARM root filesystem, verifies inputs and creates EFI/boot/root payloads. It then installs the desktop default closure, invokes omarchy-apply-system, configures a Plymouth theme and SDDM, and arms Omarchy first boot. Those operations cannot carry over unchanged.
- Omarchy's documented M3 hardware set includes linux-aurora, m1n1-aurora, uboot-aurora, firmware and Aurora Mesa/Vulkan packages. The initial console-only manifest need not install graphics userspace, but later desktop guidance must preserve the matching M3 graphics implementation.
- omarchy-mac and omarchy-mac-boot are separately packaged, but their setup/lifecycle still calls the Omarchy runtime. Installing them blindly would violate the no-runtime goal. Port only the required model-specific operations with attribution, focused tests and explicit dependencies.
- Omarchy's supported-models.json enables M3 boards but marks them untested. Catalog admission is not physical qualification. Confirm the owner's actual board identifier and its firmware requirements before finalizing a payload.
- The official Omarchy app trusts signed catalogs, not arbitrary replacement images. A custom payload must use a documented downstream/developer path; never masquerade as an official signed image or disable official verification.

Primary references:
- https://github.com/AsahiLinux/asahi-installer
- https://github.com/asahi-alarm/asahi-alarm/blob/main/manual-install.md
- https://github.com/omacom/omarchy-mac-installer/blob/main/image-builder/bin/build-mac-image
- https://github.com/omacom/omarchy-mac-installer/blob/main/image-builder/README.md
- https://github.com/omacom/omarchy-mac-installer/blob/main/scripts/supported-models.json
- https://github.com/omacom/omarchy-mac-pkgs/blob/main/omarchy-mac/README.md
- https://github.com/omacom/omarchy-mac-pkgs/blob/main/omarchy-mac-boot/README.md

## Delivery stages and feasibility gates

Stage 0 delivers the pinned upstream comparison, board-specific package/boot compatibility matrix, dependency audit, trust policy and validated custom payload contract. The board is confirmed locally as J504AP. This stage uses source and metadata inspection only and does not require a Linux daemon.

Stage 1 implements the minimal builder and portable tests. Full assembly is conditional on Stage 0 proving a coherent package set and downstream engine handoff, and on a verified disposable aarch64 Linux runner. If any gate fails, deliver the source/audit and explicit blocker; do not substitute a stripped desktop image or claim an installable result. The initial artifact is an unencrypted console-only evaluation payload; optional encryption is a later independently reviewed feature before any real installation. The console wizard is local-only, root remains locked, and SSH remains disabled throughout provisioning.

## Architecture and deliverables

### Source and provenance

Use a standalone project with small, attributed adapters rather than a full kernel fork. Pin upstream commits, repository databases and downloaded input hashes. Keep a comparison report recording upstream versus downstream duties and unresolved model-specific differences. Preserve licenses for copied code. Do not vendor huge kernel histories or Apple's proprietary firmware.

### Package and repository policy

Maintain an explicit minimal package manifest and a separate hardware manifest. Prefer Arch Linux ARM for general packages; allow downstream repositories only for enumerated hardware packages and their necessary dependency closure. Signature verification remains enabled. Validate the resolved package closure to reject desktop/runtime packages and conflicting kernels or boot providers. Record package names, versions, source repositories, hashes and signing identity in the build output. A standard pacman upgrade must retain the required boot hooks and hardware package selection; repository ordering alone is not an adequate policy.

### Image builder

Run image assembly inside a disposable aarch64 Linux environment with the required loop devices and filesystem tools. Build image files only, never a supplied physical block device. Stage an Arch ARM root, install the audited package closure, configure networking and console boot, generate initramfs and the compatible Apple boot chain, then package an Asahi-compatible payload. Choose the simplest filesystem/layout compatible with the verified installer engine; preserve an upstream layout initially if changing it increases boot uncertainty. Do not inherit factory reset or snapshot machinery unless the selected boot contract actually requires it.

The build must refuse missing pins, signature failures, unresolved dependencies, incorrect architecture, unexpected model/firmware pairings and host block-device destinations. Downloads and package execution happen only after the manifest and trust roots are reviewed. No installation entrypoint is included in the first implementation milestone.

### Firmware contract

Stage 0 must distinguish redistributable signed firmware packages from proprietary Apple firmware extracted for the individual Mac. Do not download or redistribute a pre-extracted owner bundle. Prefer the selected Asahi-derived engine's existing device-specific extraction and payload-completion contract. Record required firmware versions and paths in the compatibility matrix; a static image may intentionally lack owner firmware only if the engine contract proves how it supplies it before boot. Otherwise missing firmware blocks an installable artifact.

### First boot

Use a dedicated local tty1 systemd setup service ordered before the normal tty1 getty, with the normal getty disabled until provisioning completes. Keep its state in /var/lib/arch-m3/provisioning; write completion atomically only after account and sudo configuration validate. On interruption, resume the wizard without deleting an already created account or opening root login. Recovery is through the selected offline rescue environment, documented before image qualification. Blank-password login and network-facing setup are prohibited.

Provide a small console-only first-boot setup for hostname, timezone, a normal user and passwords entered locally. Never embed a password, SSH private key or shared root/root login in the image. Lock unused root authentication and provide a documented recovery path. Do not enable SSH by default. Networking uses NetworkManager with a documented terminal workflow. Account setup must complete before the system exposes an authenticated normal login, and interruptions must resume safely.

Builder proposal: include sudo and a small console editor, use the standard Bash shell, include Wi-Fi tools, and leave a desktop, audio userspace and development toolchains for later installation. The initial evaluation payload is unencrypted. Final partition sizes remain installation-stage choices; the source must not silently select or apply a host disk layout. Encryption support, if desired, must be added and validated before installation rather than assumed compatible.

### Installation handoff

Produce payload metadata, hashes, a package manifest, build logs and validation results. Separately document a verified custom/downstream installer handoff after proving the engine accepts the payload and the correct model/firmware combination. If the handoff cannot be demonstrated without bypassing official trust, mark the artifact build-only and stop short of calling it installable. The owner must separately authorize real disk/boot changes later.

## Validation and acceptance

1. Portable unit/fixture tests cover manifests, pins, trust failures, model guards, path safety, package exclusions and first-boot state transitions.
2. Resolve the full package dependency closure in the Linux builder; fail if excluded desktop/runtime packages return transitively.
3. Assemble the root and boot images in disposable storage. Inspect filesystem structure, installed package provenance, initramfs content, kernel/device-tree/m1n1/U-Boot compatibility and EFI paths.
4. Validate payload metadata against the selected installer engine without running live disk operations.
5. A generic ARM VM may validate userspace and first boot, but cannot validate Apple hardware. Report it separately.
6. No hardware-boot success claim until a separately authorized installation has booted on the owner's exact Mac and the checks are recorded.

## Build environment and current limits

The macOS host has a docker CLI, but docker info fails because the daemon socket is unavailable. No usable Linux build runner is currently established. An aarch64 Linux VM or container backend with suitable loop-device/filesystem capability must be verified before full image assembly. Keep Linux root filesystems on a Linux-native filesystem inside the VM; the external project volume stores source and artifact archives, not a live extracted root with assumed POSIX semantics. Do not silently start privileged infrastructure, register helpers or change host disk setup to solve this.

## Decisions left to implementation

Determine the exact M3 board and live source revisions; establish whether Asahi Alarm's current engine/image can be used directly; identify the minimal Aurora package closure; choose the downstream payload handoff and boot layout from verified contracts; settle editor choice and internal module names. Document every such choice and distinguish source-tested, image-built, VM-tested and hardware-tested results.
