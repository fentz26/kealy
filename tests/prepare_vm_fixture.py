"""Adapt disposable VM inputs only; never run against a delivered root image.

Requires prepared root.img, Image, initramfs.img and decompressed initramfs-main.
Writes fixture initramfs/config/commands; apply commands only inside the disposable
VM directory mounted as /vm. The delivered ZIP is never changed.
"""
import gzip,tarfile,subprocess,json,stat,sys
from pathlib import Path
base=Path(sys.argv[1]).resolve(); project=Path(sys.argv[2]).resolve()
main=gzip.decompress((base/'initramfs-main').read_bytes())
p=0; init=None
while main[p:p+6] in (b'070701',b'070702'):
 size=int(main[p+54:p+62],16); n=int(main[p+94:p+102],16); name=main[p+110:p+110+n-1].decode(); start=(p+110+n+3)//4*4
 if name=='init': init=main[start:start+size]
 p=(start+size+3)//4*4
 if name=='TRAILER!!!':break
assert init and b'\nmount_setup\n' in init
init=init.replace(b'\nmount_setup\n', b'\nmount_setup\ninsmod /virtio_mmio.ko\nsleep 1\nexec </dev/hvc0 >/dev/hvc0 2>&1\n',1)
with tarfile.open(project/'upstream/packages/linux-asahi-7.2.12.asahi3-1-aarch64.pkg.tar.xz') as t:
 m=next(m for m in t if m.name.endswith('/virtio_mmio.ko')); module=t.extractfile(m).read()
def cpio_entry(name,data,mode,ino):
 name=name.encode()+b'\0'; fields=[ino,mode,0,0,1,0,len(data),0,0,0,0,len(name),0]
 h=b'070701'+b''.join(f'{x:08x}'.encode() for x in fields)+name;h+=b'\0'*(-len(h)%4);h+=data;h+=b'\0'*(-len(h)%4);return h
extra=cpio_entry('virtio_mmio.ko',module,0o100644,1000001)+cpio_entry('init',init,0o100755,1000002)+cpio_entry('TRAILER!!!',b'',0,0)
(base/'initramfs-virtio-test.img').write_bytes((base/'initramfs.img').read_bytes()+extra)
service=(project/'overlay/etc/systemd/system/arch-m3-root-password.service').read_text().replace('getty@tty1.service','serial-getty@hvc0.service').replace('/dev/tty1','/dev/hvc0')
(base/'password.service').write_text(service)
(base/'hvc0.conf').write_text('[Unit]\nRequires=arch-m3-root-password.service\nAfter=arch-m3-root-password.service\n')
fstab=json.load(open(project/'evidence/derivative-audit-strict.json'))['system']['fstab']; (base/'fstab').write_text('\n'.join(line for line in fstab.splitlines() if '/boot/efi' not in line)+'\n')
(base/'fixture.commands').write_text('''rm /etc/fstab
write /vm/fstab /etc/fstab
rm /etc/systemd/system/arch-m3-root-password.service
write /vm/password.service /etc/systemd/system/arch-m3-root-password.service
mkdir /etc/systemd/system/serial-getty@hvc0.service.d
write /vm/hvc0.conf /etc/systemd/system/serial-getty@hvc0.service.d/10-root-password.conf
symlink /etc/systemd/system/getty@tty1.service /dev/null
''')
