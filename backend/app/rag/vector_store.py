import math
import re
from typing import List, Dict, Any, Optional
import numpy as np
from backend.app.rag.intents import normalize

class SimpleVectorStore:
    """
    Lightweight, fast in-memory Vector Store with TF-IDF / Embedding vector search and Metadata Filtering.
    Zero external dependencies, reliable on all platforms, perfect for course projects & RAG grounding.
    """
    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.tfidf_matrix: Optional[np.ndarray] = None

    def _tokenize(self, text: str) -> List[str]:
        # Clean text and split into lowercase words / bi-grams for Vietnamese semantics
        text = normalize(text).replace('may lanh', 'dieu hoa').replace('may dieu hoa', 'dieu hoa')
        words = re.findall(r'\w+', text)
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
        return words + bigrams

    def add_documents(self, docs: List[Dict[str, Any]]):
        """
        docs: list of dicts with:
          - id: int
          - text: str (combined title + content + conditions)
          - metadata: dict (category, brand, error_group, title)
        """
        self.documents = docs
        self._build_index()

    def _build_index(self):
        doc_tokens = [self._tokenize(doc["text"]) for doc in self.documents]
        N = len(doc_tokens)
        if N == 0:
            self.vocabulary = {}
            self.idf = {}
            self.tfidf_matrix = None
            return

        # Document frequency
        df: Dict[str, int] = {}
        for tokens in doc_tokens:
            unique_words = set(tokens)
            for w in unique_words:
                df[w] = df.get(w, 0) + 1

        self.vocabulary = {w: i for i, w in enumerate(df.keys())}
        self.idf = {w: math.log((N + 1) / (df[w] + 1)) + 1 for w in df}

        # Build TF-IDF matrix
        matrix = np.zeros((N, len(self.vocabulary)), dtype=np.float32)
        for i, tokens in enumerate(doc_tokens):
            tf: Dict[str, int] = {}
            for w in tokens:
                tf[w] = tf.get(w, 0) + 1
            length = len(tokens)
            for w, count in tf.items():
                if w in self.vocabulary:
                    col = self.vocabulary[w]
                    matrix[i, col] = (count / length) * self.idf[w]

        # Normalize matrix rows
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.tfidf_matrix = matrix / norms

    def search(self, query: str, top_k: int = 3, filter_category: Optional[str] = None, filter_brand: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.documents or self.tfidf_matrix is None:
            return []

        q_tokens = self._tokenize(query)
        q_vec = np.zeros((1, len(self.vocabulary)), dtype=np.float32)
        tf: Dict[str, int] = {}
        for w in q_tokens:
            tf[w] = tf.get(w, 0) + 1
        q_len = len(q_tokens) if q_tokens else 1
        for w, count in tf.items():
            if w in self.vocabulary:
                col = self.vocabulary[w]
                q_vec[0, col] = (count / q_len) * self.idf[w]

        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        scores = np.dot(self.tfidf_matrix, q_vec.T).flatten()

        # Apply Metadata Filtering / Boosting
        results = []
        for i, doc in enumerate(self.documents):
            score = float(scores[i])
            meta = doc.get("metadata", {})
            doc_cat = meta.get("category", "")
            doc_brand = meta.get("brand", "")

            # Product metadata is an eligibility filter, never just a score boost.
            general = {'', 'chung', 'tat ca', 'viettronimex'}
            if filter_category:
                category = normalize(doc_cat).replace('may lanh', 'dieu hoa')
                selected = normalize(filter_category).replace('may lanh', 'dieu hoa')
                if category not in general and category != selected:
                    continue

            if filter_brand:
                if normalize(doc_brand) not in general and normalize(doc_brand) != normalize(filter_brand):
                    continue

            # Unrelated questions must not receive arbitrary top-k policies.
            if score < 0.08:
                continue

            results.append({
                "document": doc,
                "score": score
            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

# Global singleton instance
vector_store = SimpleVectorStore()
