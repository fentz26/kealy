# Artifact qualification

Target: Mac15,3 / J504AP / T8122. Date: 2026-11-11.

## Current result

`artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip`

SHA-256: `dcefe5d03631ed013da73d942f7f1ab3f9844a3619da993541891b7c7760dfb2`

The unchanged evaluation image has passed static checks, userspace integration, adapted QEMU/HVF startup, and two cold boots through EDK2 and artifact-derived GRUB using persistent disposable overlays. It remains unencrypted and not physically boot-qualified on this Mac. No host partitions or Apple boot settings were changed.

## Static and package evidence

- Published Asahi Alarm v0.9.2 admits J504AP/T8122 and the 14.8.3 firmware contract.
- The signed linux-asahi, m1n1 and U-Boot packages verify against `12CE6799A94A3F1B5DDFFE88F576553597FB8FEB`. J504 DTB, m1n1 and decompressed U-Boot match the source boot bundle. The referenced kernel matches the signed package.
- Actual ext4 UUID, fstab and active GRUB arguments agree. The referenced kernel/initramfs exist with expected headers.
- All 261 packages are retained without a desktop or Omarchy runtime. Strict image checks confirm locked initial passwords, masked SSH, a console target, executable/root-owned password setup, and consistent file permissions.
- e2fsck repair followed by a read-only check passed on the built image.
- The complete ZIP is locally pinned after HTTPS download; an independent publisher signature for that entire filesystem ZIP was not verified. Signed hardware packages do not authenticate unrelated root files.

## Real userspace and installer checks

The image's actual password helper was tested in a disposable Linux chroot. Skipping the password fails closed; a private password completes setup; the marker is 0600; repeating setup preserves the password. systemd-analyze and pacman -Dk passed.

Native model/artifact preflight passed. The published engine loaded the real local ZIP, accepted the descriptor/sizing contract and extracted EFI into disposable storage with disk-changing commands, network and writes outside staging forbidden. The same contract test passed with its bundled Python 3.13.9. APFS staging preserved framework symlinks and rehashed the payload copy. No installer main was invoked.

## Adapted VM startup verification

The authoritative result is `evidence/vm-attested/vm-fixture-result.json` with its sanitized console log and preparation manifest.

A fresh root was extracted from the pinned delivered ZIP. Preparation recorded the original root hash, signed package identities, original EFI hashes, exact adaptation commands and hashes of all fixture inputs. The runner checked those identities before boot and rehashed the delivered ZIP afterward. Both raw backing files were also rehashed after shutdown and remained unchanged; guest writes went to disposable snapshots.

Virtual-hardware adaptations were explicit:

- Add the signed kernel's virtio MMIO module in a correctly aligned test initramfs overlay.
- Map password/getty units to the virtual hvc0 console and mask the unused tty1 getty in the fixture.
- Set the virtual clock from host UTC, avoiding a virtual RTC limitation.
- Attach a disposable FAT EFI disk containing the upstream EFI files and a signed package verification input.

The same signed Asahi kernel reached multi-user mode. Private-password setup and authenticated login passed. The upstream first-boot service completed UUID randomization, fstab/GRUB regeneration and keyring initialization. Explicit guest markers confirmed system state running, zero failed units, valid changed root/EFI UUIDs, pacman database success, signed-package verification with the populated keyring, mount consistency and GRUB configuration syntax.

## Diagnosed failures and regression tests

Earlier failed VM experiments were not a valid basis for judging image boot readiness. The fixture appended raw CPIO after a gzip stream ending at byte offset 13,442,791 without four-byte alignment. Adding the missing padding made the injected support usable. Regression tests cover global CPIO alignment and entry layout; Linux's initramfs buffer specification requires ALGN(4).

A fixture omitting EFI caused the upstream first-boot script to fail at findmnt, as expected from its source. Adding EFI completed that path. Attaching a second disk exposed /dev/vda ordering assumptions; the test now uses the real root UUID as GRUB does. Result parsing now rejects echoed/generic status words, missing/invalid/duplicate UUID markers and stale success from failed reruns.

50 portable tests pass. Historical failure logs are retained; the fresh attested run supersedes them.

## Firmware/GRUB and repeat cold-boot verification

The authoritative lifecycle result is `evidence/grub-final/lifecycle-result.json`. Each phase includes QEMU arguments, firmware and Linux console logs, explicit firmware-loading assertions, guest checks and a clean shutdown record.

New APFS clones were made from the attested raw fixtures. The cloned root received the existing virtual-hardware initramfs at its normal /boot path and hvc0 arguments in GRUB defaults/config. Firmware code was hashed; EFI variables used a private copied store. Persistent qcow2 overlays held all guest writes. No direct -kernel, -initrd or -append boot shortcut, host block device or network interface was used.

Both independent QEMU processes booted EDK2, then the artifact-derived BOOTAA64.EFI GRUB loader, then the kernel/initramfs from the cloned filesystem. Firmware assertions require the GRUB banner, Arch entry and kernel/initramfs load messages. Both guests verified /sys/firmware/efi and shut down with QEMU exit code zero.

The second cold boot reused the first boot's overlays and password held only in controller memory. A different kernel boot ID confirmed a new session. Root/EFI UUIDs, the credential-file checksum and a marker written only during the first boot were identical. Initial password setup did not prompt again; upstream first-boot was skipped/inactive. Both boots reported running, zero failed units, valid mounts/GRUB syntax, a consistent package database and successful package signature verification. This tests the regenerated GRUB loader/configuration across UUID changes, not only its syntax.

Raw backing files and the delivered ZIP were rehashed and unchanged. The isolated overlays and EFI-variable copy contain test state only. Review confirmed the route/persistence evidence; subsequent regression tests added automatic firmware assertions and explicit shutdown records. The final run exercised those checks successfully.

## Remaining proof boundaries

- No physical J504 boot, Apple Recovery authorization, per-device proprietary firmware extraction, m1n1 or U-Boot execution on the Mac was tested.
- EDK2/GRUB VM success does not qualify the Apple firmware/m1n1/U-Boot chain. The test's virtual transport, console and clock adaptations are not changes to the delivered ZIP.
- Virtual console adaptation does not prove the Mac's physical display, keyboard, touchpad, Wi-Fi, audio, suspend or upgrade/recovery behavior.
- Accelerated Hyprland/Mesa on M3 remains unverified. Stock Asahi was retained; no Aurora stack was substituted.
- The model-guarded preflight and staged runtime do not authorize installation. A concrete disk/backup/encryption plan and separate authorization are still required before disk or boot-policy changes.
