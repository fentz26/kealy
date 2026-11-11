"""Parse explicit guest result markers; terminal echo and generic status words are not evidence."""
import re
import uuid
from pathlib import Path


def evaluate_guest_checks(text, require_efi=False, firstboot_state="active"):
    if firstboot_state not in ("active", "inactive"):
        raise ValueError("Unsupported first-boot expectation")
    markers = {}
    failures = []
    for name, value in re.findall(r'^M3_([A-Z_]+)=([^\r\n]*)\r?$', text, re.M):
        if name in markers:
            failures.append('Duplicate guest marker: ' + name)
        markers[name] = value
    required = {'KERNEL': '7.2.12-3-1-ARCH', 'MULTI': 'active', 'PACMAN_RC': '0'}
    if require_efi:
        required.update(FIRSTBOOT=firstboot_state, SYSTEM='running', FAILED_COUNT='0', SIGNATURE_RC='0', FSTAB_RC='0', GRUB_RC='0')
    for name, expected in required.items():
        if markers.get(name) != expected:
            failures.append('Guest check failed: ' + name)
    if require_efi:
        try:
            root_uuid = uuid.UUID(markers.get('ROOT_UUID', ''))
            if not root_uuid.int or str(root_uuid) == '725346d2-f127-47bc-b464-9dd46155e8d6':
                failures.append('Root UUID was not randomized')
        except ValueError:
            failures.append('Missing or invalid root UUID')
        efi = markers.get('EFI_UUID', '')
        if not re.fullmatch(r'[0-9a-fA-F]{4}-[0-9a-fA-F]{4}', efi) or efi.upper() in ('0000-0000', '2ABF-9F91'):
            failures.append('Missing, invalid or unchanged EFI UUID')
    return dict(markers=markers, failures=failures)


def reset_result(directory):
    result = Path(directory) / 'vm-fixture-result.json'
    if result.exists() or result.is_symlink():
        result.unlink()
