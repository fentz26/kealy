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

## VM attempt

A bounded QEMU/HVF test used the same signed kernel, existing initramfs and a snapshot of a disposable root copy, with no network or host disks. It did not reach a usable console or login. The kernel has a built-in virtio console, but its required MMIO transport is modular and absent from the stock initramfs. A second bounded fixture test added the signed transport module, remapped the console units to hvc0 and omitted the Apple-only EFI mount. It also timed out without an authenticated console. `tests/integration_vm.py` therefore remains a failed integration experiment, not a passing test. There is no successful same-kernel VM boot claim. This result neither proves nor disproves physical J504 boot; no root/kernel changes were made to make a generic VM pass.

## Remaining boundary

Physical boot, Apple firmware completion, actual peripherals and future accelerated Hyprland remain unverified. No partition resize, root disk write, boot-policy change or installation was performed. No automatic launch command is included in this handoff.
