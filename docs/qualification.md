# Artifact qualification

Target: Mac15,3 / J504AP / T8122. Date: 2026-11-11.

## Result being evaluated

`artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip`

SHA-256: `dcefe5d03631ed013da73d942f7f1ab3f9844a3619da993541891b7c7760dfb2`

This is an evaluation artifact, not a physically qualified distribution release. It is unencrypted. No host partitions or Apple boot settings were changed.

## Evidence collected

- Published Asahi Alarm v0.9.2 installer contains J504AP admission, T8122 and the 14.8.3 firmware contract. Inspection used archive reads, not execution of the installer.
- Downloaded minimal payload and captured its local SHA-256, ZIP structure, root size and installed package set.
- Verified detached GPG signatures for linux-asahi, m1n1 and uboot-asahi against fingerprint `12CE6799A94A3F1B5DDFFE88F576553597FB8FEB`. The full filesystem ZIP was obtained over HTTPS and locally pinned; no independent publisher signature for that complete ZIP was verified.
- Verified signed J504 DTB and m1n1 bytes, plus decompressed signed U-Boot, in the source EFI boot bundle. Source and derivative EFI files are preserved unchanged by the builder; archive-level inspection and kernel digest comparison provide the separate readback checks.
- Verified actual ext4 UUID against fstab and active GRUB root arguments. Referenced kernel has the ARM64 image header, its digest matches the signed package, and the referenced initramfs is nonempty with a recognized archive/compression header.
- All 261 installed packages are retained. No Hyprland, Omarchy runtime, SDDM, GDM, GNOME shell, Plasma workspace or LightDM is in the package set. This is an audit of the installed product, not a new package-selection resolver.
- Builder read back edited file contents and modes/ownership, root credential policy, SSH masks and scrubbed identity/firstboot markers. e2fsck repair and subsequent read-only checks completed successfully on the disposable image.
- Strict derivative audit passed with no failures/warnings: root and other initial passwords locked, all SSH entrypoints masked, console target selected and password helper executable/root-owned.

Detailed outputs live in `evidence/`. `system-audit.json` is the earlier upstream inspection; `derivative-audit-strict.json` is the stricter final image inspection. Hardware package signatures do not authenticate unrelated files in the root filesystem.

## Real userspace validation

The image was extracted into a disposable, networkless Linux chroot and its actual systemd/account binaries were run. The sandbox had only SYS_CHROOT and MKNOD capabilities, no host disk devices and a read-only project input. An empty proc/cmdline fixture replaced unavailable live proc state; this was not a booted system.

All checks passed: skipping a password failed closed without a completion marker; a private random test password completed setup; the marker was mode 0600; repeating the helper preserved the password; systemd-analyze accepted the provisioning/getty units; and pacman -Dk accepted the installed dependency database. Test passwords were generated in memory in the disposable root and were never embedded in the ZIP. See evidence/firstboot-integration.json.

## What remains outside this proof

- Actual J504 boot through Recovery, stage-1 enrollment, per-device firmware extraction, m1n1 and U-Boot on this Mac.
- Physical keyboard, touchpad, display, Wi-Fi, sleep, audio and upgrade/recovery behavior on this board.
- Accelerated Hyprland/Mesa on M3. The base deliberately retains stock Asahi; Omarchy's Aurora hardware packages require a separate compatible-stack validation before substitution.
- A full UEFI VM boot does not follow from a chroot test. The shipped kernel config lacks the generic PL011 serial driver, so a standard QEMU virt serial boot is not a valid drop-in hardware test.
- A packaged, model-guarded macOS downstream installer. The output follows the engine's relative payload layout but is not a replacement for a signed official Omarchy catalog. No launch wrapper has been enabled for this evaluation artifact.

The image is usable as a concrete build/review artifact. Physical installation requires a separate decision and validation session; do not interpret successful source or userspace tests as hardware qualification.
