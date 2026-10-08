"""Verify installed local components without downloads, models or media rendering."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def check(root, run_versions=False):
    registry = json.loads((root / 'components.json').read_text(encoding='utf-8'))
    results = []
    for component in registry['components']:
        for entry in component['verified_files']:
            path = root / entry['path']
            exists = path.is_file()
            observed = None
            if exists:
                with path.open('rb') as source:
                    observed = hashlib.file_digest(source, 'sha256').hexdigest()
            results.append({'component': component['id'], 'path': entry['path'],
                            'ok': exists and observed == entry['sha256']})
        if run_versions and component.get('version_args'):
            command = [str(root / component['entry'])] + component['version_args']
            try:
                proc = subprocess.run(command, capture_output=True, text=True, errors='replace',
                                      timeout=30, creationflags=0x08000000 if sys.platform == 'win32' else 0)
                results.append({'component': component['id'], 'version_exit': proc.returncode,
                                'version': (proc.stdout or proc.stderr).splitlines()[:2], 'ok': proc.returncode == 0})
            except (OSError, subprocess.TimeoutExpired) as error:
                results.append({'component': component['id'], 'ok': False, 'error': str(error)})
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--versions', action='store_true', help='Also run local version-only commands')
    args = parser.parse_args()
    rows = check(args.root.resolve(), args.versions)
    print(json.dumps({'ok': all(row['ok'] for row in rows), 'checks': rows}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(row['ok'] for row in rows) else 1)
