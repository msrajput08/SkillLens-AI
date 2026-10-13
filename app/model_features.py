"""Pickle-importable feature extractor for a narrow experimental text pair model."""
import re
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from scipy.sparse import csr_matrix
from .analyzer import _mentions

STOP = set('a an and are as at be been build built candidate candidates collaborative concrete contribution demonstrate developed during engineering experience features for from hands have in involving is looking needs of on or position practical previous product project projects real requires should show skills task tasks technical the to using with work working workflows you your knowledge completed'.split())


def tokens(text):
    return {t for t in re.findall(r'[a-z][a-z0-9+#.]*', text.lower()) if len(t) >= 2 and t not in STOP}


class PairOverlapFeatures(BaseEstimator, TransformerMixin):
    def fit(self, x, y=None):
        return self

    def transform(self, x):
        rows = []
        for item in x:
            requirement, sep, evidence = item.partition('\n[RESUME EVIDENCE]\n')
            req, ev = tokens(requirement), tokens(evidence)
            common = req & ev
            mentioned = _mentions(requirement)
            found = _mentions(evidence)
            rows.append([
                len(common) / max(1, len(req)),
                len(common) / max(1, len(req | ev)),
                min(8, len(common)) / 8,
                len(mentioned & found) / max(1, len(mentioned)),
                1.0 if mentioned and mentioned.issubset(found) else 0.0,
            ])
        return csr_matrix(np.array(rows, dtype=np.float64))
