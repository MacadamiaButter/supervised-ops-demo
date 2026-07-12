"""Company knowledge base + a small self-contained BM25-ish search.

Design notes
------------
Real deployments would put this behind an embedding/vector search
service, but that's an external dependency the demo shouldn't need just
to run offline on a laptop. Instead we implement a small, dependency-free
BM25 scorer over the markdown snippets in data/kb/. It is not meant to
be state-of-the-art retrieval -- it's meant to be honest: good enough to
usefully ground AI drafts ("office hours are 9-5", "emergency plumbing
SLA is 2 hours") without pretending to be a production RAG stack. The
README calls this out explicitly under "what production adds".
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from app.config import KB_DIR

_TOKEN_RE = re.compile(r"[a-z0-9']+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class KBDoc:
    slug: str
    title: str
    body: str
    tokens: list[str]


def load_kb() -> list[KBDoc]:
    docs: list[KBDoc] = []
    if not KB_DIR.exists():
        return docs
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        lines = text.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
        docs.append(KBDoc(slug=path.stem, title=title, body=body, tokens=_tokenize(title + " " + body)))
    return docs


def _bm25_scores(query: str, docs: list[KBDoc], k1: float = 1.5, b: float = 0.75) -> list[tuple[KBDoc, float]]:
    q_tokens = _tokenize(query)
    if not q_tokens or not docs:
        return []
    n = len(docs)
    avgdl = sum(len(d.tokens) for d in docs) / n
    # document frequency per query term
    df: dict[str, int] = {}
    for term in set(q_tokens):
        df[term] = sum(1 for d in docs if term in d.tokens)

    scored: list[tuple[KBDoc, float]] = []
    for doc in docs:
        dl = len(doc.tokens) or 1
        score = 0.0
        for term in q_tokens:
            f = doc.tokens.count(term)
            if f == 0:
                continue
            idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            denom = f + k1 * (1 - b + b * dl / avgdl)
            score += idf * (f * (k1 + 1)) / denom
        if score > 0:
            scored.append((doc, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def search(query: str, top_k: int = 3) -> list[dict]:
    docs = load_kb()
    scored = _bm25_scores(query, docs)
    results = []
    for doc, score in scored[:top_k]:
        snippet = doc.body[:280] + ("..." if len(doc.body) > 280 else "")
        results.append(
            {"slug": doc.slug, "title": doc.title, "score": round(score, 3), "snippet": snippet, "body": doc.body}
        )
    return results


def all_docs() -> list[dict]:
    return [{"slug": d.slug, "title": d.title, "body": d.body} for d in load_kb()]
