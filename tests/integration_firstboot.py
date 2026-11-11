"""Run the real first-login helper in a disposable, networkless Linux chroot.

Requires SYS_CHROOT and MKNOD inside Docker's Linux VM, never host disk devices.
The image's systemd and account tools execute only in this disposable sandbox.
"""
import json
import os
import pty
import re
import secrets
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def run_prompt(root, password):
    pid, master = pty.fork()
    if pid == 0:
        os.execvp('chroot', ['chroot', str(root), '/usr/local/lib/arch-m3/set-root-password'])
    transcript = b''
    sent = set()
    deadline = time.monotonic() + 45
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                transcript += chunk
                clean = re.sub(rb'\x1b\[[0-9;?]*[A-Za-z]', b'', transcript).lower()
                if b'press any key' in clean and 'welcome' not in sent:
                    os.write(master, b'\n')
                    sent.add('welcome')
                if re.search(rb'enter[^\r\n]*root password', clean) and 'first' not in sent:
                    os.write(master, password.encode() + b'\n')
                    sent.add('first')
                if (b'repeat' in clean or b'reenter' in clean or b're-enter' in clean or b'root password again' in clean) and 'second' not in sent:
                    os.write(master, password.encode() + b'\n')
                    sent.add('second')
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status), sent, transcript.decode(errors='replace').replace(password, '[redacted]' if password else '')
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            return os.waitstatus_to_exitcode(status), sent, transcript.decode(errors='replace').replace(password, '[redacted]' if password else '')
        raise RuntimeError('Password prompt timed out: ' + transcript.decode(errors='replace').replace(password, '[redacted]'))
    finally:
        os.close(master)
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except ProcessLookupError:
            pass
        except ChildProcessError:
            pass


def main(archive):
    with tempfile.TemporaryDirectory(prefix='arch-m3-login-test-') as temp:
        temp = Path(temp)
        image = temp / 'root.img'
        with zipfile.ZipFile(archive) as z:
            with z.open('root.img') as source, image.open('wb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
        root = temp / 'root'
        root.mkdir()
        result = subprocess.run(['debugfs', '-R', f'rdump / {root}', str(image)], capture_output=True, timeout=180)
        if result.returncode or not (root / 'usr/bin/systemd-firstboot').is_file():
            raise RuntimeError('Disposable root extraction failed')
        image.unlink()
        for name, device in [('tty', os.makedev(5, 0)), ('null', os.makedev(1, 3))]:
            p = root / 'dev' / name
            if not p.exists():
                os.mknod(p, stat.S_IFCHR | 0o666, device)
        # A chroot is not a booted VM: provide an empty kernel command line,
        # without mounting proc or exposing the Docker VM's live boot options.
        (root / 'proc').mkdir(exist_ok=True)
        (root / 'proc').chmod(0o755)
        (root / 'proc/cmdline').write_text('')
        (root / 'proc').chmod(0o555)
        marker = root / 'etc/arch-m3-root-password-set'
        assert not marker.exists()
        skipped, prompts, _ = run_prompt(root, '')
        assert skipped != 0, 'Skipping a private password must not complete setup'
        assert not marker.exists(), 'Skipping setup incorrectly wrote completion marker'
        password = secrets.token_urlsafe(24)
        completed, prompts, transcript = run_prompt(root, password)
        assert completed == 0, 'Setting a private password failed: ' + transcript
        assert marker.exists(), 'Completion marker missing'
        assert stat.S_IMODE(marker.stat().st_mode) == 0o600
        root_hash = next(line.split(':')[1] for line in (root / 'etc/shadow').read_text().splitlines() if line.startswith('root:'))
        assert root_hash and not root_hash.startswith(('!', '*'))
        # A second invocation must not reset a password or prompt again.
        repeated, repeat_prompts, _ = run_prompt(root, secrets.token_urlsafe(24))
        assert repeated == 0 and not repeat_prompts
        assert root_hash == next(line.split(':')[1] for line in (root / 'etc/shadow').read_text().splitlines() if line.startswith('root:'))
        database = subprocess.run(['chroot', str(root), '/usr/bin/pacman', '-Dk'], capture_output=True, timeout=30)
        if database.returncode:
            raise RuntimeError('Package database check failed: ' + database.stderr.decode(errors='replace'))
        verified = subprocess.run(['chroot', str(root), '/usr/bin/systemd-analyze', 'verify',
                                   '/etc/systemd/system/arch-m3-root-password.service',
                                   '/usr/lib/systemd/system/getty@.service'], capture_output=True, timeout=30)
        if verified.returncode:
            raise RuntimeError('systemd unit validation failed: ' + verified.stderr.decode(errors='replace'))
        print(json.dumps({'skip_password_fails_closed': True, 'private_password_setup': True,
                          'completion_marker_mode': '0600', 'repeat_preserves_password': True,
                          'systemd_unit_verify': True, 'pacman_database_check': True, 'scope': 'disposable userspace chroot, not Mac hardware boot'}, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
