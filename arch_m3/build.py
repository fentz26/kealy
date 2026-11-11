"""Build an offline minimal derivative; never install to a disk or mount a device."""
import argparse
import copy
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .audit import AuditError, Ext4Reader, digest, inspect_archive


def lock_shadow(text):
    lines = text.splitlines()
    roots = [i for i, line in enumerate(lines) if line.startswith('root:')]
    if len(roots) != 1:
        raise ValueError('Expected exactly one root account')
    for index, line in enumerate(lines):
        parts = line.split(':')
        if len(parts) != 9:
            raise ValueError('Malformed shadow entry')
        if parts[0] == 'root' or (parts[1] and not parts[1].startswith(('!', '*'))):
            parts[1] = '!'
            lines[index] = ':'.join(parts)
    return '\n'.join(lines) + '\n'


def corrected_metadata(original, root_bytes):
    if root_bytes <= 0 or root_bytes % 4096:
        raise ValueError('Root size must be a positive 4KiB multiple')
    products = [x for x in original['os_list'] if x.get('name') == 'Asahi Alarm Minimal']
    if len(products) != 1:
        raise ValueError('Expected one upstream ext4 minimal product')
    product = copy.deepcopy(products[0])
    roots = [p for p in product['partitions'] if p.get('image') == 'root.img']
    if len(roots) != 1 or not roots[0].get('expand'):
        raise ValueError('Unexpected upstream root partition contract')
    roots[0]['size'] = str(root_bytes) + 'B'
    product['name'] = product['default_os_name'] = 'Kealy'
    product['package'] = 'arch-m3-minimal.zip'
    return {'os_list': [product]}


def overlay_entries(root):
    """Skip AppleDouble entries before stat; external-volume metadata may deny it."""
    for entry in sorted(os.scandir(root), key=lambda e: e.name):
        if entry.name.startswith('._') or entry.name == '.DS_Store':
            continue
        path = Path(entry.path)
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError('Overlay must contain regular files and directories only')
        yield path
        if entry.is_dir():
            yield from overlay_entries(path)


def make_overlay_commands(overlay, shadow):
    overlay = Path(overlay).resolve()
    shadow = Path(shadow).resolve()
    entries = list(overlay_entries(overlay))
    required = ('etc/systemd/system/arch-m3-root-password.service',
                'etc/systemd/system/getty@tty1.service.d/10-root-password.conf',
                'usr/local/lib/arch-m3/set-root-password')
    if not all((overlay / name) in entries and (overlay / name).is_file()
               and (overlay / name).stat().st_size > 0 for name in required):
        raise ValueError('Incomplete password-provisioning overlay')
    # debugfs is a command interpreter: all constructed arguments are restricted.
    safe_path = re.compile(r'/[A-Za-z0-9_./@+-]+')
    if not safe_path.fullmatch(str(shadow)):
        raise ValueError('Unsafe staging path')
    commands = []
    dirs = set()
    for source in overlay_entries(overlay):
        if source.is_symlink() or not (source.is_file() or source.is_dir()):
            raise ValueError('Overlay must contain regular files and directories only')
        relative = source.relative_to(overlay)
        dest = '/' + relative.as_posix()
        if not safe_path.fullmatch(str(source)) or not safe_path.fullmatch(dest):
            raise ValueError('Unsafe overlay path')
        if source.is_dir():
            dirs.add(dest)
        else:
            for parent in relative.parents:
                if str(parent) != '.':
                    dirs.add('/' + parent.as_posix())
    for directory in sorted(dirs, key=lambda x: (x.count('/'), x)):
        commands.append('mkdir ' + directory)
    for source in overlay_entries(overlay):
        if source.is_file():
            dest = '/' + source.relative_to(overlay).as_posix()
            commands.extend(['rm ' + dest, f'write {source} {dest}',
                             f'set_inode_field {dest} mode ' + ('0100755' if dest.startswith('/usr/local/lib/') else '0100644'),
                             f'set_inode_field {dest} uid 0', f'set_inode_field {dest} gid 0'])
    commands += ['rm /etc/shadow', f'write {shadow} /etc/shadow',
                 'set_inode_field /etc/shadow mode 0100600',
                 'set_inode_field /etc/shadow uid 0', 'set_inode_field /etc/shadow gid 0']
    for unit in ('sshd.service', 'sshd.socket', 'sshd@.service'):
        commands.extend([f'rm /etc/systemd/system/multi-user.target.wants/{unit}',
                         f'rm /etc/systemd/system/sockets.target.wants/{unit}',
                         f'rm /etc/systemd/system/{unit}',
                         f'symlink /etc/systemd/system/{unit} /dev/null'])
    commands.extend(['rm /etc/systemd/system/default.target',
                     'symlink /etc/systemd/system/default.target /usr/lib/systemd/system/multi-user.target',
                     'rm /etc/machine-id', 'rm /var/lib/systemd/random-seed',
                     'rm /etc/arch-m3-root-password-set'])
    return commands


def build(source, metadata, overlay, output, expected_sha256, boot_chain='unchanged from source'):
    source, output = Path(source).resolve(), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Output must be a new directory')
    # Only create files in a normal user-selected directory, never a device path.
    output = output.resolve()
    if any(output == Path(p) or Path(p) in output.parents for p in ('/dev', '/proc', '/sys')):
        raise ValueError('Refusing a device/system output path')
    report = inspect_archive(source, expected_sha256)
    corrected = corrected_metadata(json.loads(Path(metadata).read_text()), report['root_bytes'])
    make_overlay_commands(overlay, Path('/tmp/shadow-preflight'))
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='arch-m3-build-') as directory:
        directory = Path(directory)
        image = directory / 'root.img'
        with zipfile.ZipFile(source) as archive:
            with archive.open('root.img') as src, image.open('wb') as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
        fs = Ext4Reader(image)
        shadow = directory / 'shadow'
        shadow.write_text(lock_shadow(fs.read('/etc/shadow')))
        shadow.chmod(0o600)
        commands = directory / 'overlay.commands'
        commands.write_text('\n'.join(make_overlay_commands(overlay, shadow)) + '\n')
        with (output / 'debugfs.log').open('wb') as log:
            subprocess.run(['debugfs', '-w', '-f', str(commands), str(image)],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        # debugfs can return success when an individual command fails. Read back
        # every intended security/boot change before producing a ZIP.
        if fs.link('/etc/systemd/system/default.target') != '/usr/lib/systemd/system/multi-user.target':
            raise AuditError('Console target change failed')
        if fs.read('/etc/shadow') != shadow.read_text():
            raise AuditError('Root password locking failed')
        for unit in ('sshd.service', 'sshd.socket', 'sshd@.service'):
            if fs.link('/etc/systemd/system/' + unit) != '/dev/null':
                raise AuditError('SSH mask failed')
        for path in overlay_entries(Path(overlay)):
            if path.is_file():
                if fs.read('/' + path.relative_to(overlay).as_posix(), binary=True) != path.read_bytes():
                    raise AuditError('Overlay readback failed: ' + str(path))
        for operation, accepted in [(['e2fsck', '-fy', str(image)], (0, 1)),
                                    (['e2fsck', '-fn', str(image)], (0,))]:
            with (output / 'filesystem-check.log').open('ab') as log:
                checked = subprocess.run(operation, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            if checked.returncode not in accepted:
                raise AuditError('Filesystem check failed')
        # Recheck permissions and scrubbed identity after filesystem repair.
        for path in overlay_entries(Path(overlay)):
            if path.is_file():
                dest = '/' + path.relative_to(overlay).as_posix()
                inode = fs.inode(dest)
                expected_mode = 0o755 if dest.startswith('/usr/local/lib/') else 0o644
                if not inode or (inode['mode'], inode['uid'], inode['gid']) != (expected_mode, 0, 0):
                    raise AuditError('Incorrect overlay permissions: ' + dest)
        inode = fs.inode('/etc/shadow')
        if not inode or (inode['mode'], inode['uid'], inode['gid']) != (0o600, 0, 0):
            raise AuditError('Incorrect shadow permissions')
        for scrubbed in ('/etc/machine-id', '/var/lib/systemd/random-seed', '/etc/arch-m3-root-password-set'):
            if fs.inode(scrubbed) is not None:
                raise AuditError('Identity/provisioning marker was not scrubbed: ' + scrubbed)
        (output / 'os').mkdir()
        target = output / 'os' / 'arch-m3-minimal.zip'
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as result:
            for member in original.infolist():
                if member.filename == 'root.img':
                    result.write(image, 'root.img')
                else:
                    result.writestr(member, original.read(member.filename))
        corrected_path = output / 'installer_data.json'
        corrected_path.write_text(json.dumps(corrected, indent=2) + '\n')
        provenance = {'source_sha256': report['sha256'], 'output_sha256': digest(target),
                      'root_bytes': report['root_bytes'], 'boot_chain': boot_chain,
                      'status': 'evaluation artifact; not hardware boot qualified',
                      'encrypted': False, 'desktop_preinstalled': False}
        (output / 'build.json').write_text(json.dumps(provenance, indent=2) + '\n')
        return provenance


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--overlay', type=Path, default=Path('overlay'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--boot-chain', default='unchanged from source',
                   help='Provenance note for the kernel/m1n1/U-Boot in the source ZIP')
    args = p.parse_args()
    print(json.dumps(build(args.source, args.metadata, args.overlay, args.output, args.sha256,
                           args.boot_chain), indent=2))


if __name__ == '__main__':
    main()
