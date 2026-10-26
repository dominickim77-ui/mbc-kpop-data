"""Explicit synthetic dataset isolation. Production source gates stay unchanged."""
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = APP_ROOT / 'preview_fixture'


def synthetic():
    return os.environ.get('KPOP_PREVIEW_SYNTHETIC') == '1'


def data_root():
    return FIXTURE_ROOT if synthetic() else APP_ROOT


def fixture_root(root):
    return synthetic() and Path(root).resolve() == FIXTURE_ROOT.resolve()


def inventory(root):
    from news.chart_import import read_json, safe_path, read_bytes, validate_csv, sha256, week_date
    obj = read_json(safe_path(root, 'data/chart_registry/baseline.json'))
    if obj.get('dataset_kind') != 'SYNTHETIC' or obj.get('baseline_commit') != 'SYNTHETIC_FIXTURE_V1':
        raise ValueError('Synthetic fixture manifest required')
    result = {}
    for record in obj['weeks']:
        end = week_date(record['week_end'])
        if record['status'] != 'synthetic_fixture' or set(record['files']) != {'spotify','youtube'}:
            raise ValueError('Invalid synthetic fixture record')
        files = {}
        for platform, item in record['files'].items():
            raw = read_bytes(safe_path(root, item['path']))
            if sha256(raw) != item['sha256']:
                raise ValueError('Synthetic fixture hash mismatch')
            validate_csv(raw, platform)
            files[platform] = item['path']
        result[end] = files
    return result, ['SYNTHETIC PREVIEW: generated examples, not official chart observations.']
