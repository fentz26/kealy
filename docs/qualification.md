# Artifact qualification

Target: Mac15,3 / J504AP / T8122. Date: 2026-11-11.

## Current result

`artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip`

SHA-256: `dcefe5d03631ed013da73d942f7f1ab3f9844a3619da993541891b7c7760dfb2`

The unchanged evaluation image has passed static checks, userspace integration and an adapted QEMU/HVF startup test using the original signed kernel. It remains unencrypted and not physically boot-qualified on this Mac. No host partitions or Apple boot settings were changed.

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

43 portable tests pass. Historical failure logs are retained; the fresh attested run supersedes them.

## Remaining proof boundaries

- No physical J504 boot, Apple Recovery authorization, per-device proprietary firmware extraction, m1n1 or U-Boot execution on the Mac was tested.
- QEMU booted directly with kernel/initramfs. GRUB configuration syntax was checked, but rebooting through regenerated GRUB or the Apple boot chain was not tested.
- Virtual console adaptation does not prove the Mac's physical display, keyboard, touchpad, Wi-Fi, audio, suspend or upgrade/recovery behavior.
- Accelerated Hyprland/Mesa on M3 remains unverified. Stock Asahi was retained; no Aurora stack was substituted.
- The model-guarded preflight and staged runtime do not authorize installation. A concrete disk/backup/encryption plan and separate authorization are still required before disk or boot-policy changes.
