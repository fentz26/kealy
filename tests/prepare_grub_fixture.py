"""Clone verified VM parents and adapt GRUB only for virtual hardware testing."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main(source, destination):
    source, base = Path(source).resolve(), Path(destination).resolve()
    if base.exists():
        raise ValueError('GRUB fixture destination must be new')
    preparation = json.loads((source / 'vm-preparation.json').read_text())
    for name in ('root.img', 'efi.img', 'Image', 'initramfs-virtio-test.img'):
        if sha(source / name) != preparation['fixture_files_sha256'][name]:
            raise ValueError('Attested parent changed: ' + name)
    base.mkdir(mode=0o700)
    for source_name, target in (('root.img', 'root-base.img'), ('efi.img', 'efi-base.img')):
        subprocess.run(['cp', '-c', str(source / source_name), str(base / target)], check=True)
    shutil.copyfile(source / 'initramfs-virtio-test.img', base / 'vm-initramfs.img')
    def docker(command, log):
        with (base / log).open('wb') as output:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--cap-drop', 'ALL',
                            '--mount', f'type=bind,source={base},target=/vm', '--entrypoint', 'sh',
                            'arch-m3-audit:local', '-c', command], check=True, stdout=output,
                           stderr=subprocess.STDOUT, timeout=120)
    docker('debugfs -R "dump /etc/default/grub /vm/grub-default.original" /vm/root-base.img; debugfs -R "dump /boot/grub/grub.cfg /vm/grub-config.original" /vm/root-base.img', 'read-grub.log')
    defaults = (base / 'grub-default.original').read_text()
    lines = []
    found = False
    for line in defaults.splitlines():
        if line.startswith('GRUB_CMDLINE_LINUX_DEFAULT='):
            if not line.endswith('"'):
                raise ValueError('Unexpected GRUB defaults syntax')
            line = line[:-1] + ' console=hvc0"'
            found = True
        lines.append(line)
    if not found:
        raise ValueError('GRUB kernel defaults missing')
    (base / 'grub-default.vm').write_text('\n'.join(lines) + '\n')
    config = (base / 'grub-config.original').read_text()
    config = '\n'.join(line + ' console=hvc0' if line.lstrip().startswith('linux\t') or line.lstrip().startswith('linux ') else line for line in config.splitlines()) + '\n'
    (base / 'grub-config.vm').write_text(config)
    commands = '''rm /boot/initramfs-linux-asahi.img
write /vm/vm-initramfs.img /boot/initramfs-linux-asahi.img
rm /etc/default/grub
write /vm/grub-default.vm /etc/default/grub
rm /boot/grub/grub.cfg
write /vm/grub-config.vm /boot/grub/grub.cfg
'''
    (base / 'adapt-grub.commands').write_text(commands)
    docker('debugfs -w -f /vm/adapt-grub.commands /vm/root-base.img && e2fsck -fy /vm/root-base.img', 'adapt-grub.log')
    code = Path('/opt/homebrew/share/qemu/edk2-aarch64-code.fd')
    shutil.copyfile('/opt/homebrew/share/qemu/edk2-arm-vars.fd', base / 'vars.fd')
    overlays = {}
    for name in ('root', 'efi'):
        parent = base / (name + '-base.img')
        overlay = base / (name + '.qcow2')
        subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw', '-b', str(parent), str(overlay)], check=True)
        info = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', str(overlay)]))
        if info['format'] != 'qcow2' or Path(info['full-backing-filename']) != parent:
            raise ValueError('Wrong overlay backing chain')
        overlays[name] = info
    record = dict(source_preparation=preparation, firmware_code=str(code), firmware_sha256=sha(code),
                  raw_parents_sha256={name: sha(base / name) for name in ('root-base.img', 'efi-base.img')},
                  adaptations=['VM initramfs placed inside cloned root', 'hvc0 arguments in cloned GRUB defaults/config'],
                  grub_defaults_sha256=sha(base / 'grub-default.vm'), grub_config_sha256=sha(base / 'grub-config.vm'),
                  commands_sha256=sha(base / 'adapt-grub.commands'), overlays=overlays,
                  overlay_initial_sha256={name: sha(base / (name + '.qcow2')) for name in ('root', 'efi')}, vars_initial_sha256=sha(base / 'vars.fd'), original_artifact_changed=False)
    (base / 'grub-preparation.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
