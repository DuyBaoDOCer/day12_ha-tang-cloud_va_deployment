import os
import json
import numpy as np

SIMILARITY_THRESHOLD = 0.78

_rulebase_cache: list = []
_rulebase_mtime: float = 0.0


def _get_rulebase_path() -> str:
    return os.getenv('RULEBASE_PATH', '../discord/data/rulebase.json')


def _cosine_sim(a, b) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def _load_rulebase() -> list:
    path = _get_rulebase_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                return data if isinstance(data, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
    return []


def build_rulebase_cache(emb_model):
    """Xây dựng lại cache embedding cho toàn bộ Rule-base."""
    global _rulebase_cache, _rulebase_mtime
    items = _load_rulebase()
    if not items:
        _rulebase_cache = []
        return
    questions = [i['question'] for i in items]
    vecs = emb_model.embed_documents(questions)
    _rulebase_cache = list(zip(vecs, items))
    try:
        _rulebase_mtime = os.path.getmtime(_get_rulebase_path())
    except OSError:
        pass


def _maybe_reload(emb_model):
    """Tự động reload cache nếu rulebase.json được Discord cập nhật (mtime thay đổi)."""
    global _rulebase_mtime
    try:
        mtime = os.path.getmtime(_get_rulebase_path())
        if mtime != _rulebase_mtime:
            build_rulebase_cache(emb_model)
    except OSError:
        pass


def search_rulebase(emb_model, question: str):
    """Tìm câu trả lời trong Rule-base theo cosine similarity."""
    _maybe_reload(emb_model)
    if not _rulebase_cache:
        return None
    q_vec = emb_model.embed_query(question)
    best_score, best_item = -1.0, None
    for vec, item in _rulebase_cache:
        score = _cosine_sim(q_vec, vec)
        if score > best_score:
            best_score, best_item = score, item
    if best_score >= SIMILARITY_THRESHOLD and best_item:
        return best_item['answer']
    return None
