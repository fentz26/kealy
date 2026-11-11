# Kealy external display plan (handoff, 2026-11-11)

Goal: built-in screen plus one external monitor at the same time on the owner's MacBook Pro M3 8GB (Mac15,3 / J504AP / T8122), using a USB-C to DisplayPort adapter.

Nothing has been installed on the Mac. Do not install, repartition or change boot settings without the owner's explicit approval.

## Naming

- "Kealy" is the user-facing name: installer / boot-picker OS name (`arch_m3/build.py`), README, this folder (renamed from `arch-m3` on 2026-11-11).
- Keep upstream identifiers: `linux-asahi`, `m1n1`, `uboot-asahi`, `arch-m3-minimal.zip`, the `arch_m3` Python package, overlay paths. The boot chain, pacman and the handoff checks depend on them.
- Keep upstream licence and copyright notices.
- `evidence/` logs still contain the old `/Volumes/Fentz_SSD_A/Coding/arch-m3` path. They are historical records; leave them.
- The built image in `artifacts/minimal-evaluation-r2/` still carries the old OS name until the next rebuild.

## Upstream state (checked 2026-11-11)

- Current image ships `linux-asahi 7.2.12.asahi3-1`, from before M3 display-controller (DCP) support.
- DCP on M3: merged into `AsahiLinux/linux` branch `asahi-wip` on 2026-10-28 (from PR #608, mixed with #607), tested by the maintainer on J504. Needs m1n1 with PR `AsahiLinux/m1n1#746` (merged 2026-11-01).
- USB-C DisplayPort on M3: open, unreviewed PR `AsahiLinux/linux#662` by a-ramses, branch `a-ramses:t8122-displayport`, base `asahi-wip`. Depends on open PRs #659 (DCP 14.7 reply handling), #660 (tipd SPMI), #661 (RTKit startup).
- The four commits that matter in #662:
  - `a9b7aedf4a` phy: apple: atc: Add T8122 DisplayPort support (`drivers/phy/apple/atc.c`, +630/-37)
  - `76787b6781` usb: typec: tipd: Forward DisplayPort hotplug events
  - `7c396d2af2` drm: apple: Handle newer ATC PHY graph endpoints
  - `db468ac9c9` arm64: dts: apple: Enable J514s USB-C display output (`t6030-j514s.dts`, +73)
- #662 wires only J514s (M3 Pro 14"). J504 wiring is missing and has to be written here, modelled on `db468ac9c9`: enable the external DCP, its DARTs and mailbox, route it through an ATC PHY and its xbar mux to a `typec` port. Which dcpext/atcphy/port/mux-index J504 uses is not yet established; read the t8122 dtsi in `asahi-wip` and the Apple device tree before guessing.
- HDMI: PR #607 reported it only works with a forced mode (EDID parsing unresolved). USB-C is the better first target.
- M3 GPU: no driver (m1n1 draws a triangle). Any desktop renders on the CPU.
- Asahi's support table still lists M3 "DP Alt Mode" and "HDMI Out" as WIP.

## Build plan

1. Fetch `asahi-wip` plus PRs #659 to #662 into a case-sensitive filesystem (this SSD is ExFAT and case-insensitive, so not here; use a Docker volume or a case-sensitive disk image).
2. Add the J504 device-tree wiring as a local patch.
3. Build the kernel as an Arch package using the Asahi Alarm `linux-asahi` PKGBUILD as the base (repo `asahi-alarm/PKGBUILDs`), keeping the package name.
4. Build or take an m1n1 that includes #746, and check its J504 handoff constraints against the kernel.
5. Rebuild the image with those packages; record hashes in `upstream.lock.json` and a new `artifacts/` directory.
6. Extend the static audit: decoded J504 DTB shows the external DCP, DARTs and PHY endpoint enabled.
7. Physical test on the Mac only after the owner approves an install.

## Risks

- J504 wiring is our own and untested; the external screen may not light up.
- #662 and its dependencies are unreviewed and may change or be rejected.
- Built-in display should be unaffected (merged and tested on J504), but this kernel is a development branch, not a release.
- Asahi does not accept AI-written code. Keep the J504 patch local; do not submit it upstream.

## Status update (2026-11-11, later the same day)

Steps 1 to 6 are implemented; step 7 (physical test) is still open.

- Kernel source: `fentz26/kealy-linux`, branch `kealy`, commit `bfe8e1e5d596`. It is `asahi-wip` at `414e55da7a0a` (7.2.14, the base the pull requests were written against) plus the 16 commits of #659 to #662 and one local commit for J504.
- m1n1: upstream main at `cf37927d6bf4`. The v2.0.0 tag predates #746.
- CI (`.github/workflows/build.yml`) builds both packages and the image on arm64 runners; `arch_m3/display.py` is the static device-tree check.

What the J504 commit does, and where each value came from:

| Item | Value | Source |
| --- | --- | --- |
| Per-port display crossbar | `mux@70304c000` (ATC0), `mux@b0304c000` (ATC1), t6020-style | This Mac's Apple device tree: `atc0-dpxbar@304C000`, `atc1-dpxbar@304C000`, compatible `atc-dpxbar,t602x` |
| Crossbar input (`mux-index`) | 1 | Apple device tree: `dcp` is `dp-switch-ufp-endpoint` 0, `dcpext` is 1. J514s uses 2 for its third controller, consistent with this numbering |
| DP PHY target (`apple,dptx-phy`) | 0 | Apple device tree: `atc0-dpphy` is `dp-switch-dfp-endpoint` 0 |
| IOMMU apertures for `dcpext` and `dispext0` | base `0x100_0000_0000`, same as the internal display | Apple device tree `vm-base`/`vm-size` of `dart-dcpext` and `dart-dispext0`. The previous placeholder values in `t8122.dtsi` did not match |
| `dcpext` alias | added | m1n1 only reserves the controller firmware for aliased nodes |
| Port | left-back USB-C (`typec0`, ATC0) | J514s wiring; the base M3 has one external controller, so only one port is wired |

Open risks specific to this wiring: nobody has run `dcpext` on a J504 under Linux, so the interrupt numbers and register ranges already in `t8122.dtsi` for it are unexercised; the HDMI port shares the same controller and stays unwired.
