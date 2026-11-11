"""Rebuild attested disposable QEMU inputs from the pinned delivered ZIP.

No mounts, host disk devices or installation. Requires the local audit/fs-tools
Docker images. Destination must be new POSIX storage, not the project exFAT disk.
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main(destination, project):
    base, project = Path(destination).resolve(), Path(project).resolve()
    if base.exists():
        raise ValueError('Destination must be a new disposable directory')
    base.mkdir(mode=0o700)
    probe = base / '.posix-probe'
    probe.symlink_to('not-a-real-file')
    probe.unlink()
    lock = json.loads((project / 'upstream.lock.json').read_text())
    source = project / 'artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip'
    source_sha = sha(source)
    if source_sha != lock['result']['output_sha256']:
        raise ValueError('Delivered ZIP identity mismatch')
    original_root = hashlib.sha256()
    esp_files = {}
    with zipfile.ZipFile(source) as archive:
        with archive.open('root.img') as incoming, (base / 'root.img').open('xb') as outgoing:
            while block := incoming.read(1024 * 1024):
                original_root.update(block)
                outgoing.write(block)
        for name in ('esp/EFI/BOOT/BOOTAA64.EFI', 'esp/m1n1/boot.bin'):
            data = archive.read(name)
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            esp_files[name] = hashlib.sha256(data).hexdigest()
    packages = json.loads((project / 'evidence/hardware-package-identities.json').read_text())
    identities = {}
    for package in packages:
        if package['name'] not in ('linux-asahi', 'm1n1'):
            continue
        path = project / 'upstream/packages' / package['file']
        if sha(path) != package['sha256']:
            raise ValueError('Signed package input identity mismatch')
        identities[package['name']] = package['sha256']
        if package['name'] == 'linux-asahi':
            with tarfile.open(path) as archive:
                member = next(m for m in archive if m.name.endswith('/vmlinuz'))
                (base / 'Image').write_bytes(archive.extractfile(member).read())
        else:
            validation = base / 'validation'
            validation.mkdir()
            shutil.copyfile(path, validation / 'm1n1.pkg.tar.xz')
            shutil.copyfile(str(path) + '.sig', validation / 'm1n1.pkg.tar.xz.sig')
    mount = f'type=bind,source={base},target=/vm'
    def docker(image, command, log):
        with (base / log).open('wb') as output:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
                            '--mount', mount, '--entrypoint', 'sh', image, '-c', command],
                           stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)
    docker('arch-m3-audit:local', 'debugfs -R "dump /boot/initramfs-linux-asahi.img /vm/initramfs.img" /vm/root.img', 'initrd-extraction.log')
    initrd = (base / 'initramfs.img').read_bytes()
    offset = initrd.find(b'\x1f\x8b\x08')
    if offset != 10240:
        raise ValueError('Unexpected pinned initramfs archive layout')
    (base / 'initramfs-main').write_bytes(initrd[offset:])
    with (base / 'efi.img').open('xb') as output:
        output.truncate(524288000)
    docker('arch-m3-fs-tools:local', 'mkfs.fat -F 32 -i 2abf9f91 /vm/efi.img && mcopy -s -i /vm/efi.img /vm/esp/* /vm/validation ::', 'efi-preparation.log')
    subprocess.run([sys.executable, str(project / 'tests/prepare_vm_fixture.py'), str(base), str(project), '--with-efi'],
                   check=True, timeout=30)
    docker('arch-m3-audit:local', 'debugfs -w -f /vm/fixture.commands /vm/root.img && e2fsck -fy /vm/root.img', 'root-adaptation.log')
    record = dict(source_zip_sha256=source_sha, source_root_sha256=original_root.hexdigest(),
                  signed_package_sha256=identities, original_efi_sha256=esp_files,
                  fixture_files_sha256={name: sha(base / name) for name in (
                      'root.img', 'efi.img', 'Image', 'initramfs-virtio-test.img', 'fixture.commands',
                      'fstab', 'password.service', 'hvc0.conf')},
                  adaptations=['signed virtio MMIO module in aligned initramfs overlay',
                               'hvc0 password/getty mapping and tty1 getty mask',
                               'host UTC clock fixture', 'disposable EFI disk with upstream files and signature test input'],
                  physical_disk_modified=False, delivered_zip_modified=False)
    (base / 'vm-preparation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
