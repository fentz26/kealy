"""Bounded QEMU userspace boot test of an explicitly adapted virtual-hardware fixture."""
import json
import hashlib
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from vm_checks import evaluate_guest_checks, reset_result


def run(base, report_dir, accelerator="hvf", with_efi=False):
    base, report_dir = Path(base), Path(report_dir)
    reset_result(report_dir)
    if accelerator not in ("hvf", "tcg"):
        raise ValueError("Unsupported VM test accelerator")
    console = base / 'virtio-test.sock'
    if console.exists():
        console.unlink()
    args = ['qemu-system-aarch64', '-machine', 'virt', '-accel', accelerator, '-cpu', 'host' if accelerator == 'hvf' else 'max',
            '-m', '1536', '-smp', '2', '-display', 'none', '-serial', 'none', '-monitor', 'none',
            '-nic', 'none', '-kernel', str(base / 'Image'), '-initrd', str(base / 'initramfs-virtio-test.img'),
            '-drive', f'if=none,file={base / "root.img"},format=raw,id=root,snapshot=on',
            '-device', 'virtio-blk-device,drive=root', '-device', 'virtio-serial-device',
            '-chardev', f'socket,id=console,path={console},server=on,wait=on',
            '-device', 'virtconsole,chardev=console',
            '-append', 'root=UUID=725346d2-f127-47bc-b464-9dd46155e8d6 rw console=hvc0 loglevel=4']
    if with_efi:
        args += ['-drive', f'if=none,file={base / "efi.img"},format=raw,id=esp,snapshot=on', '-device', 'virtio-blk-device,drive=esp']
    project = Path(__file__).resolve().parents[1]
    signed = json.loads((project / 'evidence/signed-boot-content-comparison.json').read_text())
    expected_kernel = next(p['sha256'] for p in signed if p['member'].endswith('/vmlinuz'))
    preparation_path = base / 'vm-preparation.json'
    preparation = json.loads(preparation_path.read_text()) if preparation_path.exists() else None
    if preparation:
        expected_zip = json.loads((project / 'upstream.lock.json').read_text())['result']['output_sha256']
        assert preparation['source_zip_sha256'] == expected_zip
        for name in ('root.img', 'efi.img', 'Image', 'initramfs-virtio-test.img'):
            with (base / name).open('rb') as input_file:
                assert hashlib.file_digest(input_file, 'sha256').hexdigest() == preparation['fixture_files_sha256'][name], 'Fixture changed: ' + name
    actual_kernel = hashlib.file_digest((base / 'Image').open('rb'), 'sha256').hexdigest()
    assert actual_kernel == expected_kernel, 'VM kernel differs from signed package'
    password = secrets.token_urlsafe(24).encode()
    token = 'ARCH_M3_VM_' + secrets.token_hex(8)
    done_token = token + '_DONE'
    output = b''
    sent = set()
    socket_client = None
    with (report_dir / 'vm-fixture-qemu.log').open('wb') as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if socket_client is None:
                    try:
                        socket_client = socket.socket(socket.AF_UNIX)
                        socket_client.connect(str(console))
                        socket_client.settimeout(0.25)
                    except OSError:
                        if socket_client:
                            socket_client.close()
                        socket_client = None
                        time.sleep(0.1)
                        continue
                try:
                    data = socket_client.recv(65536)
                    if not data:
                        break
                    output += data
                    (report_dir / 'vm-fixture-console.log').write_bytes(output.replace(password, b'[redacted]'))
                except TimeoutError:
                    continue
                clean = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', output)
                lower = clean.lower()
                if re.search(rb'enter[^\r\n]*root password', lower) and 'first' not in sent:
                    socket_client.sendall(password + b'\r')
                    sent.add('first')
                if b'root password again' in lower and 'confirm' not in sent:
                    socket_client.sendall(password + b'\r')
                    sent.add('confirm')
                if re.search(rb'login:\s*$', lower) and 'login' not in sent:
                    socket_client.sendall(b'root\r')
                    sent.add('login')
                if 'login' in sent and re.search(rb'password:\s*$', lower) and 'auth' not in sent:
                    socket_client.sendall(password + b'\r')
                    sent.add('auth')
                if 'auth' in sent and re.search(rb'[^\r\n]+#\s*$', clean) and 'commands' not in sent:
                    command = (f"export SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat; printf '\\n%s\\n' '{token}'; "
                               "printf 'M3_KERNEL='; uname -r; printf 'M3_MULTI='; systemctl is-active multi-user.target; "
                               "printf 'M3_FIRSTBOOT='; systemctl is-active first-boot.service; "
                               "printf 'M3_SYSTEM='; systemctl is-system-running; "
                               "printf 'M3_FAILED_COUNT='; systemctl --failed --no-legend --plain | wc -l; "
                               "systemctl --failed --no-legend --plain; pacman -Dk; printf 'M3_PACMAN_RC=%s\\n' $?; "
                               "pacman-key --verify /boot/efi/validation/m1n1.pkg.tar.xz.sig; printf 'M3_SIGNATURE_RC=%s\\n' $?; "
                               "printf 'M3_ROOT_UUID='; findmnt -no UUID /; printf 'M3_EFI_UUID='; findmnt -no UUID /boot/efi; "
                               "findmnt --verify >/dev/null 2>&1; printf 'M3_FSTAB_RC=%s\\n' $?; "
                               "grub-script-check /boot/grub/grub.cfg; printf 'M3_GRUB_RC=%s\\n' $?; "
                               f"printf '%s\\n' '{done_token}'; systemctl poweroff\r")
                    socket_client.sendall(command.encode())
                    sent.add('commands')
                if re.search(rb'(?:^|\n)' + done_token.encode() + rb'\r?\n', clean):
                    sent.add('completed')
                    break
            transcript = output.replace(password, b'[redacted]')
            (report_dir / 'vm-fixture-console.log').write_bytes(transcript)
            assert 'completed' in sent, 'VM did not complete authenticated startup checks; inspect sanitized console log'
            guest = evaluate_guest_checks(clean.decode(errors='replace'), require_efi=with_efi)
            assert not guest['failures'], '; '.join(guest['failures'])
            lock = json.loads((project / 'upstream.lock.json').read_text())
            delivered = project / 'artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip'
            delivered_hash = hashlib.file_digest(delivered.open('rb'), 'sha256').hexdigest()
            assert delivered_hash == lock['result']['output_sha256'], 'Delivered ZIP changed'
            result = dict(authenticated_console_login=True, private_root_password_setup=True,
                          multi_user_target_active=True, pacman_database_check=True,
                          kernel_unchanged=True, kernel_sha256=actual_kernel, delivered_zip_unchanged=True, delivered_zip_sha256=delivered_hash, guest_checks=guest['markers'],
                          fixture_changes=['add signed virtio_mmio module to test initramfs',
                                           'map password/getty units to hvc0', 'initialize virtual clock from UTC host time', 'attach disposable FAT EFI disk' if with_efi else 'omit Apple EFI mount in test fstab'],
                          preparation_manifest=preparation, physical_mac_boot_verified=False,
                          accelerator=accelerator, efi_attached=with_efi, scope='QEMU virtual-hardware fixture; not the unmodified release or Apple boot chain')
            (report_dir / 'vm-fixture-result.json').write_text(json.dumps(result, indent=2) + '\n')
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        finally:
            if socket_client:
                socket_client.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "hvf", "--with-efi" in sys.argv[4:])
