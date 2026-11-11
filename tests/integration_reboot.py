"""Two persistent-overlay cold boots through EDK2 and GRUB, never direct kernel loading."""
import hashlib
import json
import re
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

from reboot_checks import build_uefi_args, evaluate_lifecycle, firmware_boot_evidence
from vm_checks import evaluate_guest_checks


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def boot_once(base, report, firmware, password, first_boot, proof, extra_commands=""):
    report.mkdir()
    console = base / 'console.sock'
    if console.exists():
        if not console.is_socket():
            raise ValueError('Unexpected non-socket console path')
        console.unlink()
    args = build_uefi_args(base, firmware)
    args[args.index('-serial') + 1] = 'file:' + str(report / 'firmware-console.log')
    (report / 'qemu-args.json').write_text(json.dumps(args, indent=2) + '\n')
    token = 'M3_REBOOT_' + secrets.token_hex(8)
    done = token + '_DONE'
    output = b''
    sent = set()
    client = None
    with (report / 'qemu.log').open('wb') as log:
        process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if client is None:
                    try:
                        client = socket.socket(socket.AF_UNIX)
                        client.connect(str(console))
                        client.settimeout(0.25)
                    except OSError:
                        if client:
                            client.close()
                        client = None
                        time.sleep(0.1)
                        continue
                try:
                    data = client.recv(65536)
                except TimeoutError:
                    continue
                if not data:
                    break
                output += data
                (report / 'linux-console.log').write_bytes(output.replace(password, b'[redacted]'))
                clean = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', output)
                lower = clean.lower()
                if re.search(rb'enter[^\r\n]*root password', lower) and 'setup' not in sent:
                    if not first_boot:
                        raise AssertionError('Second boot unexpectedly requested initial password setup')
                    client.sendall(password + b'\r')
                    sent.add('setup')
                if b'root password again' in lower and 'confirm' not in sent:
                    client.sendall(password + b'\r')
                    sent.add('confirm')
                if re.search(rb'login:\s*$', lower) and 'login' not in sent:
                    client.sendall(b'root\r')
                    sent.add('login')
                if 'login' in sent and re.search(rb'password:\s*$', lower) and 'auth' not in sent:
                    client.sendall(password + b'\r')
                    sent.add('auth')
                if 'auth' in sent and re.search(rb'[^\r\n]+#\s*$', clean) and 'commands' not in sent:
                    save = f"printf '%s\\n' '{proof}' > /root/arch-m3-lifecycle-proof; " if first_boot else ''
                    command = ("export SYSTEMD_COLORS=0 SYSTEMD_PAGER=cat; " + save +
                               f"printf '\\n%s\\n' '{token}'; "
                               "printf 'M3_KERNEL='; uname -r; printf 'M3_MULTI='; systemctl is-active multi-user.target; "
                               "printf 'M3_FIRSTBOOT='; systemctl is-active first-boot.service; "
                               "printf 'M3_SYSTEM='; systemctl is-system-running; "
                               "printf 'M3_FAILED_COUNT='; systemctl --failed --no-legend --plain | wc -l; "
                               "systemctl --failed --no-legend --plain; pacman -Dk; printf 'M3_PACMAN_RC=%s\\n' $?; "
                               "pacman-key --verify /boot/efi/validation/m1n1.pkg.tar.xz.sig; printf 'M3_SIGNATURE_RC=%s\\n' $?; "
                               "printf 'M3_ROOT_UUID='; findmnt -no UUID /; printf 'M3_EFI_UUID='; findmnt -no UUID /boot/efi; "
                               "findmnt --verify >/dev/null 2>&1; printf 'M3_FSTAB_RC=%s\\n' $?; "
                               "grub-script-check /boot/grub/grub.cfg; printf 'M3_GRUB_RC=%s\\n' $?; "
                               "printf 'M3_UEFI='; if test -d /sys/firmware/efi; then echo 1; else echo 0; fi; "
                               "printf 'M3_BOOT_ID='; cat /proc/sys/kernel/random/boot_id; "
                               "printf 'M3_SHADOW_SHA='; sha256sum /etc/shadow | cut -d' ' -f1; "
                               "printf 'M3_PERSIST='; cat /root/arch-m3-lifecycle-proof; "
                               + extra_commands + f"printf '%s\\n' '{done}'; systemctl poweroff\r")
                    client.sendall(command.encode())
                    sent.add('commands')
                if re.search(rb'(?:^|\n)' + done.encode() + rb'\r?\n', clean):
                    sent.add('completed')
                    break
            if 'completed' not in sent:
                raise AssertionError('Firmware/GRUB boot did not complete checks; inspect firmware and Linux logs')
            guest = evaluate_guest_checks(clean.decode(errors='replace'), True,
                                          firstboot_state='active' if first_boot else 'inactive')
            if guest['failures']:
                raise AssertionError('; '.join(guest['failures']))
            if guest['markers'].get('PERSIST') != proof:
                raise AssertionError('Persistent proof was not preserved')
            guest['markers']['setup_prompt_seen'] = 'setup' in sent
            shutdown_deadline = time.monotonic() + 30
            while process.poll() is None and time.monotonic() < shutdown_deadline:
                try:
                    remaining = client.recv(65536)
                except TimeoutError:
                    continue
                if not remaining:
                    break
                output += remaining
                (report / 'linux-console.log').write_bytes(output.replace(password, b'[redacted]'))
            process.wait(timeout=max(1, shutdown_deadline - time.monotonic()))
            if process.returncode != 0:
                raise AssertionError('VM did not shut down cleanly')
            firmware_result = firmware_boot_evidence((report / 'firmware-console.log').read_text(errors='replace'))
            if not firmware_result['verified']:
                raise AssertionError('Firmware log did not substantiate GRUB/kernel loading')
            guest['markers']['firmware_grub_verified'] = firmware_result['verified']
            (report / 'firmware-evidence.json').write_text(json.dumps(firmware_result, indent=2) + '\n')
            (report / 'shutdown.json').write_text(json.dumps(dict(qemu_exit_code=process.returncode,
                guest_completion_marker_observed=True, clean_process_shutdown=True), indent=2) + '\n')
            (report / 'guest-checks.json').write_text(json.dumps(guest, indent=2) + '\n')
            return guest['markers']
        finally:
            if client:
                client.close()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)


def main(base, report):
    base, report = Path(base).resolve(), Path(report).resolve()
    if report.exists():
        raise ValueError('Lifecycle report directory must be new')
    report.mkdir(parents=True)
    preparation = json.loads((base / 'grub-preparation.json').read_text())
    firmware = Path(preparation['firmware_code'])
    if sha(firmware) != preparation['firmware_sha256']:
        raise ValueError('Firmware identity changed')
    for name, expected in preparation['raw_parents_sha256'].items():
        if sha(base / name) != expected:
            raise ValueError('Raw parent changed')
    for name, expected in preparation['overlay_initial_sha256'].items():
        if sha(base / (name + '.qcow2')) != expected:
            raise ValueError('Overlay is not pristine; prepare a new fixture')
    if sha(base / 'vars.fd') != preparation['vars_initial_sha256']:
        raise ValueError('EFI variable store is not pristine')
    password = secrets.token_urlsafe(24).encode()
    proof = secrets.token_hex(24)
    first = boot_once(base, report / 'first', firmware, password, True, proof)
    for name in ('root', 'efi'):
        subprocess.run(['qemu-img', 'check', str(base / (name + '.qcow2'))], check=True,
                       stdout=subprocess.DEVNULL, timeout=30)
    second = boot_once(base, report / 'second', firmware, password, False, proof)
    failures = evaluate_lifecycle(first, second)
    if failures:
        raise AssertionError('; '.join(failures))
    for name in ('root', 'efi'):
        subprocess.run(['qemu-img', 'check', str(base / (name + '.qcow2'))], check=True, stdout=subprocess.DEVNULL, timeout=30)
    unchanged = {}
    for name, expected in preparation['raw_parents_sha256'].items():
        unchanged[name] = sha(base / name) == expected
    if not all(unchanged.values()):
        raise AssertionError('Raw backing image changed')
    project = Path(__file__).resolve().parents[1]
    lock = json.loads((project / 'upstream.lock.json').read_text())
    delivered = project / 'artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip'
    if sha(delivered) != lock['result']['output_sha256']:
        raise AssertionError('Delivered ZIP changed')
    result = dict(first_boot=first, second_boot=second, lifecycle_checks_passed=True,
                  firmware_grub_route=all(p['firmware_grub_verified'] for p in (first, second)), direct_kernel_arguments_used=False,
                  raw_backing_files_unchanged=unchanged, delivered_zip_unchanged=True,
                  preparation=preparation, physical_apple_boot_verified=False,
                  scope='EDK2/GRUB and repeat cold boot in persistent disposable VM overlays, not Apple boot-chain qualification')
    (report / 'lifecycle-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
