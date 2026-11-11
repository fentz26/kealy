# Local installer handoff

The evaluation ZIP is unchanged. Its local host, archive, metadata and published-runtime preflight now passes on Mac15,3 / J504AP / native arm64 / macOS 27.2.1.

## Read-only preflight

From the project directory:

```sh
python3 -m arch_m3.handoff
```

This checks the exact model/board, native process architecture, macOS version, pinned ZIP and installer hashes, M3 firmware handoff, EFI volume identity, actual root size and the allowed metadata operations. It rejects network payload names, extra downloads, unknown product/partition operations, root reformatting and EFI expansion. It does not run installer main, sudo or diskutil.

## Prepared runtime

A disposable APFS staging directory was created at `/private/tmp/arch-m3-handoff-reviewed/`. Its `runtime/` contains the pinned published installer, a copied local ZIP under `os/` and the reviewed descriptor. The payload copy was rehashed. `handoff.json` records the paths and hashes.

The external source SSD is exFAT and cannot preserve the installer's framework symlinks. Use POSIX/APFS staging. A future restaging operation can be prepared, without launching an installer, with:

```sh
python3 -m arch_m3.handoff --stage /private/tmp/arch-m3-handoff-NEW
```

The destination must not already exist. `/private/tmp` is disposable, so it is not a permanent backup or release location. The staged runtime remains a raw capable installer; the preparer does not authorize invoking it. Any future installation session must revalidate staged identity and separately approve a concrete disk plan before using it.

## Contract tests performed

`tests/integration_engine.py` extracts only the pinned `osinstall.py`, `util.py`, `m1n1.py` and `urlcache.py` into a temporary source directory. It calls the published engine's local payload loader, size calculations and EFI extraction. Installer main is never imported or run; network, subprocess/device access and writes outside disposable extraction are blocked by the test guard. The same test passed with both host Python and the installer's actual bundled Python 3.13.9.

The original engine reports 4,243,587,072 bytes minimum and 8,487,174,144 bytes recommended for its two-partition OS payload. These are engine calculations, not a proposed allocation for the owner's work. They exclude the Apple stub and do not promise sufficient space for a future desktop, development tools or personal data.

The bundled Python starts successfully and loads SSL/ctypes on this Mac. This proves runtime loading, not per-device firmware extraction, Recovery authorization or installation.

## VM startup verification

The adapted QEMU/HVF test now passes with the same signed kernel and root derived from the pinned ZIP. It reaches authenticated login, completes upstream first boot, reports zero failed units and verifies a signed package with the guest's populated keyring. Mount and regenerated GRUB syntax checks also pass.

Earlier failures were traced to missing four-byte CPIO padding in the test fixture. A fixture without EFI also failed the upstream first-boot prerequisite; a second disk required UUID-based root selection. These were harness defects/omissions, not changes needed in the delivered ZIP. Historical logs remain, and evidence/vm-attested is the current result.

Reproduction uses fresh disposable POSIX storage:

```sh
docker build -f - -t arch-m3-fs-tools:local . < tools/Dockerfile.vm
python3 tests/prepare_vm_inputs.py /private/tmp/arch-m3-vm-NEW .
mkdir -p evidence/vm-NEW
python3 tests/integration_vm.py /private/tmp/arch-m3-vm-NEW evidence/vm-NEW hvf --with-efi
```

Preparation records and hashes the source ZIP/root and exact fixture changes. The runner verifies these before boot. It uses file-backed snapshots and no network or host disk devices. The fixture adds virtio transport, remaps the console and supplies a disposable EFI filesystem and UTC clock. It does not modify the delivered ZIP. That initial test alone did not prove a GRUB reboot; the separate lifecycle test below now covers EDK2/GRUB, while the Apple boot chain remains untested. See docs/qualification.md for the precise boundary.

## GRUB and second cold boot

`evidence/grub-final/` records two successful cold boots through EDK2 and the artifact-derived GRUB EFI loader, with no direct kernel-loading arguments. Both phase reports include checked firmware banners/load messages and explicit clean shutdown records.

The first boot performs setup and UUID changes. The second reuses the same persistent disposable overlays and private test password, keeps both filesystem UUIDs, credential checksum and persistence marker, and skips initial setup. Both report healthy userspace, zero failed units, valid mounts and successful package signature verification. Raw parents and the delivered ZIP remain unchanged.

To reproduce from an attested fixture:

```sh
python3 tests/prepare_grub_fixture.py /private/tmp/arch-m3-vm-NEW /private/tmp/arch-m3-grub-NEW
python3 tests/integration_reboot.py /private/tmp/arch-m3-grub-NEW evidence/grub-NEW
```

Both destination/report directories must be new. The prepared fixture uses the locally installed QEMU EDK2 firmware, cloned GRUB console configuration and VM-only initramfs. It is not a physical Mac install or Apple firmware test.

## Remaining boundary

Physical boot, Apple firmware completion, actual peripherals and future accelerated Hyprland remain unverified. No partition resize, root disk write, boot-policy change or installation was performed. No automatic launch command is included in this handoff.
