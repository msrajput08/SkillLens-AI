"""Train and evaluate experimental evidence matcher on human-labeled CSV.

Usage: python -m training.train --dataset training/demo_labeled_pairs.csv --output models/demo.joblib --dataset-kind synthetic_demo
CSV fields: requirement,evidence,label,group. Labels 0/1; group should identify
related role/resume family to avoid train/test leakage.
DO NOT use a demo model for employment decisions.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix
from sklearn.model_selection import GroupShuffleSplit
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from app.model_features import PairOverlapFeatures


def read_data(path: Path):
    entries = []
    with path.open(newline='', encoding='utf-8') as handle:
        r = csv.DictReader(handle)
        if not {'requirement', 'evidence', 'label', 'group'}.issubset(set(r.fieldnames or [])):
            raise ValueError('CSV must contain requirement,evidence,label,group')
        for row in r:
            req = row['requirement'].strip()
            evidence = row['evidence'].strip()
            if len(req) < 12 or len(evidence) < 12 or len(req) > 1500 or len(evidence) > 2000:
                raise ValueError('Each requirement/evidence text must be 12–1500/2000 characters.')
            if row['label'] not in ('0', '1'):
                raise ValueError('Labels must be 0 or 1.')
            if not row['group'].strip():
                raise ValueError('Every row needs a group to prevent leakage.')
            entries.append((req + '\n[RESUME EVIDENCE]\n' + evidence, int(row['label']), row['group'].strip()))
    if len(entries) < 30 or len(set(g for _, _, g in entries)) < 5:
        raise ValueError('Need at least 30 labeled pairs spanning 5 groups.')
    if min(Counter(y for _, y, _ in entries).values()) < 10:
        raise ValueError('At least 10 examples required for each label.')
    return entries


def make_pipeline():
    return Pipeline([
        ('features', FeatureUnion([('word_patterns', TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, max_features=14000)), ('overlap', PairOverlapFeatures())])),
        ('classifier', LogisticRegression(max_iter=900, class_weight='balanced', random_state=17))
    ])


def train(dataset: Path, output: Path, dataset_kind: str = 'human_labeled') -> dict:
    if dataset_kind not in ('synthetic_demo', 'human_labeled'):
        raise ValueError('dataset-kind must be synthetic_demo or human_labeled')
    rows = read_data(dataset)
    x, y, groups = zip(*rows)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=17)
    train_idx, test_idx = next(splitter.split(x, y, groups))
    train_labels = {y[i] for i in train_idx}
    test_labels = {y[i] for i in test_idx}
    if train_labels != {0, 1} or test_labels != {0, 1}:
        raise ValueError('Train and held-out role groups must include both labels; add diverse group data.')
    pipeline = make_pipeline()
    pipeline.fit([x[i] for i in train_idx], [y[i] for i in train_idx])
    true = [y[i] for i in test_idx]
    pred = pipeline.predict([x[i] for i in test_idx]).tolist()
    evaluation = {'accuracy': round(accuracy_score(true, pred), 3),
                  'precision': round(precision_score(true, pred, zero_division=0), 3),
                  'recall': round(recall_score(true, pred, zero_division=0), 3),
                  'f1': round(f1_score(true, pred, zero_division=0), 3),
                  'confusion_matrix': confusion_matrix(true, pred, labels=[0, 1]).tolist(),
                  'train_examples': len(train_idx), 'test_examples': len(test_idx),
                  'held_out_groups': sorted(set(groups[i] for i in test_idx))}
    # Fit shipped model on all data AFTER held-out assessment. Metrics come from separate model.
    final_model = make_pipeline().fit(x, y)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final_model, output)
    meta = {'schema_version': 1, 'dataset_kind': dataset_kind, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'training_records': len(rows), 'unique_groups': len(set(groups)), 'evaluation': evaluation,
            'warning': 'EXPERIMENTAL; illustrative synthetic dataset, not real applicant outcomes.' if dataset_kind == 'synthetic_demo'
                       else 'Human labels still require audit for quality, bias, representativeness, and drift; not for automatic hiring decisions.'}
    output.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--dataset-kind', choices=['human_labeled', 'synthetic_demo'], default='human_labeled')
    args = parser.parse_args()
    print(json.dumps(train(args.dataset, args.output, args.dataset_kind), indent=2))


if __name__ == '__main__':
    main()
