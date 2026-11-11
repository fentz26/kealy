# Kealy

Minimal Arch Linux ARM for a base M3 MacBook Pro, built on Asahi Linux and Asahi Alarm. "Kealy" is the name of this build only: upstream package, kernel and file names (`linux-asahi`, `m1n1`, `uboot-asahi`, `arch-m3-minimal.zip`) are kept as they are, because the boot chain, pacman and the installer depend on them, and upstream licence and copyright notices stay intact.

A console-only image for **Mac15,3 / J504AP / T8122**. You install your own user tools, desktop and rice later with pacman. There is no Omarchy frontend.

**Nothing here has been booted on the physical Mac yet.** The image passes static checks and virtual-machine boots; the Apple boot chain, built-in screen, input, Wi-Fi and the external display are unverified until a real install.

## Repositories

| Part | Where |
| --- | --- |
| Image builder, audits, CI, installer script | this repository |
| Kernel source (`kealy` branch) | [fentz26/kealy-linux](https://github.com/fentz26/kealy-linux), also linked as the `kernel/linux` submodule |
| Package recipes for the kernel and m1n1 | `packages/` |

## Kealy kernel and external display

The released image replaces the stock `linux-asahi 7.2.12` with a kernel built from Asahi's `asahi-wip` branch (7.2.14, which has the M3 display controller) plus:

- the open, unreviewed upstream pull requests for M3 USB-C DisplayPort ([#659](https://github.com/AsahiLinux/linux/pull/659), [#660](https://github.com/AsahiLinux/linux/pull/660), [#661](https://github.com/AsahiLinux/linux/pull/661), [#662](https://github.com/AsahiLinux/linux/pull/662)), and
- one local device-tree change that wires the J504's external display controller to the **left-back USB-C port**. Upstream only wires the M3 Pro. The values come from this Mac's own Apple device tree, but the change is untested on hardware.

m1n1 is built from a pinned upstream commit that includes M3 display-controller setup. U-Boot is unchanged. `pacman` holds `linux-asahi` back (`IgnorePkg`) so a system upgrade does not swap this kernel for the stock one; `/etc/kealy-release` in the image explains how to return to stock. HDMI is not wired, and there is no GPU acceleration on the M3 yet, so any desktop renders on the CPU. Details are in [the external display plan](docs/external-display-plan.md).

The local device-tree change was written with AI assistance and must not be submitted to Asahi Linux, whose policy does not accept such code.

## Build

GitHub Actions builds everything on native arm64 runners (`.github/workflows/build.yml`): the kernel and m1n1 packages, then the image. `tools/upgrade-image.sh` installs the two packages into a private copy of the pinned Asahi Alarm image, the builder below applies the Kealy changes, and the audits run on the result. Running the workflow by hand with a release tag publishes the image as a GitHub release.

## Install

On the target Mac, from macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/fentz26/kealy/main/install.sh | sh
```

The script refuses any other model, downloads a release and the pinned Asahi Alarm installer, verifies their hashes and, after you type `install`, starts the interactive Asahi installer. That installer shrinks macOS to make room, asks how much space to give Linux and confirms before it changes the disk. Set `KEALY_DOWNLOAD_ONLY=1` to download and verify without starting it. Back up first.

## What the image builder does

The sections below describe the first evaluation image, built locally from the stock Asahi Alarm image. CI uses the same builder on top of the kernel upgrade.

`artifacts/minimal-evaluation-r2/` contains:

- `os/arch-m3-minimal.zip`: ext4 root plus the upstream EFI boot files.
- `installer_data.json`: Asahi downstream metadata with the actual image size.
- `build.json`: input/output hashes and qualification status.
- Filesystem and debugfs logs.

The source is Asahi Alarm Minimal, not the complete Omarchy desktop. Changes are deliberately small:

- Lock every pre-existing usable password, including any generic image account.
- Disable and mask SSH service/socket activation.
- Boot explicitly to `multi-user.target`.
- Ask for a private root password on the local tty1 before its login prompt, using the installed `systemd-firstboot`.
- Preserve ordinary manual account and package setup. No graphical installer or desktop is included.
- Correct the metadata root size from 2,209,614,225 to 3,719,299,072 bytes. The old normal recommended allocation is larger than the payload, but its declared minimum is too small for the current image.

The evaluation filesystem is **unencrypted**. No secret or default usable password is embedded. Nothing prevents installing Hyprland later; accelerated graphics on M3 is a separate hardware qualification step.

## Hardware comparison

The inspected payload has `linux-asahi 7.2.12.asahi3-1`, `m1n1 1.9.9-1` and `uboot-asahi 2026.07.asahi2-1`. Its J504 device tree is byte-identical to the one in the signed kernel package and is present in `esp/m1n1/boot.bin`. m1n1 and compressed U-Boot in that bundle also match their signed packages. The kernel referenced by GRUB matches the signed kernel package.

Omarchy's Aurora kernel, loader and Mesa recipes add downstream M3 work and impose their own compatibility constraints. They were compared, not mixed into this base. Stock Asahi still lists M3 GPU/full display support as work in progress; this console image does not promise accelerated Hyprland. Read [the comparison](docs/repository-comparison.md) and [the qualification report](docs/qualification.md) before deciding on later graphics changes.

## Reproduce local checks

Python 3.12+ is sufficient for portable tests:

```sh
python3 -m unittest discover -s tests -v
python3 -m arch_m3.audit asahi-base.zip --sha256 61153885581ca93bf7fbc05147146503b0b2de15355f207f0c04e56a78f03954
```

The original downloaded ZIP is ignored by Git. Its URL, hash, source revisions and signing fingerprint are in `upstream.lock.json`. A local hash pins the inspected download; it is not an independent publisher signature for the complete ZIP.

Build the Linux inspection tool from the checked-in Dockerfile. Passing it through stdin avoids macOS AppleDouble extended-attribute errors on the external SSD:

```sh
docker build --platform linux/arm64 -f - -t arch-m3-audit:local . < tools/Dockerfile.audit
```

Run the auditor with the project mounted **read-only**, no network and no capabilities:

```sh
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,source=$PWD,target=/project,readonly" \
  arch-m3-audit:local artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip \
  --system --derivative --sha256 dcefe5d03631ed013da73d942f7f1ab3f9844a3619da993541891b7c7760dfb2
```

To rebuild, create `artifacts/`, mount only that directory writable at `/output`, override the entrypoint to `python3`, and run `-m arch_m3.build asahi-base.zip --metadata evidence/asahi-alarm-installer-data.json --output /output/NEW-DIRECTORY --sha256 61153885581ca93bf7fbc05147146503b0b2de15355f207f0c04e56a78f03954`. Output must be a new directory. Filesystem timestamps mean a rebuild need not have the same ZIP hash; inspect and record each result separately.

No loop device, mount, privileged container or host disk is required for this builder. `debugfs` edits a private temporary image; `e2fsck` checks that image, then the output is packed and read back by the auditor.

## Verification results

50 portable tests pass. The strict derivative audit, e2fsck checks and signed hardware-file comparisons pass. The actual image's password helper, skip/retry behavior, repeat invocation, systemd units and pacman dependency database were tested successfully in a disposable chroot. These chroot results are separate from the adapted VM startup check below; neither is physical Mac qualification.

The integration command is `python3 tests/integration_firstboot.py <ZIP>` inside the audit container with `--network none --cap-drop ALL --cap-add SYS_CHROOT --cap-add MKNOD` and the project mounted read-only. It temporarily extracts a root in the container, runs its binaries, then deletes that disposable root.

## Installation boundary

This project intentionally has no automatic installation command. Relative package names in the Asahi engine resolve to `$REPO_BASE/os/<package>`, which is why the output contains an `os/` directory. The metadata is for a downstream Asahi engine, not a replacement for the official signed Omarchy catalog. The engine still must extract the model's proprietary Apple firmware during an authorized install and complete Apple's Recovery boot-policy flow.

Before any actual install, separately review backup, free space, firmware choice, root size, encryption needs and recovery. Local files and unit/chroot checks cannot prove the Apple boot chain or peripherals work on the physical J504AP.

After a separately authorized, successful boot, the intended workflow is ordinary console setup: set hostname/timezone, create your user, configure sudo, connect networking, update the full system, then install your own tools and desktop. There is no Omarchy update framework to undo those choices.

## Installer handoff continuation

A fail-closed, non-installing preflight and POSIX runtime staging are now available. The published engine accepted the actual local ZIP and metadata, calculated sizes and extracted EFI into disposable storage. Its bundled Python also passed this contract test on the owner's Mac. Read [the handoff report](docs/handoff.md). The corrected, attested same-kernel QEMU fixture now reaches login with healthy first boot, zero failed units and successful in-guest package signature verification. Virtual-hardware adaptations are explicit; the delivered ZIP is unchanged. Apple hardware and boot-chain qualification remain outstanding.

## GRUB and reboot validation

The follow-up lifecycle test now boots through actual EDK2/GRUB rather than QEMU's direct kernel shortcut, shuts down cleanly, and cold-boots the same overlays again. The password, regenerated UUIDs, credential checksum and persistence marker survive; setup is skipped on the second boot. Both boots are healthy with successful package signature verification. See evidence/grub-final/ and the qualification report. Apple firmware, m1n1/U-Boot and physical peripherals remain outside this VM proof.
