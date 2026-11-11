# Minimal Arch Linux ARM for a base M3 MacBook Pro

A console-only evaluation image for **Mac15,3 / J504AP / T8122**. It preserves the stock Asahi Alarm kernel and Apple boot stack. You install your own user tools, desktop and rice later with pacman.

**Static, userspace and adapted VM startup checks pass. Physical Mac boot remains unverified; no installation has been performed.**

## What was built

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

43 portable tests pass. The strict derivative audit, e2fsck checks and signed hardware-file comparisons pass. The actual image's password helper, skip/retry behavior, repeat invocation, systemd units and pacman dependency database were tested successfully in a disposable chroot. These chroot results are separate from the adapted VM startup check below; neither is physical Mac qualification.

The integration command is `python3 tests/integration_firstboot.py <ZIP>` inside the audit container with `--network none --cap-drop ALL --cap-add SYS_CHROOT --cap-add MKNOD` and the project mounted read-only. It temporarily extracts a root in the container, runs its binaries, then deletes that disposable root.

## Installation boundary

This project intentionally has no automatic installation command. Relative package names in the Asahi engine resolve to `$REPO_BASE/os/<package>`, which is why the output contains an `os/` directory. The metadata is for a downstream Asahi engine, not a replacement for the official signed Omarchy catalog. The engine still must extract the model's proprietary Apple firmware during an authorized install and complete Apple's Recovery boot-policy flow.

Before any actual install, separately review backup, free space, firmware choice, root size, encryption needs and recovery. Local files and unit/chroot checks cannot prove the Apple boot chain or peripherals work on the physical J504AP.

After a separately authorized, successful boot, the intended workflow is ordinary console setup: set hostname/timezone, create your user, configure sudo, connect networking, update the full system, then install your own tools and desktop. There is no Omarchy update framework to undo those choices.

## Installer handoff continuation

A fail-closed, non-installing preflight and POSIX runtime staging are now available. The published engine accepted the actual local ZIP and metadata, calculated sizes and extracted EFI into disposable storage. Its bundled Python also passed this contract test on the owner's Mac. Read [the handoff report](docs/handoff.md). The corrected, attested same-kernel QEMU fixture now reaches login with healthy first boot, zero failed units and successful in-guest package signature verification. Virtual-hardware adaptations are explicit; the delivered ZIP is unchanged. Apple hardware and boot-chain qualification remain outstanding.
