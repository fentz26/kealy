"""Strict checks for a two-cold-boot, firmware-only VM lifecycle."""
import re
import uuid
from pathlib import Path


def build_uefi_args(directory, firmware_code):
    directory, firmware_code = Path(directory).resolve(), Path(firmware_code)
    files = [directory / name for name in ('root.qcow2', 'efi.qcow2', 'vars.fd')] + [firmware_code]
    for path in files:
        if path.is_symlink() or not path.is_file() or ',' in str(path) or '\n' in str(path):
            raise ValueError('Firmware boot requires regular private file inputs')
    return ['qemu-system-aarch64', '-machine', 'virt,acpi=off', '-accel', 'hvf', '-cpu', 'host',
            '-m', '1536', '-smp', '2', '-display', 'none', '-monitor', 'none', '-nic', 'none',
            '-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={firmware_code}',
            '-drive', f'if=pflash,format=raw,unit=1,file={directory / "vars.fd"}',
            '-drive', f'if=none,format=qcow2,id=root,file={directory / "root.qcow2"}',
            '-device', 'virtio-blk-device,drive=root',
            '-drive', f'if=none,format=qcow2,id=esp,file={directory / "efi.qcow2"}',
            '-device', 'virtio-blk-device,drive=esp', '-device', 'virtio-serial-device',
            '-chardev', f'socket,id=console,path={directory / "console.sock"},server=on,wait=on',
            '-device', 'virtconsole,chardev=console',
            '-serial', f'file:{directory / "firmware-console.log"}']


def firmware_boot_evidence(text):
    clean = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text).replace('\r', '')
    markers = dict(grub_banner='GNU GRUB' in clean,
                   arch_entry="Booting `Arch Linux'" in clean,
                   kernel_load='Loading Linux linux-asahi' in clean,
                   initramfs_load='Loading initial ramdisk' in clean)
    return dict(verified=all(markers.values()), markers=markers)


def evaluate_lifecycle(first, second):
    failures = []
    for phase, report, firstboot, prompted in (('first', first, 'active', True), ('second', second, 'inactive', False)):
        for field, value in {'UEFI': '1', 'FIRSTBOOT': firstboot, 'SYSTEM': 'running',
                             'FAILED_COUNT': '0', 'setup_prompt_seen': prompted, 'firmware_grub_verified': True}.items():
            if report.get(field) != value:
                failures.append(phase + ' boot failed: ' + field)
        for field in ('BOOT_ID', 'ROOT_UUID'):
            try:
                if not uuid.UUID(report.get(field, '')).int:
                    raise ValueError('zero UUID')
            except ValueError:
                failures.append(phase + ' missing/invalid UUID: ' + field)
        if not re.fullmatch('[0-9a-fA-F]{64}', report.get('SHADOW_SHA', '')):
            failures.append(phase + ' missing credential checksum')
        if not report.get('PERSIST'):
            failures.append(phase + ' missing persistence marker')
    if first.get('BOOT_ID') == second.get('BOOT_ID'):
        failures.append('Boot ID did not change')
    for field in ('ROOT_UUID', 'EFI_UUID', 'SHADOW_SHA', 'PERSIST'):
        if not first.get(field) or first[field] != second.get(field):
            failures.append('State changed across reboot: ' + field)
    return failures
