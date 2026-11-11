# Root growth and J504 offline hardware audit

Continue local validation only. No real installation, host disk changes or device passthrough.

- [x] Build a new disposable GRUB fixture from attested parents. Increase only its root qcow2 virtual capacity to 12 GiB before first boot.
- [x] Boot through firmware/GRUB without manually resizing the guest filesystem. Verify the image's x-systemd.growfs path exposes the new capacity, exercise allocation/data writes, then cold boot again with state/capacity preserved.
- [x] Audit the signed J504 DTB and shipped kernel config/module/initramfs paths for display framebuffer, internal input, NVMe and Wi-Fi. Record missing/runtime-dependent firmware explicitly; no physical support claim from static presence.
- [x] Review result parsing/provenance, run relevant tests, update qualification and commit.
