# Minimal Arch M3 work ledger

User authorized substantive local research/build work and explicitly wants minimal Arch-style console first, desktop/rice later. No installation authorization.

Ruling: work in the explicitly requested new project directory on a dedicated branch; no pre-existing code or branch to isolate.
Ruling: prefer validating the published minimal product before custom assembly; this reduces unnecessary maintenance while preserving the desired Arch experience.

Active: Task 1, inspect published installer and minimal image. Docker Desktop start requested locally to establish a disposable Linux runner; no host disk devices will be passed to containers.

Task 1: published installer v0.9.2 explicitly admits j504ap/T8122 firmware 14.8.3. Downloaded 1,355,729,315-byte minimal ZIP; local SHA256 61153885581ca93bf7fbc05147146503b0b2de15355f207f0c04e56a78f03954. Local hash is identity, not an upstream signature.
Task 2: initial 10 archive/policy tests RED (missing module) -> GREEN. Real offline audit found 261 packages, linux-asahi 7.2.12.asahi3-1, m1n1 1.9.9-1, U-Boot 2026.07.asahi2-1; J504 DTB exactly present in boot.bin. No requested desktop/runtime packages. SSH enabled and root unlocked; explicit default target absent.
Ruling: derivative changes only credentials, SSH enablement, explicit console target and metadata size; preserve stock boot/kernel bytes. No Aurora substitution without a demonstrated console boot gap. Cost if wrong: stock M3 limitations remain; no claim of hardware qualification or accelerated Hyprland.
Ruling: use a local root-password prompt, then ordinary manual useradd/pacman setup; no custom desktop/account wizard. Image has no default usable password and SSH is masked. Initial evaluation image unencrypted and not yet qualified for installation.
Ruling: Docker Desktop is now running and aarch64 containers work. Read-only image inspection needs no privileged container, mount or host disk device.

Task 3: built artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip. Root filesystem and EFI payload assembled without mounts or privileged containers. Source and output digests recorded in upstream.lock.json and build.json. e2fsck -fy and subsequent -fn succeeded.
Review fixes: empty provisioning overlay now fails preflight; output ZIP is under os/ to match engine resolution; mode/owner and scrubbed markers checked after filesystem repair; boot checks use actual UUID, active GRUB/fstab entries and real kernel/initramfs headers. All were covered by new failing tests followed by passing tests. Strict derivative policy additionally checks all credential locks and SSH masks.
Task 4 verification: 23 portable tests pass. Strict artifact audit passes. Signed DTB/m1n1/U-Boot bundle comparisons and kernel hash comparison pass. Final interactive userspace test subsequently passed; see completion below.
Ruling: a full generic QEMU virt serial boot is not a valid drop-in test for this stock kernel (PL011 driver disabled). Test real userspace/password helper in a disposable chroot; do not represent that as a VM boot or hardware qualification.
Test-environment findings: external-volume AppleDouble files need filtering before stat; compile checks must name Python files rather than compile AppleDouble metadata. A chroot needs an empty proc/cmdline fixture for systemd-firstboot, and its preserved proc directory needs temporary fixture write permission. Test driver must recognize the installed firstboot's 'root password again' confirmation. These are test fixture corrections, not changes to the artifact's password helper.

Task 4: complete for the local evaluation-build scope. Real image helper tests PASS: skipped password fails closed, private password completes, marker0600, repeat preserves password. Actual image systemd-analyze verify and pacman -Dk PASS in disposable chroot. Strict artifact audit and signed kernel/device-tree/boot bundle comparisons PASS. Hardware boot and accelerated desktop support explicitly unverified. No external publication or installation performed.
Final review: fresh reviewer found four Important issues, all addressed with RED-to-GREEN tests plus real artifact readback. No known deferred minor findings. Preserve this standalone local branch; there is no base branch or remote to merge/publish.

Continuation: user requested further work. Scope is read-only/preparatory installer handoff and deeper boot tests, not physical install. Plan: docs/superpowers/plans/2026-11-11-handoff-validation.md.
Observed project volume is exFAT. Full published installer contains 37 symlinks, so any future native runtime extraction must use POSIX/APFS staging, not direct exFAT extraction.
The kernel does have CONFIG_VIRTIO_CONSOLE=y. Investigate virtio-console QEMU boot instead of assuming missing PL011 rules out every same-kernel VM test.

Continuation results: 34 portable tests pass. Native host preflight passed; pinned published engine accepted the local payload and descriptor, calculated min/recommended sizes and extracted EFI under an audit guard. The same test passed under the staged bundled Python 3.13.9, whose SSL and ctypes imports also pass. APFS staging is /private/tmp/arch-m3-handoff-reviewed; no installer main was invoked.
Review fix: reject unknown operational metadata, extra downloads, EFI expansion, root formatting/source overrides and altered EFI volume identity. Six regression mutations first passed incorrectly, then were rejected after the fix; full suite green. Existing artifact bytes unchanged.
VM result: bounded same-kernel QEMU/HVF attempt did not reach console/login. Stock initramfs lacks the modular virtio MMIO transport despite built-in virtio console. Do not claim VM or physical hardware boot. Kernel-memory diagnostic search did not establish a reliable runtime failure message; do not infer an exact panic cause from register text alone.
Ruling: leave the stock artifact unchanged rather than alter its initramfs for generic virtual hardware. Cost: no full VM boot evidence; physical qualification remains a separate stage. Staging is preparation only and does not authorize installation.

Final continuation verification: 34 portable tests PASS; published engine contract PASS under host and bundled Python; model/artifact preflight PASS; APFS runtime staging and native SSL/ctypes load PASS. Known failing integration: tests/integration_vm.py timed out before authenticated console even with explicit test-only virtio transport, hvc0 service mapping and no Apple EFI mount. Empty console log; no claimed VM boot. Full hardware/boot readiness remains unproved. Keep the stock delivered ZIP unchanged and preserve the failure evidence rather than imply a pass.
