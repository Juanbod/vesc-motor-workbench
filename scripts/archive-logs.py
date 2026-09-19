"""Archive large JSONL bench streams without changing the original files."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def digest_stream(source):
    result = hashlib.sha256()
    size = 0
    for block in iter(lambda: source.read(1024 * 1024), b''):
        size += len(block)
        result.update(block)
    return result.hexdigest(), size


def create(root):
    entries = []
    for original in sorted(root.rglob('*.jsonl')):
        archive = original.with_name(original.name + '.gz')
        temporary = archive.with_name(archive.name + '.tmp')
        with original.open('rb') as source, temporary.open('wb') as target:
            with gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0,
                               compresslevel=6) as compressed:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    compressed.write(block)
        os.replace(temporary, archive)
        with gzip.open(archive, 'rb') as source:
            original_hash, original_size = digest_stream(source)
        if original_hash != digest(original) or original_size != original.stat().st_size:
            raise ValueError(f'Archive verification failed: {original}')
        entries.append(dict(path=original.relative_to(root).as_posix(),
                            original_bytes=original_size, original_sha256=original_hash,
                            archive_bytes=archive.stat().st_size,
                            archive_sha256=digest(archive)))
    if not entries:
        raise ValueError('No source JSONL files found')
    manifest = dict(schema='bench-jsonl-gzip-v1', streams=entries)
    (root/'archive-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n',
                                              encoding='utf-8')
    return manifest


def verify(root, restore=False):
    manifest = json.loads((root/'archive-manifest.json').read_text(encoding='utf-8'))
    if manifest['schema'] != 'bench-jsonl-gzip-v1':
        raise ValueError('Unexpected archive schema')
    for item in manifest['streams']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.suffix != '.jsonl':
            raise ValueError('Invalid archive path')
        original = root/relative
        archive = original.with_name(original.name + '.gz')
        if archive.stat().st_size != item['archive_bytes'] or digest(archive) != item['archive_sha256']:
            raise ValueError(f'Archive hash mismatch: {archive}')
        with gzip.open(archive, 'rb') as source:
            actual_hash, actual_size = digest_stream(source)
        if (actual_hash, actual_size) != (item['original_sha256'], item['original_bytes']):
            raise ValueError(f'Original stream hash mismatch: {archive}')
        if restore and not original.exists():
            with gzip.open(archive, 'rb') as source, original.open('xb') as target:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    target.write(block)
        if restore and digest(original) != item['original_sha256']:
            raise ValueError(f'Restored stream hash mismatch: {original}')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify', 'restore'))
    parser.add_argument('--root', type=Path, default=Path('logs'))
    args = parser.parse_args()
    manifest = create(args.root) if args.action == 'create' else verify(
        args.root, restore=args.action == 'restore')
    print(json.dumps(dict(action=args.action, streams=len(manifest['streams']),
                          original_bytes=sum(i['original_bytes'] for i in manifest['streams']),
                          archive_bytes=sum(i['archive_bytes'] for i in manifest['streams']))))


if __name__ == '__main__':
    main()
