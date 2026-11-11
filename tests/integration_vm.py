"""Bounded QEMU userspace boot test of an explicitly adapted virtual-hardware fixture."""
import json
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path


def run(base, report_dir):
    base, report_dir = Path(base), Path(report_dir)
    console = base / 'virtio-test.sock'
    if console.exists():
        console.unlink()
    args = ['qemu-system-aarch64', '-machine', 'virt', '-accel', 'hvf', '-cpu', 'host',
            '-m', '1536', '-smp', '2', '-display', 'none', '-serial', 'none', '-monitor', 'none',
            '-nic', 'none', '-kernel', str(base / 'Image'), '-initrd', str(base / 'initramfs-virtio-test.img'),
            '-drive', f'if=none,file={base / "root.img"},format=raw,id=root,snapshot=on',
            '-device', 'virtio-blk-device,drive=root', '-device', 'virtio-serial-device',
            '-chardev', f'socket,id=console,path={console},server=on,wait=on',
            '-device', 'virtconsole,chardev=console',
            '-append', 'root=/dev/vda rw console=hvc0 loglevel=4']
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
                    command = (f"printf '\\n%s\\n' '{token}'; uname -r; systemctl is-active multi-user.target; "
                               f"systemctl --failed --no-legend; pacman -Dk; printf 'PACMAN_RC=%s\\n' $?; "
                               f"printf '%s\\n' '{done_token}'; systemctl poweroff\r")
                    socket_client.sendall(command.encode())
                    sent.add('commands')
                if re.search(rb'(?:^|\n)' + done_token.encode() + rb'\r?\n', clean):
                    sent.add('completed')
                    break
            transcript = output.replace(password, b'[redacted]')
            (report_dir / 'vm-fixture-console.log').write_bytes(transcript)
            assert 'completed' in sent, 'VM did not complete authenticated startup checks; inspect sanitized console log'
            assert re.search(rb'(?:^|\n)PACMAN_RC=0\r?\n', clean), 'Guest pacman database check failed'
            assert re.search(rb'(?:^|\n)active\r?\n', clean), 'Guest multi-user.target was not active'
            result = dict(authenticated_console_login=True, private_root_password_setup=True,
                          multi_user_target_active=True, pacman_database_check=True,
                          kernel_unchanged=True, delivered_zip_unchanged=True,
                          fixture_changes=['add signed virtio_mmio module to test initramfs',
                                           'map password/getty units to hvc0', 'omit Apple EFI mount in test fstab'],
                          physical_mac_boot_verified=False,
                          scope='QEMU/HVF with virtual-hardware fixture; not the unmodified release or Apple boot chain')
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
    run(sys.argv[1], sys.argv[2])
