"""Grow only a disposable qcow2; require automatic guest growth across cold boots."""
import json
import secrets
import subprocess
import sys
from pathlib import Path
from integration_reboot import boot_once, sha
from reboot_checks import evaluate_lifecycle, build_uefi_args
from growth_checks import evaluate_growth


def main(base, report):
    base, report = Path(base).resolve(), Path(report).resolve()
    if report.exists():
        raise ValueError('Report must be new')
    prep = json.loads((base / 'grub-preparation.json').read_text())
    firmware = Path(prep['firmware_code'])
    build_uefi_args(base, firmware)  # Reject nonregular/symlink inputs before any resize.
    for name, expected in prep['raw_parents_sha256'].items():
        if sha(base / name) != expected:
            raise ValueError('Parent changed')
    for name, expected in prep['overlay_initial_sha256'].items():
        if sha(base / (name + '.qcow2')) != expected:
            raise ValueError('Overlay not pristine')
    if sha(firmware) != prep['firmware_sha256'] or sha(base/'vars.fd') != prep['vars_initial_sha256']:
        raise ValueError('Firmware identity changed')
    subprocess.run(['qemu-img','resize','-f','qcow2',str(base/'root.qcow2'),'12G'],check=True)
    info=json.loads(subprocess.check_output(['qemu-img','info','--output=json',str(base/'root.qcow2')]))
    if info['virtual-size'] != 12*1024**3 or Path(info['full-backing-filename']) != base/'root-base.img':
        raise ValueError('Unexpected resized overlay')
    report.mkdir(parents=True)
    (report/'growth-preparation.json').write_text(json.dumps(dict(preparation=prep,resized_root=info, resized_overlay_sha256=sha(base/'root.qcow2')),indent=2)+'\n')
    password=secrets.token_urlsafe(24).encode(); proof=secrets.token_hex(24)
    measure=("printf 'M3_DISK_BYTES='; blockdev --getsize64 $(findmnt -no SOURCE /); "
             "printf 'M3_FS_BYTES=%s\\n' $(( $(stat -f -c %S /) * $(stat -f -c %b /) )); "
             "printf 'M3_EXTENT_BYTES=%s\\n' $(( $(stat -c %b /root/arch-m3-growth-extent) * 512 )); "
             "printf 'M3_DATA_SHA='; sha256sum /root/arch-m3-growth-data | cut -d' ' -f1; ")
    write=("fallocate -l 1G /root/arch-m3-growth-extent && dd if=/dev/urandom of=/root/arch-m3-growth-data bs=1M count=8 status=none && sync; printf 'M3_WRITE_RC=%s\\n' $?; ")
    first=boot_once(base,report/'first',firmware,password,True,proof,write+measure)
    second=boot_once(base,report/'second',firmware,password,False,proof,"test -f /root/arch-m3-growth-data; printf 'M3_WRITE_RC=%s\\n' $?; "+measure)
    failures=evaluate_lifecycle(first,second)+evaluate_growth(first,second)
    for name in ('root','efi'):
        subprocess.run(['qemu-img','check',str(base/(name+'.qcow2'))],check=True)
    unchanged={name:sha(base/name)==expected for name,expected in prep['raw_parents_sha256'].items()}
    project=Path(__file__).resolve().parents[1]
    lock=json.loads((project/'upstream.lock.json').read_text())
    delivered=sha(project/'artifacts/minimal-evaluation-r2/os/arch-m3-minimal.zip')==lock['result']['output_sha256']
    if failures or not all(unchanged.values()) or not delivered:
        raise AssertionError(str(failures or 'Original file changed'))
    result=dict(first_boot=first,second_boot=second,automatic_growth_verified=True,manual_guest_resize_used=False,raw_backing_files_unchanged=unchanged,delivered_zip_unchanged=delivered,physical_apple_boot_verified=False)
    (report/'growth-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    main(*sys.argv[1:])
