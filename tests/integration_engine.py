"""Exercise the pinned published engine's local payload contract without installer main."""
import contextlib
import hashlib
import importlib
import io
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

from arch_m3.handoff import inspect_installer, validate_metadata


class NoDisk:
    def __getattr__(self, name):
        raise AssertionError('A disk operation was attempted: ' + name)


def main(project):
    project = Path(project).resolve()
    lock = json.loads((project / 'upstream.lock.json').read_text())
    installer = project / 'upstream/arch-m3-alarm-published-installer.tar.gz'
    inspected = inspect_installer(installer, lock['published_installer']['sha256'])
    repo = project / 'artifacts/minimal-evaluation-r2'
    metadata = json.loads((repo / 'installer_data.json').read_text())
    product = metadata['os_list'][0]
    contract = validate_metadata(metadata, lock['result']['root_bytes'])
    with tempfile.TemporaryDirectory(prefix='arch-m3-engine-contract-') as directory:
        directory = Path(directory).resolve()
        source = directory / 'source'
        source.mkdir()
        sources = {}
        with tarfile.open(installer) as archive:
            for name in ('osinstall.py', 'm1n1.py', 'urlcache.py', 'util.py'):
                member = next(m for m in archive.getmembers() if str(Path(m.name)) == name)
                data = archive.extractfile(member).read()
                (source / name).write_bytes(data)
                sources[name] = hashlib.sha256(data).hexdigest()
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(source))
        os.environ['REPO_BASE'] = str(repo)
        armed = [True]
        def guard(event, arguments):
            if not armed[0]:
                return
            if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'socket.connect', 'socket.getaddrinfo'):
                raise AssertionError('Engine contract test forbids operation: ' + event)
            if event == 'open' and isinstance(arguments[0], (str, bytes)):
                path = Path(os.fsdecode(arguments[0])).resolve()
                mode, flags = arguments[1:3]
                writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                if str(path).startswith('/dev/') and path != Path('/dev/null'):
                    raise AssertionError('Engine test forbids device access')
                if writing and not path.is_relative_to(directory):
                    raise AssertionError('Engine test forbids writes outside disposable staging')
        sys.addaudithook(guard)
        try:
            module = importlib.import_module('osinstall')
            engine = module.OSInstaller(NoDisk(), metadata, product)
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                engine.load_package()
            payload = repo / contract['relative_payload']
            assert Path(engine.pkg.filename).resolve() == payload
            assert engine.ucache is None, 'Local payload unexpectedly uses HTTP cache'
            assert engine.min_size >= contract['root_bytes'] + contract['efi_bytes']
            assert engine.min_recommended_size == engine.min_size * 2
            assert engine.needs_firmware
            assert engine.pkg.getinfo('root.img').file_size == contract['root_bytes']
            esp = directory / 'esp'
            esp.mkdir()
            with contextlib.redirect_stdout(captured):
                engine.extract_tree('esp', str(esp))
            hashes = {}
            for name in ('EFI/BOOT/BOOTAA64.EFI', 'm1n1/boot.bin'):
                output = esp / name
                expected = engine.pkg.read('esp/' + name)
                assert output.read_bytes() == expected
                hashes[name] = hashlib.sha256(expected).hexdigest()
            engine.pkg.close()
            result = dict(published_engine_version=inspected['version'], engine_sources_sha256=sources,
                          local_payload_opened=True, source_metadata_accepted=True,
                          min_os_bytes=engine.min_size, recommended_os_bytes=engine.min_recommended_size,
                          root_image_bytes=contract['root_bytes'], firmware_copy_required=True,
                          efi_extraction_sha256=hashes, disk_operations_invoked=False,
                          network_used=False, installer_main_invoked=False,
                          scope='published loader, sizing and disposable EFI extraction; no real disk writes')
        finally:
            armed[0] = False
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
