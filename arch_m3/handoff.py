"""Read-only validation for a local J504 installer handoff. Never launches an installer."""
import argparse
import json
import platform
import plistlib
import posixpath
import re
import subprocess
import shutil
import tempfile
import tarfile
from pathlib import Path, PurePosixPath

from .audit import digest, inspect_archive


class HandoffError(ValueError):
    """The local host or payload is outside the reviewed handoff contract."""


def validate_host(host):
    expected = dict(system='Darwin', architecture='arm64', model='Mac15,3', board='J504AP')
    for key, value in expected.items():
        if host.get(key) != value:
            raise HandoffError('Unsupported host ' + key)
    version = host.get('macos', '')
    if not re.fullmatch(r'\d+(?:\.\d+){1,2}', version):
        raise HandoffError('Invalid macOS version')
    if tuple(map(int, version.split('.'))) < (13, 5):
        raise HandoffError('macOS is older than the reviewed installer minimum')


def read_host():
    if platform.system() != 'Darwin':
        raise HandoffError('Native macOS is required for host inspection')
    def read(*args):
        return subprocess.check_output(args, timeout=20)
    objects = plistlib.loads(read('/usr/sbin/ioreg', '-ar', '-d1', '-c', 'IOPlatformExpertDevice'))
    compatible = objects[0].get('compatible', b'')
    if isinstance(compatible, bytes):
        compatible = compatible.decode('ascii', errors='strict').split('\0')
    boards = [value for value in compatible if re.fullmatch(r'J\d+[A-Z]*AP', value)]
    if len(boards) != 1:
        raise HandoffError('Could not determine an unambiguous Apple board identifier')
    return dict(system=platform.system(), architecture=platform.machine(),
                model=read('/usr/sbin/sysctl', '-n', 'hw.model').decode().strip(),
                board=boards[0], macos=read('/usr/bin/sw_vers', '-productVersion').decode().strip())


def validate_metadata(metadata, root_bytes):
    if set(metadata) != {'os_list'}:
        raise HandoffError('Unexpected installer metadata fields')
    products = metadata.get('os_list', [])
    if len(products) != 1:
        raise HandoffError('Expected exactly one local evaluation product')
    product = products[0]
    allowed = {'name', 'default_os_name', 'package', 'boot_object', 'next_object', 'supported_fw', 'partitions', 'extras'}
    if set(product) - allowed or product.get('extras') != {}:
        raise HandoffError('Unreviewed product fields or extra downloads')
    if product.get('package') != 'arch-m3-minimal.zip':
        raise HandoffError('Only the reviewed local payload name is allowed')
    if product.get('boot_object') != 'm1n1.bin' or product.get('next_object') != 'm1n1/boot.bin':
        raise HandoffError('Unexpected Apple boot object contract')
    if '14.8.3' not in product.get('supported_fw', []):
        raise HandoffError('M3 firmware contract is missing')
    if product.get('external_boot') or product.get('expert'):
        raise HandoffError('Unexpected expert/external boot mode')
    parts = product.get('partitions', [])
    if len(parts) != 2:
        raise HandoffError('Unexpected partition contract')
    efi, root = parts
    efi_keys = {'name', 'type', 'size', 'format', 'source', 'volume_id', 'copy_firmware', 'copy_installer_data'}
    root_keys = {'name', 'type', 'size', 'image', 'expand'}
    if set(efi) - efi_keys or set(root) - root_keys:
        raise HandoffError('Unreviewed partition operations')
    if efi.get('volume_id') != '0x2abf9f91':
        raise HandoffError('EFI volume identity does not match fstab')
    if (efi.get('type'), efi.get('format'), efi.get('source')) != ('EFI', 'fat', 'esp'):
        raise HandoffError('Unexpected EFI partition contract')
    if efi.get('copy_firmware') is not True or efi.get('copy_installer_data') is not True:
        raise HandoffError('Per-device firmware/installer handoff is missing')
    if (root.get('type'), root.get('image'), root.get('expand')) != ('Linux', 'root.img', True):
        raise HandoffError('Unexpected root partition contract')
    if root.get('size') != str(root_bytes) + 'B' or root_bytes % 4096:
        raise HandoffError('Metadata root size does not match payload')
    if efi.get('size') != '524288000B':
        raise HandoffError('Unexpected EFI partition size')
    return dict(relative_payload='os/arch-m3-minimal.zip', required_firmware='14.8.3',
                root_bytes=root_bytes, efi_bytes=524288000)


def validate_tar_path(name, link=None):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:
        raise HandoffError('Installer archive path escapes staging')
    if link is not None:
        target = posixpath.normpath(str(path.parent / link))
        if PurePosixPath(link).is_absolute() or target == '..' or target.startswith('../') or '\\' in link:
            raise HandoffError('Installer archive link escapes staging')


def inspect_installer(path, expected_sha256):
    if digest(path) != expected_sha256:
        raise HandoffError('Published installer hash mismatch')
    required = {'install.sh', 'main.py', 'osinstall.py', 'util.py', 'm1n1.py', 'urlcache.py',
                'boot/m1n1.bin', 'version.tag'}
    names = set()
    sources = {}
    links = 0
    with tarfile.open(path) as archive:
        for member in archive:
            validate_tar_path(member.name, member.linkname if member.issym() else None)
            if not (member.isfile() or member.isdir() or member.issym()):
                raise HandoffError('Unsupported installer archive member type')
            name = str(PurePosixPath(member.name))
            if name in names:
                raise HandoffError('Duplicate installer archive member')
            names.add(name)
            links += int(member.issym())
            if name in required and member.isfile():
                if member.size > 8 * 1024 * 1024:
                    raise HandoffError('Unexpected installer component size')
                sources[name] = archive.extractfile(member).read()
    if not required <= sources.keys() or sources['version.tag'].strip() != b'v0.9.2':
        raise HandoffError('Incomplete or unexpected installer version')
    text = sources['main.py'].decode()
    if not re.search(r'"j504ap"\s*:\s*Device\("14\.8\.3",\s*False\)', text):
        raise HandoffError('Published installer does not admit the reviewed board')
    return dict(version='v0.9.2', sha256=expected_sha256, symlinks=links,
                staging_requires_posix_filesystem=True)


def preflight(project, host=None):
    project = Path(project).resolve()
    lock = json.loads((project / 'upstream.lock.json').read_text())
    target = dict(board='J504AP', model='Mac15,3', chip='T8122', architecture='aarch64')
    if any(lock.get(k) != v for k, v in target.items()):
        raise HandoffError('Lock file target changed')
    host = read_host() if host is None else host
    validate_host(host)
    repo = project / 'artifacts/minimal-evaluation-r2'
    payload = repo / 'os/arch-m3-minimal.zip'
    artifact = inspect_archive(payload, lock['result']['output_sha256'])
    descriptor = repo / 'installer_data.json'
    metadata = validate_metadata(json.loads(descriptor.read_text()), artifact['root_bytes'])
    installer = project / 'upstream/arch-m3-alarm-published-installer.tar.gz'
    engine = inspect_installer(installer, lock['published_installer']['sha256'])
    # This report never invokes installer main, diskutil, sudo or a disk API.
    return dict(status='local_preflight_passed_hardware_unverified', host=host,
                payload=dict(path=str(payload), sha256=artifact['sha256'], root_bytes=artifact['root_bytes']),
                metadata=dict(path=str(descriptor), sha256=digest(descriptor), **metadata),
                installer=dict(path=str(installer), **engine),
                physical_boot_verified=False, installation_started=False,
                installer_main_invoked=False, encrypted=False,
                next_boundary='Separate authorization required before real installation or boot-policy changes')


def require_posix_staging(directory):
    directory = Path(directory)
    with tempfile.NamedTemporaryFile(dir=directory, prefix='.arch-m3-probe-') as probe:
        link = Path(probe.name + '.link')
        try:
            link.symlink_to(Path(probe.name).name)
            if not link.is_symlink() or link.resolve() != Path(probe.name).resolve():
                raise HandoffError('Staging does not preserve POSIX symlinks')
        except OSError as error:
            raise HandoffError('Installer staging needs a POSIX filesystem such as APFS') from error
        finally:
            if link.is_symlink():
                link.unlink()


def stage(project, destination):
    project = Path(project).resolve()
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise HandoffError('Staging destination must be a new directory')
    report = preflight(project)
    destination = destination.resolve()
    destination.mkdir(mode=0o700)
    require_posix_staging(destination)
    runtime = destination / 'runtime'
    runtime.mkdir(mode=0o700)
    with tarfile.open(report['installer']['path']) as archive:
        archive.extractall(runtime, filter='data')
    payload_dir = runtime / 'os'
    payload_dir.mkdir(exist_ok=True)
    payload = payload_dir / 'arch-m3-minimal.zip'
    if payload.exists() or payload.is_symlink() or (runtime / 'installer_data.json').exists():
        raise HandoffError('Published runtime unexpectedly contains a local payload or descriptor')
    shutil.copyfile(report['payload']['path'], payload)
    if digest(payload) != report['payload']['sha256']:
        raise HandoffError('Staged payload copy failed identity verification')
    descriptor = runtime / 'installer_data.json'
    shutil.copyfile(report['metadata']['path'], descriptor)
    if digest(descriptor) != report['metadata']['sha256']:
        raise HandoffError('Descriptor changed during staging')
    report['staging'] = dict(directory=str(destination), runtime=str(runtime),
                             payload_sha256=report['payload']['sha256'],
                             repo_base=str(runtime), installer_launched=False,
                             extraction_filesystem='POSIX symlink probe passed')
    (destination / 'handoff.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path.cwd())
    parser.add_argument('--stage', type=Path, help='Prepare a new POSIX staging directory; does not launch installation')
    args = parser.parse_args()
    try:
        print(json.dumps(stage(args.project, args.stage) if args.stage else preflight(args.project), indent=2))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, 'Preflight rejected: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
