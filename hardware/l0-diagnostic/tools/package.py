#!/usr/bin/env python3
"""Package verified L0 and R0 sources/images; reject evidence for a different revision."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ('src', 'tools', 'tests', 'reference', 'licenses', 'evidence')
SOURCE_FILES = ('README.md', 'ONLINE.md', 'platformio.ini', 'requirements.txt', 'ZRODLA-I-WERYFIKACJA.txt')
OFFSETS = {'bootloader.bin': 0, 'partitions.bin': 0x8000,
           'boot_app0.bin': 0xe000, 'firmware.bin': 0x10000}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_files(project):
    files = [project / name for name in SOURCE_FILES if (project / name).is_file()]
    for name in SOURCE_DIRS:
        files.extend(path for path in (project / name).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts)
    return sorted(files)


def verify_source(project, firmware):
    evidence = json.loads((project / 'checks.json').read_text())
    expected = {str(path.relative_to(project)): checksum(path) for path in source_files(project)}
    if evidence['source_sha256'] != expected:
        raise RuntimeError(f'{project}: źródła zmieniły się od zapisanej weryfikacji.')
    if (not evidence['compiled'] or evidence['automated_tests'] < 1 or
            evidence['automated_tests_passed'] != evidence['automated_tests'] or
            evidence['firmware_bin_sha256'] != checksum(firmware)):
        raise RuntimeError(f'{project}: brak poprawnej weryfikacji tego obrazu.')
    return evidence


def copy_source(project, target):
    for source in source_files(project) + [project / 'checks.json']:
        destination = target / source.relative_to(project)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if (project / '.gitignore').is_file():
        shutil.copy2(project / '.gitignore', target / '.gitignore')


def make_image(build, boot_app0, destination, name):
    destination.mkdir(parents=True)
    for filename in OFFSETS:
        source = boot_app0 if filename == 'boot_app0.bin' else build / filename
        shutil.copy2(source, destination / filename)
    command = [sys.executable, '-m', 'esptool', '--chip', 'esp32s3', 'merge_bin',
               '--flash_mode', 'dio', '--flash_freq', '80m', '--flash_size', '8MB',
               '-o', str(destination / name)]
    for filename, offset in OFFSETS.items():
        command.extend([hex(offset), str(destination / filename)])
    subprocess.run(command, check=True)
    merged = (destination / name).read_bytes()
    for filename, offset in OFFSETS.items():
        data = (destination / filename).read_bytes()
        if merged[offset:offset + len(data)] != data:
            raise RuntimeError('Niezgodność składnika scalonego obrazu: ' + filename)
    (destination / 'offsets.json').write_text(json.dumps({
        'chip': 'esp32s3', 'flash_size': '8MB', 'flash_mode': 'dio', 'flash_freq': '80m',
        'full_image': {'file': name, 'offset': '0x0'},
        'components': {filename: hex(offset) for filename, offset in OFFSETS.items()},
    }, indent=2) + '\n')


def build_package(output, peer, boot_app0):
    l0_build = ROOT / '.pio/build/l0'
    r0_build = peer / '.pio/build/pair'
    verify_source(ROOT, l0_build / 'firmware.bin')
    verify_source(peer, r0_build / 'firmware.bin')
    with tempfile.TemporaryDirectory() as folder:
        package = Path(folder)
        copy_source(ROOT, package)
        copy_source(peer, package / 'partner-r0')
        make_image(l0_build, boot_app0, package / 'images', 'l0-full.bin')
        make_image(r0_build, boot_app0, package / 'partner-r0/images', 'r0-full.bin')
        shutil.copy2(ROOT / 'reference/R0-INSTRUKCJA.txt', package / 'partner-r0/INSTRUKCJA.txt')
        sums = ''.join(f'{checksum(path)}  {path.relative_to(package)}\n'
                       for path in sorted(package.rglob('*')) if path.is_file())
        (package / 'SHA256SUMS.txt').write_text(sums)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob('*')):
                if path.is_file():
                    archive.write(path, str(path.relative_to(package)))
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Błąd integralności ZIP.')
    print(f'Paczka: {output}\nSHA-256: {checksum(output)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--r0', type=Path, default=ROOT.parent / 'radio-pair')
    parser.add_argument('--boot-app0', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build_package(args.output, args.r0, args.boot_app0)


if __name__ == '__main__':
    main()
