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

53 portable tests pass. Historical failure logs are retained; the fresh attested run supersedes them.

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

## Automatic root growth (disposable VM)

`evidence/growth-final/growth-result.json` records two clean EDK2 → GRUB boots of a fresh fixture whose root qcow2 alone was enlarged to 12 GiB before first boot. No guest resize command was issued. The filesystem automatically exposed 12,599,418,880 bytes on the 12,884,901,888-byte virtual disk, consistent with the existing `x-systemd.growfs` configuration. A 1 GiB extent allocation and 8 MiB random-data write succeeded; capacity, allocated blocks and SHA256 persisted across the second cold boot. Both boots reached a healthy multi-user system with zero failed units, valid package signatures and unchanged UUID/password state after initialization. Qcow2 checks and clean QEMU exits passed; raw parents and delivered ZIP stayed unchanged.

Reproduce using new directories (existing overlays deliberately fail the pristine-state guard):

```sh
python3 tests/prepare_grub_fixture.py /private/tmp/arch-m3-vm-attested /private/tmp/arch-m3-growth-new
python3 tests/integration_growth.py /private/tmp/arch-m3-growth-new evidence/growth-new
```

This tests filesystem expansion inside virtual hardware. It does not test partition allocation or resizing on the Mac. Systemd documents automatic growth via the [`x-systemd.growfs` fstab option](https://github.com/systemd/systemd/blob/main/docs/BUILDING_IMAGES.md).

## J504 static hardware inspection

The signed kernel package's DTB decodes to `apple,j504`, `apple,t8122`, model `Apple MacBook Pro (14-inch, M3, 2023)`. Its SHA256 remains `622073860f2bd6e9db1a6eef2e9d20fe3e7e4670fda4333cda0468db8d64ef8e`. Evidence is under `evidence/hardware-static/`; the config is `evidence/linux-asahi.config`.

| Path | Observed static evidence | Remaining qualification |
| --- | --- | --- |
| Internal storage | DTB Apple ANS2 NVMe node; `CONFIG_NVME_APPLE=y`, SART/RTKit built in | Physical controller initialization and I/O |
| Internal input | MTP/helper and dockchannel nodes enabled; `CONFIG_HID_DOCKCHANNEL=m`; `dockchannel-hid.ko` shipped in both package and original initramfs | Trackpad requires `apple/tpmtfw-j504.bin`; actual firmware loading/input untested |
| Wi-Fi | DTB Broadcom `pci14e4,4434`, board `apple,tresco`; `CONFIG_BRCMFMAC=m`, PCIe enabled, modules shipped | Board-specific firmware/calibration, actual network association |
| Display | `CONFIG_DRM_SIMPLEDRM=y`; DTB simple framebuffer placeholder has `status="disabled"`; Apple DRM module shipped | Boot-time framebuffer fixups and actual physical console output |
| GPU | `CONFIG_DRM_ASAHI=y`, but no GPU node in this static J504 DTB | No M3 acceleration or Hyprland qualification inferred from kernel config |

The original initramfs includes `/usr/lib/firmware/vendor -> /vendorfw`; it does not carry the named J504 trackpad firmware itself. Firmware supplied by the Asahi installer and boot-time device-tree fixups remain essential. Disabled static framebuffer placeholders do not establish that the boot-time framebuffer will fail. Conversely, package/module presence does not establish that these devices work. No proprietary firmware extraction or physical hardware test was performed in this phase.
