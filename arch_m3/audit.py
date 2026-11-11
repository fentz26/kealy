"""Inspect installer ZIPs without mounting filesystems or executing their files."""
import argparse
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
import uuid
from pathlib import Path, PurePosixPath


class AuditError(ValueError):
    """The artifact does not satisfy the minimal image contract."""


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def inspect_archive(path, expected_sha256=None):
    sha = digest(path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise AuditError('Artifact SHA-256 does not match the pinned identity')
    with zipfile.ZipFile(path) as archive:
        names = set()
        members = []
        for member in archive.infolist():
            p = PurePosixPath(member.filename)
            if (p.is_absolute() or '..' in p.parts or '\\' in member.filename
                    or '\x00' in member.filename or member.filename in names):
                raise AuditError('Unsafe or duplicate ZIP member')
            if stat.S_ISLNK(member.external_attr >> 16):
                raise AuditError('ZIP symlinks are not allowed')
            names.add(member.filename)
            members.append({'path': member.filename, 'bytes': member.file_size})
        required = {'root.img', 'esp/EFI/BOOT/BOOTAA64.EFI', 'esp/m1n1/boot.bin'}
        if not required <= names:
            raise AuditError('Missing root or Apple EFI boot chain')
        root_size = archive.getinfo('root.img').file_size
        if not 2048 <= root_size <= 16 * 1024**3:
            raise AuditError('Unexpected root image size')
        with archive.open('root.img') as root:
            header = root.read(2048)
        if header[1080:1082] != b'\x53\xef':
            raise AuditError('This auditor requires an ext4 root image')
    return {'sha256': sha, 'root_bytes': root_size, 'filesystem': 'ext4',
            'root_uuid': str(uuid.UUID(bytes=header[1128:1144])),
            'members': members, 'trust': 'local digest; not an upstream signature'}


def evaluate_system(system, derivative=False):
    failures = []
    warnings = []
    packages = system['packages']
    for required in ('base', 'pacman', 'linux-asahi', 'm1n1', 'uboot-asahi', 'networkmanager'):
        if required not in packages:
            failures.append('Missing package: ' + required)
    desktops = {'hyprland', 'omarchy', 'omarchy-dev', 'sddm', 'gdm', 'gnome-shell',
                'plasma-workspace', 'lightdm'}
    for package in sorted(desktops & packages.keys()):
        failures.append('Not a minimal console image: ' + package)
    for key in ('board_dtb', 'board_dtb_in_boot_bundle', 'kernel', 'initramfs', 'grub_root_uuid'):
        if not system.get(key):
            failures.append('Missing or invalid: ' + key)
    if system.get('default_target') != 'multi-user.target':
        failures.append('Default boot target is not multi-user.target')
    if system.get('sshd_enabled'):
        warnings.append('SSH is enabled in the initial image')
    if not system.get('root_password_locked'):
        warnings.append('Root password is not locked; set private credentials before network use')
    if derivative:
        for key in ('root_password_locked', 'all_passwords_locked'):
            if not system.get(key):
                failures.append('Derivative credential policy failed: ' + key)
        if system.get('sshd_enabled') or any(system.get('ssh_masks', {}).get(unit) != '/dev/null'
                for unit in ('sshd.service', 'sshd.socket', 'sshd@.service')):
            failures.append('Derivative SSH must be disabled and masked')
        if system.get('provisioning_marker_present', True):
            failures.append('Derivative already has a provisioning marker')
        for key, mode in (('provisioning_helper', 0o755), ('shadow_inode', 0o600)):
            info = system.get(key) or {}
            if (info.get('mode'), info.get('uid'), info.get('gid')) != (mode, 0, 0) or not info.get('size', 0):
                failures.append('Derivative file permissions invalid: ' + key)
    return {'failures': failures, 'warnings': warnings, 'hardware_boot_verified': False}


def parse_inode(text):
    mode = re.search(r'Mode:\s+([0-7]+)', text)
    owner = re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', text)
    size = re.search(r'Size:\s+(\d+)', text)
    if not mode or not owner or not size:
        return None
    return dict(mode=int(mode[1], 8), uid=int(owner[1]), gid=int(owner[2]), size=int(size[1]))


def validate_boot_config(root_uuid, fstab, grub):
    root_entries = [line.split() for line in fstab.splitlines()
                    if line.strip() and not line.lstrip().startswith('#')]
    fstab_matches = any(len(e) >= 2 and e[0] == 'UUID=' + root_uuid and e[1] == '/'
                        for e in root_entries)
    kernels, initramfs, roots = [], [], []
    for line in grub.splitlines():
        line = line.strip()
        if line.startswith(('linux ', 'linux\t')):
            parts = line.split()
            if len(parts) > 1:
                kernels.append(parts[1])
                roots.append(next((p[10:] for p in parts[2:] if p.startswith('root=UUID=')), None))
        elif line.startswith(('initrd ', 'initrd\t')):
            initramfs.extend(line.split()[1:])
    return dict(root_matches=fstab_matches and bool(roots) and all(r == root_uuid for r in roots),
                kernel_paths=sorted(set(kernels)), initramfs_paths=sorted(set(initramfs)))


class Ext4Reader:
    """Read a regular image with debugfs, with no mount or writable mode."""
    def __init__(self, image):
        self.image = Path(image)

    def run(self, command, binary=False):
        result = subprocess.run(['debugfs', '-R', command, str(self.image)],
                                capture_output=True, check=True, timeout=60)
        return result.stdout if binary else result.stdout.decode('utf-8', errors='replace')

    def read(self, path, binary=False):
        if not re.fullmatch(r'/[A-Za-z0-9_./+@:=,-]+', path) or '..' in Path(path).parts:
            raise AuditError('Invalid ext4 path')
        return self.run('cat ' + path, binary=binary)

    def ls(self, path):
        output = self.run('ls -p ' + path)
        return [line.split('/')[5] for line in output.splitlines()
                if line.startswith('/') and len(line.split('/')) > 5
                and line.split('/')[5] not in ('.', '..')]

    def inode(self, path):
        return parse_inode(self.run('stat ' + path))

    def link(self, path):
        output = self.run('stat ' + path)
        match = re.search(r'Fast link dest: "([^"]+)"', output)
        return match.group(1) if match else ''


def fields(text):
    result = {}
    key = None
    for line in text.splitlines():
        if line.startswith('%') and line.endswith('%'):
            key = line.strip('%')
            result[key] = []
        elif line and key:
            result[key].append(line)
    return result


def inspect_system(archive_path, derivative=False):
    with tempfile.TemporaryDirectory(prefix='arch-m3-audit-') as directory:
        image = Path(directory) / 'root.img'
        with zipfile.ZipFile(archive_path) as archive:
            with archive.open('root.img') as source, image.open('wb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            boot = archive.read('esp/m1n1/boot.bin')
        fs = Ext4Reader(image)
        packages = {}
        for name in fs.ls('/var/lib/pacman/local'):
            if name == 'ALPM_DB_VERSION':
                continue
            desc = fields(fs.read('/var/lib/pacman/local/' + name + '/desc'))
            if desc.get('NAME') and desc.get('VERSION'):
                packages[desc['NAME'][0]] = desc['VERSION'][0]
        kernels = fs.ls('/usr/lib/modules')
        dtb_paths = []
        board_dtbs = []
        for version in kernels:
            for suffix in ('dtbs/apple/t8122-j504.dtb', 'dtbs/t8122-j504.dtb'):
                path = '/usr/lib/modules/' + version + '/' + suffix
                value = fs.read(path, binary=True)
                if value.startswith(b'\xd0\x0d\xfe\xed'):
                    dtb_paths.append(path)
                    board_dtbs.append(value)
        grub = fs.read('/boot/grub/grub.cfg')
        fstab = fs.read('/etc/fstab')
        shadow = fs.read('/etc/shadow')
        root_entry = next((line.split(':')[1] for line in shadow.splitlines()
                           if line.startswith('root:')), None)
        with image.open('rb') as source:
            source.seek(1128)
            root_uuid = str(uuid.UUID(bytes=source.read(16)))
        boot_config = validate_boot_config(root_uuid, fstab, grub)
        kernel_data = {p: fs.read(p, binary=True) for p in boot_config['kernel_paths']}
        initramfs_data = {p: fs.read(p, binary=True) for p in boot_config['initramfs_paths']}
        kernel_ok = bool(kernel_data) and all(len(b) > 4096 and b[56:60] == b'ARMd' for b in kernel_data.values())
        ramfs_magic = (b'\x1f\x8b', b'\x28\xb5\x2f\xfd', b'070701', b'070702', b'\x04\x22\x4d\x18')
        initramfs_ok = bool(initramfs_data) and all(len(b) > 1024 and b.startswith(ramfs_magic) for b in initramfs_data.values())
        system = {
            'packages': dict(sorted(packages.items())), 'kernel_versions': kernels,
            'board': 'apple,j504', 'board_dtb_paths': dtb_paths,
            'board_dtb': bool(board_dtbs),
            'board_dtb_in_boot_bundle': bool(board_dtbs) and all(d in boot for d in board_dtbs),
            'kernel': kernel_ok, 'initramfs': initramfs_ok,
            'root_uuid': root_uuid, 'boot_references': boot_config,
            'kernel_sha256': {p: hashlib.sha256(b).hexdigest() for p, b in kernel_data.items()},
            'board_dtb_sha256': [hashlib.sha256(b).hexdigest() for b in board_dtbs],
            'grub_root_uuid': boot_config['root_matches'],
            'default_target': Path(fs.link('/etc/systemd/system/default.target')).name,
            'all_passwords_locked': all(len(line.split(':')) == 9 and line.split(':')[1].startswith(('!', '*')) for line in shadow.splitlines()),
            'ssh_masks': {u: fs.link('/etc/systemd/system/' + u) for u in ('sshd.service', 'sshd.socket', 'sshd@.service')},
            'provisioning_helper': fs.inode('/usr/local/lib/arch-m3/set-root-password'),
            'provisioning_marker_present': fs.inode('/etc/arch-m3-root-password-set') is not None,
            'shadow_inode': fs.inode('/etc/shadow'),
            'root_password_locked': root_entry is not None and root_entry.startswith(('!', '*')),
            'fstab': fstab, 'grub_config': grub,
            'sshd_enabled': 'sshd.service' in fs.ls('/etc/systemd/system/multi-user.target.wants'),
            'networkmanager_enabled': 'NetworkManager.service' in fs.ls('/etc/systemd/system/multi-user.target.wants'),
        }
        return {**system, **evaluate_system(system, derivative=derivative)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--sha256', help='Expected artifact identity (not a signature)')
    parser.add_argument('--system', action='store_true', help='Inspect ext4 with Linux debugfs')
    parser.add_argument('--derivative', action='store_true', help='Require locked credentials, masked SSH and executable provisioning')
    args = parser.parse_args()
    if args.derivative and not args.system:
        parser.error('--derivative requires --system')
    try:
        report = {'archive': inspect_archive(args.archive, args.sha256)}
        if args.system:
            report['system'] = inspect_system(args.archive, derivative=args.derivative)
        print(json.dumps(report, indent=2))
        return int(bool(report.get('system', {}).get('failures')))
    except (AuditError, zipfile.BadZipFile, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f'Audit failed: {error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
