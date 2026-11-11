"""Static check that the J504 device tree routes the external display to USB-C.

This reads a device tree only. It cannot show that a monitor lights up.
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .audit import AuditError, Ext4Reader

# Addresses come from the J504 Apple device tree (see docs/external-display-plan.md).
DCPEXT = 'dcp@31ac00000'
XBAR = 'mux@70304c000'
REQUIRED_OKAY = (DCPEXT, XBAR, 'iommu@319304000', 'iommu@31930c000', 'mbox@31ac08000')


def node_body(dts, name):
    """Return the text of the first node called `name` in decompiled DTS."""
    match = re.search(r'^\s*(?:[\w-]+:\s*)?' + re.escape(name) + r'\s*\{', dts, re.M)
    if not match:
        return None
    depth, start = 1, match.end()
    for index in range(start, len(dts)):
        if dts[index] == '{':
            depth += 1
        elif dts[index] == '}':
            depth -= 1
            if depth == 0:
                return dts[start:index]
    return None


def own_properties(body):
    """Properties of a node, ignoring those of its children."""
    result, depth, current = {}, 0, ''
    for char in body:
        if char == '{':
            depth += 1
            current = ''
        elif char == '}':
            depth -= 1
            current = ''
        elif depth == 0:
            current += char
            if char == ';':
                name, _, value = current.strip().rstrip(';').partition('=')
                result[name.strip()] = value.strip()
                current = ''
    return result


def check_display(dts):
    failures = []
    if 'compatible = "apple,j504"' not in dts:
        failures.append('Not a J504 device tree')
    for name in REQUIRED_OKAY:
        body = node_body(dts, name)
        if body is None:
            failures.append('Missing node: ' + name)
        elif own_properties(body).get('status') != '"okay"':
            failures.append('Node is not enabled: ' + name)
    dcpext = own_properties(node_body(dts, DCPEXT) or '')
    expected = {'apple,connector-type': '"DP"', 'mux-index': '<0x01>',
                'mux-control-names': '"dp-xbar"', 'phy-names': '"dp-phy"',
                'apple,dptx-phy': '<0x00>'}
    for key, value in expected.items():
        if dcpext.get(key) != value:
            failures.append(f'External display controller: {key} is {dcpext.get(key)}, expected {value}')
    xbar = own_properties(node_body(dts, XBAR) or '')
    if 'apple,t6020-display-crossbar' not in xbar.get('compatible', ''):
        failures.append('Crossbar is not driven by the t6020 crossbar driver')
    aliases = own_properties(node_body(dts, 'aliases') or '')
    if aliases.get('dcpext') != '"/soc/' + DCPEXT + '"':
        failures.append('Missing dcpext alias for m1n1')
    if not re.search(r'^\s*displayport = <', dts, re.M):
        failures.append('No USB-C connector references the display controller')
    return failures


def decompile(dtb_bytes):
    if not shutil.which('dtc'):
        raise AuditError('dtc (device-tree-compiler) is required')
    result = subprocess.run(['dtc', '-I', 'dtb', '-O', 'dts', '-q', '-'], input=dtb_bytes,
                            capture_output=True, check=True, timeout=60)
    return result.stdout.decode()


def inspect_zip(archive_path):
    with tempfile.TemporaryDirectory(prefix='kealy-display-') as directory:
        image = Path(directory) / 'root.img'
        with zipfile.ZipFile(archive_path) as archive:
            with archive.open('root.img') as source, image.open('wb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            boot = archive.read('esp/m1n1/boot.bin')
        fs = Ext4Reader(image)
        found = []
        for version in fs.ls('/usr/lib/modules'):
            for suffix in ('dtbs/apple/t8122-j504.dtb', 'dtbs/t8122-j504.dtb'):
                path = f'/usr/lib/modules/{version}/{suffix}'
                data = fs.read(path, binary=True)
                if data.startswith(b'\xd0\x0d\xfe\xed'):
                    found.append((path, data))
        if len(found) != 1:
            raise AuditError('Expected exactly one J504 device tree in the image')
        path, data = found[0]
        failures = check_display(decompile(data))
        if data not in boot:
            failures.append('Boot bundle does not contain this device tree')
        return {'device_tree': path, 'failures': failures,
                'external_display_wired': not failures,
                'hardware_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        report = inspect_zip(args.archive)
    except (AuditError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(2, f'Display check failed: {error}\n')
    print(json.dumps(report, indent=2))
    return int(bool(report['failures']))


if __name__ == '__main__':
    raise SystemExit(main())
