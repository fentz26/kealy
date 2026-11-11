#!/bin/bash
# Install locally built packages into a copy of the pinned upstream image.
#
# Works only on private copies inside a temporary directory: the root image is
# loop-mounted from a regular file and the EFI tree is a plain directory. It
# never touches a host disk. Needs root on a native aarch64 Linux host (CI).
#
# Usage: upgrade-image.sh BASE_ZIP PACKAGE_DIR OUTPUT_ZIP REPORT_JSON
set -euo pipefail

if [ "$#" -ne 4 ]; then
    echo "usage: $0 BASE_ZIP PACKAGE_DIR OUTPUT_ZIP REPORT_JSON" >&2
    exit 2
fi
base=$(readlink -f "$1")
pkgdir=$(readlink -f "$2")
out=$(readlink -f "$3")
report=$(readlink -f "$4")

[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }
[ "$(uname -m)" = aarch64 ] || { echo "needs a native aarch64 host" >&2; exit 1; }
[ ! -e "$out" ] || { echo "output already exists: $out" >&2; exit 1; }

mapfile -t kernel < <(find "$pkgdir" -maxdepth 1 -name 'linux-asahi-[0-9]*.pkg.tar.*' ! -name '*.sig')
mapfile -t m1n1 < <(find "$pkgdir" -maxdepth 1 -name 'm1n1-[0-9]*.pkg.tar.*' ! -name '*.sig')
[ "${#kernel[@]}" -eq 1 ] || { echo "expected exactly one linux-asahi package" >&2; exit 1; }
[ "${#m1n1[@]}" -eq 1 ] || { echo "expected exactly one m1n1 package" >&2; exit 1; }

work=$(mktemp -d /var/tmp/kealy-upgrade.XXXXXX)
mnt="$work/mnt"
mounted=()
cleanup() {
    set +e
    for ((i = ${#mounted[@]} - 1; i >= 0; i--)); do
        umount -R "${mounted[$i]}" 2>/dev/null || umount -l "${mounted[$i]}"
    done
    rm -rf "$work"
}
trap cleanup EXIT

echo "== Extracting base image"
mkdir -p "$work/src" "$mnt"
unzip -q "$base" -d "$work/src"
img="$work/src/root.img"
esp="$work/src/esp"
[ -f "$img" ] && [ -f "$esp/m1n1/boot.bin" ] || { echo "unexpected base layout" >&2; exit 1; }
old_boot_sha=$(sha256sum "$esp/m1n1/boot.bin" | cut -d' ' -f1)

e2fsck -fy "$img" || [ "$?" -le 1 ]

echo "== Mounting private copies"
mount -o loop "$img" "$mnt"; mounted+=("$mnt")
mkdir -p "$mnt/boot/efi"
mount --bind "$esp" "$mnt/boot/efi"; mounted+=("$mnt/boot/efi")
mount -t proc proc "$mnt/proc"; mounted+=("$mnt/proc")
mount -t sysfs -o ro sys "$mnt/sys"; mounted+=("$mnt/sys")
mount --rbind /dev "$mnt/dev"; mount --make-rslave "$mnt/dev"; mounted+=("$mnt/dev")
mount -t tmpfs tmpfs "$mnt/run"; mounted+=("$mnt/run")
mount -t tmpfs tmpfs "$mnt/tmp"; mounted+=("$mnt/tmp")

free_kb=$(df -k --output=avail "$mnt" | tail -1)
echo "Free space in root image: $((free_kb / 1024)) MiB"
[ "$free_kb" -ge 716800 ] || { echo "less than 700 MiB free in the root image" >&2; exit 1; }

in_root() { chroot "$mnt" /usr/bin/env -i PATH=/usr/bin:/usr/sbin HOME=/root LC_ALL=C "$@"; }

before=$(in_root pacman -Q linux-asahi m1n1 uboot-asahi asahi-scripts)
echo "== Before"; echo "$before"

echo "== Installing packages"
stage="$mnt/var/cache/kealy-packages"
mkdir -p "$stage"
cp "${kernel[0]}" "${m1n1[0]}" "$stage/"
# Local files only: no repository sync, no network use inside the image.
in_root pacman -U --noconfirm \
    "/var/cache/kealy-packages/$(basename "${m1n1[0]}")" \
    "/var/cache/kealy-packages/$(basename "${kernel[0]}")"
rm -rf "$stage"

echo "== Regenerating initramfs"
echo "mkinitcpio HOOKS: $(grep -E '^HOOKS=' "$mnt/etc/mkinitcpio.conf" || true)"
skip=()
# autodetect would tailor the initramfs to the build host instead of the Mac.
if grep -Eq '^HOOKS=.*\bautodetect\b' "$mnt/etc/mkinitcpio.conf" \
        "$mnt"/etc/mkinitcpio.conf.d/*.conf 2>/dev/null; then
    skip=(-S autodetect)
fi
in_root mkinitcpio -P "${skip[@]}"

echo "== Rebuilding the m1n1 boot bundle"
[ -e "$mnt/etc/default/update-m1n1" ] && cat "$mnt/etc/default/update-m1n1"
in_root update-m1n1 /boot/efi/m1n1/boot.bin
rm -f "$esp/m1n1/boot.bin.old"
new_boot_sha=$(sha256sum "$esp/m1n1/boot.bin" | cut -d' ' -f1)
[ "$new_boot_sha" != "$old_boot_sha" ] || { echo "boot bundle did not change" >&2; exit 1; }

kver=$(basename "$(ls -d "$mnt"/usr/lib/modules/*kealy*)")
dtb=$(find "$mnt/usr/lib/modules/$kver/dtbs" -name t8122-j504.dtb | head -1)
[ -n "$dtb" ] || { echo "J504 device tree missing from the kernel package" >&2; exit 1; }
python3 - "$dtb" "$esp/m1n1/boot.bin" "$mnt/usr/lib/asahi-boot/m1n1.bin" <<'EOF'
import sys
dtb, boot, m1n1 = (open(p, 'rb').read() for p in sys.argv[1:4])
assert dtb in boot, 'new J504 device tree is not in the boot bundle'
assert boot.startswith(m1n1), 'boot bundle does not start with the installed m1n1'
print('boot bundle contains the new m1n1 and J504 device tree')
EOF
for f in vmlinuz-linux-asahi initramfs-linux-asahi.img; do
    [ -s "$mnt/boot/$f" ] || { echo "missing /boot/$f" >&2; exit 1; }
    grep -q "/boot/$f" "$mnt/boot/grub/grub.cfg" || grep -q "/$f" "$mnt/boot/grub/grub.cfg" \
        || { echo "GRUB does not reference $f" >&2; exit 1; }
done

echo "== Holding the kernel package"
# A plain system upgrade would replace this kernel with the stock one, which
# does not carry the J504 USB-C display patches yet.
conf="$mnt/etc/pacman.conf"
if grep -Eq '^IgnorePkg' "$conf"; then
    echo "pacman.conf already has an active IgnorePkg line" >&2; exit 1
fi
grep -Eq '^#IgnorePkg' "$conf" || { echo "unexpected pacman.conf layout" >&2; exit 1; }
sed -i '0,/^#IgnorePkg.*/s//IgnorePkg   = linux-asahi linux-asahi-headers/' "$conf"
grep -E '^IgnorePkg' "$conf"
cat > "$mnt/etc/kealy-release" <<EOF
Kealy: minimal Arch Linux ARM for the base M3 MacBook Pro (J504)
https://github.com/fentz26/kealy

Kernel: linux-asahi $(in_root pacman -Q linux-asahi | cut -d' ' -f2)
  source https://github.com/fentz26/kealy-linux
  Experimental USB-C DisplayPort output on the left-back port.

/etc/pacman.conf holds linux-asahi back (IgnorePkg) so that a system upgrade
does not replace this kernel with the stock Asahi Alarm kernel. Once the stock
kernel supports USB-C displays on the M3, remove that IgnorePkg line and run
a full upgrade to return to stock packages.
EOF
chmod 644 "$mnt/etc/kealy-release"

after=$(in_root pacman -Q linux-asahi m1n1 uboot-asahi asahi-scripts)
echo "== After"; echo "$after"

echo "== Cleaning up"
rm -f "$mnt"/var/cache/pacman/pkg/* "$mnt/var/log/pacman.log"
rm -rf "$mnt"/root/.cache "$mnt"/root/.gnupg
sync
fstrim "$mnt" || true
for ((i = ${#mounted[@]} - 1; i >= 0; i--)); do umount -R "${mounted[$i]}"; done
mounted=()
e2fsck -fy "$img" || [ "$?" -le 1 ]
e2fsck -fn "$img"

echo "== Packing"
(cd "$work/src" && zip -q -1 -r "$out" esp root.img)
python3 - "$report" "$base" "$out" "$old_boot_sha" "$new_boot_sha" "$kver" \
    "${kernel[0]}" "${m1n1[0]}" "$before" "$after" <<'EOF'
import hashlib, json, os, sys
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()
report, base, out, old_boot, new_boot, kver, kernel, m1n1, before, after = sys.argv[1:]
json.dump({
    'base_sha256': sha(base), 'upgraded_sha256': sha(out),
    'kernel_release': kver,
    'packages': {os.path.basename(p): sha(p) for p in (kernel, m1n1)},
    'versions_before': dict(l.split() for l in before.splitlines()),
    'versions_after': dict(l.split() for l in after.splitlines()),
    'boot_bundle_sha256': {'before': old_boot, 'after': new_boot},
    'held_packages': ['linux-asahi', 'linux-asahi-headers'],
}, open(report, 'w'), indent=2)
print(open(report).read())
EOF
echo "Wrote $out"
