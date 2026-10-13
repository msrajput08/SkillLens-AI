"""Optional local sentence embedding retrieval; no downloads occur unless configured.

Set SKILLLENS_EMBED_MODEL to a local model path or a Hugging Face model identifier.
Identifiers may download on first use. The browser must explicitly choose embeddings.
"""
import os
import re
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class SemanticUnavailable(RuntimeError):
    pass


def configured_model() -> str:
    return os.getenv('SKILLLENS_EMBED_MODEL', '').strip()


@lru_cache(maxsize=2)
def _load_model(model_id: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SemanticUnavailable('Install optional dependency: pip install -r requirements-ai.txt') from exc
    try:
        return SentenceTransformer(model_id)
    except Exception as exc:
        raise SemanticUnavailable('Configured embedding model could not be loaded. Check local path/network availability.') from exc


def _passages(text: str, max_passages=50) -> list[str]:
    lines = [re.sub(r'\s+', ' ', l).strip(' -*•\t') for l in text.splitlines()]
    chunks = [line[:650] for line in lines if len(line.strip()) >= 20]
    if len(chunks) < 3:
        chunks = [x.strip()[:650] for x in re.split(r'(?<=[.!?])\s+', text) if len(x.strip()) >= 20]
    return chunks[:max_passages] or [text[:650]]


def retrieval(resume: str, jd: str) -> dict:
    """Return 0..1 semantic score and cited source text matches."""
    model_id = configured_model()
    if not model_id:
        raise SemanticUnavailable('Local embedding model not configured. Set SKILLLENS_EMBED_MODEL first.')
    model = _load_model(model_id)
    passages = _passages(resume)
    requirements = _passages(jd, 35)
    try:
        import numpy as np
        embeddings = model.encode(passages + requirements, normalize_embeddings=True, show_progress_bar=False)
        scores = np.asarray(embeddings[:len(passages)]) @ np.asarray(embeddings[len(passages):]).T
        best = scores.max(axis=0)
        strength = float(np.mean(np.clip((best - 0.20) / 0.65, 0, 1)))
        matches = []
        for i, req in enumerate(requirements):
            match_i = int(np.argmax(scores[:, i]))
            matches.append({'requirement': req[:240], 'resume_evidence': passages[match_i][:240], 'similarity': round(float(scores[match_i, i]), 3)})
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return {'score': round(strength, 4), 'matches': matches[:8], 'model': model_id, 'note': 'Embedding similarity finds related phrases; does not verify competence or equal meaning.'}
    except Exception as exc:
        raise SemanticUnavailable('Embedding inference failed. Try lexical mode or check model compatibility.') from exc


def model_status() -> dict:
    model_id = configured_model()
    return {'available': bool(model_id), 'model': model_id or None,
            'note': 'Embeddings are opt-in. A model identifier can download weights on first use.'}
