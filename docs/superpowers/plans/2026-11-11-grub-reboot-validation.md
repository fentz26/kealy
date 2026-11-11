# GRUB and repeat-boot validation

> Execute inline in disposable VM storage. Do not install or touch host partitions/boot policy.

Goal: cover the firmware/GRUB loading path and a second cold boot after first-boot UUID regeneration.

- [x] Clone attested raw fixtures to new private POSIX storage, add the existing VM initramfs inside the cloned root and hvc0 kernel arguments to cloned GRUB defaults/config only. Record all hashes and adaptations.
- [x] Create persistent qcow2 overlays over those raw parents and a copied EDK2 variable store. All VM writes must remain in the overlays/variable-copy files. No host devices/network or direct kernel/initrd arguments.
- [x] Cold boot through EDK2 and the actual source GRUB EFI image. Provision a private test password and collect named startup, UUID, mount, GRUB and package-signature markers.
- [x] Shut down cleanly. Cold boot with the same overlays, reuse the test password held only in memory, and verify different boot IDs but stable filesystem UUIDs, credential hash and a guest persistence marker. Initial setup must not prompt again.
- [x] Check raw backing and delivered ZIP hashes unchanged, review false-positive risks, update qualification boundaries and commit evidence.

A VM pass still does not qualify Apple Recovery, m1n1/U-Boot, per-device firmware or physical peripherals. New tests must distinguish first-boot active from second-boot skipped/inactive state. Firmware and GRUB logs are separate from the Linux hvc0 console.

Completed: final two-phase firmware/GRUB lifecycle PASS with explicit shutdown and route evidence; Apple hardware qualification remains outside scope.
