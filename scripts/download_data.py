"""Bounded, cached official downloads. Ctrl+C cancels; .part never becomes trusted raw data."""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
MAX_FILE = 250_000_000
MAX_RAW = 500_000_000
HOSTS = {'github.com', 'api.github.com', 'raw.githubusercontent.com', 'objects.githubusercontent.com',
         'zenodo.org', 'pypi.org', 'files.pythonhosted.org', 'registry.npmjs.org'}


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        old = urllib.parse.urlparse(req.full_url).hostname
        new = urllib.parse.urlparse(newurl).hostname
        if old != new and not (old in {'github.com', 'raw.githubusercontent.com'} and new in
                              {'raw.githubusercontent.com', 'objects.githubusercontent.com'}):
            raise ValueError('Unrelated-domain redirect refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.username or parsed.port:
        raise ValueError('Non-official HTTPS URL refused')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def get(url, max_bytes=4_000_000):
    check_url(url)
    opener = urllib.request.build_opener(RestrictedRedirect())
    req = urllib.request.Request(url, headers={'User-Agent': 'Flyweight-local-research/0.1'}, method='GET')
    with opener.open(req, timeout=30) as response:
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError('Response exceeds limit')
        return data


def download(url, name, expected_hash=None, limit=MAX_FILE):
    if '/' in name or '\\' in name or name.startswith('.') or not name:
        raise ValueError('Unsafe filename')
    check_url(url)
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / 'downloads.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    dest = RAW / name
    old = manifest.get(name)
    if dest.exists():
        if old and old['url'] == url and sha256(dest) == old['sha256'] and dest.stat().st_size == old['bytes']:
            if expected_hash and expected_hash != old['sha256']:
                raise ValueError('Pinned source hash mismatch')
            print(f'Cache verified: {name}', flush=True)
            return old
        raise ValueError(f'Existing raw file is unverified or changed: {name}; no overwrite')
    used = sum(p.stat().st_size for p in RAW.iterdir() if p.is_file())
    opener = urllib.request.build_opener(RestrictedRedirect())
    req = urllib.request.Request(url, headers={'User-Agent': 'Flyweight-local-research/0.1'}, method='GET')
    part = dest.with_suffix(dest.suffix + '.part')
    start = time.monotonic()
    with opener.open(req, timeout=30) as response, part.open('wb') as output:
        size = int(response.headers.get('Content-Length', 0))
        if size > limit or used + size > MAX_RAW:
            raise ValueError('Download/storage quota exceeded')
        count = 0
        digest = hashlib.sha256()
        while block := response.read(1 << 20):
            count += len(block)
            if count > limit or used + count > MAX_RAW or time.monotonic() - start > 300:
                raise ValueError('Download byte/time quota exceeded')
            output.write(block)
            digest.update(block)
    if count == 0 or (size and size != count):
        raise ValueError('Empty or incomplete download')
    if expected_hash and digest.hexdigest() != expected_hash:
        raise ValueError('Downloaded hash mismatch')
    part.rename(dest)
    entry = {'url': url, 'bytes': count, 'sha256': digest.hexdigest(),
             'downloaded_utc': datetime.now(timezone.utc).isoformat()}
    manifest[name] = entry
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'file': name, **entry}), flush=True)
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-only', action='store_true')
    args = parser.parse_args()
    lock_path = ROOT / 'docs' / 'source-lock.json'
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
    else:
        commit = json.loads(get('https://api.github.com/repos/philshiu/Drosophila_brain_model/commits/main'))['sha']
        lock = {'repository': 'https://github.com/philshiu/Drosophila_brain_model', 'commit': commit,
                'zenodo': 'https://zenodo.org/records/10676866', 'files': {}}
    base = f"https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/{lock['commit']}/"
    names = ['LICENSE', 'Readme.md'] if args.reference_only else ['Completeness_783.csv', 'Connectivity_783.parquet']
    for name in names:
        prior = lock['files'].get(name, {})
        entry = download(base + name, name, prior.get('sha256'))
        lock['files'][name] = entry
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock, indent=2))
    if not args.reference_only:
        try:
            entry = download('https://zenodo.org/api/records/10676866', 'zenodo-10676866.json', limit=4_000_000)
            lock['zenodo_record'] = entry
        except (urllib.error.URLError, ValueError) as error:
            lock['zenodo_status'] = f'Official record unavailable: {type(error).__name__}; using author v783 files'
            print(lock['zenodo_status'])
        lock_path.write_text(json.dumps(lock, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise SystemExit(f'Download stopped ({type(error).__name__}). Network unavailable or validation failed. '
                         'Use: python -m services.brain.preprocess --synthetic. Raw files are never overwritten.')
