"""Locally-trained supervised *requirement-evidence* matcher.

Only artifacts at a server-configured path are used. joblib uses pickle internally:
NEVER accept artifacts uploaded from clients or untrusted sources.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import joblib


class CustomModelUnavailable(RuntimeError):
    pass


def model_path() -> Path | None:
    path = os.getenv('SKILLLENS_CUSTOM_MODEL', '').strip()
    return Path(path).expanduser() if path else None


@lru_cache(maxsize=2)
def _load(path: str):
    try:
        model = joblib.load(path)  # TRUSTED artifacts created locally by training/train.py ONLY
        metadata = json.loads(Path(path).with_suffix('.json').read_text(encoding='utf-8'))
        if metadata.get('schema_version') != 1:
            raise ValueError('Unsupported model metadata')
        return model, metadata
    except Exception as exc:
        raise CustomModelUnavailable('Unable to load trusted trained model or metadata. Verify SKILLLENS_CUSTOM_MODEL.') from exc


def status() -> dict:
    path = model_path()
    if not path:
        return {'available': False, 'note': 'Train a model, then set SKILLLENS_CUSTOM_MODEL to its .joblib path.'}
    metadata = path.with_suffix('.json')
    if not path.is_file() or not metadata.is_file():
        return {'available': False, 'note': 'Configured model files do not exist.'}
    try:
        data = json.loads(metadata.read_text(encoding='utf-8'))
        return {'available': True, 'purpose': 'requirement-evidence matching', 'dataset_kind': data.get('dataset_kind'),
                'evaluation': data.get('evaluation'), 'warning': data.get('warning')}
    except Exception:
        return {'available': False, 'note': 'Model metadata is unreadable.'}


def assess(requirement: str, evidence: str) -> dict:
    path = model_path()
    if not path or not path.is_file():
        raise CustomModelUnavailable('Custom model is not configured or does not exist.')
    model, metadata = _load(str(path.resolve()))
    prob = float(model.predict_proba([requirement + '\n[RESUME EVIDENCE]\n' + evidence])[0, 1])
    return {'confidence': round(prob, 4), 'positive': prob >= 0.5,
            'dataset_kind': metadata.get('dataset_kind'),
            'caution': 'Classifier prediction is experimental evidence matching, NOT applicant ranking or a hiring outcome.'}
