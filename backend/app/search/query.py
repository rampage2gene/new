"""Hybrid retrieval: keyword (FTS5 + synonyms) + semantic + entity + section-aware.

Results are fused with reciprocal rank fusion and returned with the chunk's
page, section and bounding box so every hit can be opened and highlighted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select, text as sql_text
from sqlalchemy.orm import Session

from ..extraction import patterns as P
from ..models import Chunk, Document, Embedding, Entity
from .semantic import get_embedding_provider
from .synonyms import expand_terms

ENTITY_TYPE_TERMS: dict[str, list[str]] = {
    "fuse": ["fuse", "fuses", "fusing", "fuse rating", "fuse size"],
    "breaker": ["breaker", "breakers", "circuit breaker", "circuit breakers"],
    "wire_size": ["wire size", "cable size", "wire gauge", "awg", "cable gauge", "conductor size", "wire sizes", "cable sizes", "mm²"],
    "voltage": ["voltage", "volts", "voltages"],
    "current": ["current", "amps", "amperage", "currents", "input current", "output current", "max current", "maximum current"],
    "torque": ["torque", "tightening torque", "torque setting"],
    "temperature": ["temperature", "operating temperature", "ambient"],
    "power": ["power", "watts", "wattage", "rated power"],
    "capacity": ["capacity", "amp hours", "ah", "kwh"],
    "clearance": ["clearance", "clearances", "ventilation", "spacing"],
    "equipment": ["equipment", "model", "models", "devices"],
    "terminal_size": ["terminal size", "stud size", "terminal"],
}

SEMANTIC_STRONG = 0.12  # cosine similarity below this is treated as weak evidence

_ENTITY_VALUE_RE = re.compile(
    rf"(?P<num>{P.NUM})\s*(?P<unit>volts?|v|vdc|vac|amps?|a|watts?|w|kw|awg|mm²|hz|ah|n·m|nm|°c|°f)\b", re.I
)


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    document_name: str
    page_number: int
    section: str | None
    text: str
    bbox: list[float]
    score: float
    sources: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    source_scores: dict = field(default_factory=dict)
    strong: bool = True


@dataclass
class ParsedQuery:
    raw: str
    entity_types: list[str]
    value: float | None = None
    unit: str | None = None
    expansions: dict[str, set[str]] = field(default_factory=dict)


def parse_query(q: str) -> ParsedQuery:
    ql = q.lower()
    types = []
    for etype, terms in ENTITY_TYPE_TERMS.items():
        if any(re.search(r"(?<![\w])" + re.escape(t) + r"(?![\w])", ql) for t in terms):
            types.append(etype)
    pq = ParsedQuery(raw=q, entity_types=types, expansions=expand_terms(q))
    m = _ENTITY_VALUE_RE.search(q)
    if m:
        pq.value = P.parse_number(m.group("num"))
        u = m.group("unit").lower()
        pq.unit = {"volts": "V", "volt": "V", "v": "V", "vdc": "V", "vac": "V", "amps": "A", "amp": "A", "a": "A", "watts": "W", "watt": "W", "w": "W", "kw": "kW", "awg": "AWG", "hz": "Hz", "ah": "Ah", "n·m": "N·m", "nm": "N·m", "°c": "°C", "°f": "°F", "mm²": "mm²"}.get(u, u)
    return pq


_STOP = set("what which where how does do the a an this that is are of for to in on with and or find all every mention mentions size required require need needs should be used use my it its does".split())


def _stem(word: str) -> str:
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("es") and not w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _query_groups(pq: ParsedQuery) -> list[list[str]]:
    """Content groups: each is a list of alternative surface forms (synonyms)."""
    q = pq.raw.lower()
    groups: list[list[str]] = []
    consumed = q
    for phrase, syns in pq.expansions.items():
        groups.append([phrase] + sorted(syns))
        consumed = re.sub(r"(?<![\w])" + re.escape(phrase) + r"(?:e?s)?(?![\w])", " ", consumed)
    for w in re.findall(r"[a-z0-9][a-z0-9/.\-²]*", consumed):
        if w in _STOP or len(w) < 2:
            continue
        groups.append([w])
    return groups


def _fts_query(pq: ParsedQuery) -> str:
    """FTS5 MATCH expression: OR over every alternative (ranking rewards chunks that
    match more groups - see _fts_search)."""
    terms: list[str] = []
    for group in _query_groups(pq):
        for alt in group:
            alt = alt.replace('"', "")
            stem = _stem(alt) if " " not in alt else alt
            if stem.isalpha() and len(stem) >= 3:
                terms.append(f'"{stem}"*')
            else:
                terms.append(f'"{alt}"')
    return " OR ".join(dict.fromkeys(terms))


def _group_matches(text: str, groups: list[list[str]]) -> int:
    tl = text.lower()
    n = 0
    for group in groups:
        for alt in group:
            stem = _stem(alt) if " " not in alt else alt
            if re.search(r"(?<![\w])" + re.escape(stem), tl):
                n += 1
                break
    return n


def _fts_search(session: Session, pq: ParsedQuery, document_ids: list[str] | None, limit: int) -> list[tuple[str, float, int, int]]:
    """Returns (chunk_id, score, matched_groups, total_groups)."""
    groups = _query_groups(pq)
    expr = _fts_query(pq)
    if not expr:
        return []
    doc_filter = ""
    params: dict = {"q": expr, "limit": limit * 2}
    if document_ids:
        placeholders = ",".join(f":d{i}" for i in range(len(document_ids)))
        doc_filter = f" AND document_id IN ({placeholders})"
        params.update({f"d{i}": d for i, d in enumerate(document_ids)})
    sql = f"SELECT chunk_id, body, bm25(chunks_fts, 0, 0, 0, 2.0, 1.0) AS rank FROM chunks_fts WHERE chunks_fts MATCH :q{doc_filter} ORDER BY rank LIMIT :limit"
    try:
        rows = session.execute(sql_text(sql), params).all()
    except Exception:
        return []
    scored = []
    total = len(groups)
    for cid, body, rank in rows:
        matched = _group_matches(body or "", groups)
        scored.append((cid, matched * 3.0 + min(3.0, float(-rank)), matched, total))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]


def _semantic_search(session: Session, pq: ParsedQuery, document_ids: list[str] | None, limit: int) -> list[tuple[str, float]]:
    provider = get_embedding_provider()
    stmt = select(Embedding.chunk_id, Embedding.vector, Embedding.dim).where(Embedding.provider == provider.name)
    if document_ids:
        stmt = stmt.where(Embedding.document_id.in_(document_ids))
    rows = session.execute(stmt).all()
    if not rows:
        return []
    qv = provider.embed_query(pq.raw + " " + " ".join(" ".join(s) for s in pq.expansions.values()))
    ids = [r[0] for r in rows]
    mat = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
    if mat.shape[1] != qv.shape[0]:
        return []
    sims = mat @ qv
    order = np.argsort(-sims)[:limit]
    return [(ids[i], float(sims[i])) for i in order if sims[i] > 0.02]


def _entity_search(session: Session, pq: ParsedQuery, document_ids: list[str] | None, limit: int) -> list[tuple[str, float, Entity]]:
    if not pq.entity_types and pq.value is None:
        return []
    stmt = select(Entity)
    if document_ids:
        stmt = stmt.where(Entity.document_id.in_(document_ids))
    if pq.entity_types:
        types = set(pq.entity_types)
        if "current" in types:
            types.update({"fuse", "breaker"})
        stmt = stmt.where(Entity.entity_type.in_(list(types)))
    if pq.value is not None:
        lo, hi = pq.value * 0.999, pq.value * 1.001
        stmt = stmt.where(Entity.value >= lo, Entity.value <= hi)
        if pq.unit in ("V", "A", "W", "AWG", "Hz", "Ah"):
            type_for_unit = {"V": ["voltage"], "A": ["current", "fuse", "breaker"], "W": ["power"], "AWG": ["wire_size"], "Hz": ["frequency"], "Ah": ["capacity"]}[pq.unit]
            stmt = stmt.where(Entity.entity_type.in_(type_for_unit))
    ents = session.execute(stmt.limit(limit * 4)).scalars().all()
    # Map to chunks by block id.
    if not ents:
        return []
    block_ids = {e.block_id for e in ents if e.block_id}
    chunk_by_block: dict[str, str] = {}
    cstmt = select(Chunk.id, Chunk.block_ids).where(Chunk.document_id.in_({e.document_id for e in ents}))
    for cid, bids in session.execute(cstmt).all():
        for b in bids or []:
            if b in block_ids:
                chunk_by_block[b] = cid
    out = []
    for e in ents:
        cid = chunk_by_block.get(e.block_id or "")
        if cid:
            out.append((cid, e.confidence, e))
    return out[:limit]


def search(session: Session, query: str, document_ids: list[str] | None = None, limit: int = 12) -> tuple[ParsedQuery, list[SearchHit]]:
    pq = parse_query(query)
    fts = _fts_search(session, pq, document_ids, limit * 3)
    sem = _semantic_search(session, pq, document_ids, limit * 3)
    ents = _entity_search(session, pq, document_ids, limit * 3)

    # Reciprocal rank fusion. Weak evidence (a partial keyword match or a low
    # semantic similarity) is fused with a lower weight and flagged so callers
    # can tell "found something" from "found nothing relevant".
    k = 60.0
    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    detail: dict[str, dict] = {}
    for rank, (cid, sc, matched, total) in enumerate(fts):
        strong_kw = matched >= max(1, (total + 1) // 2)
        label = "keyword" if strong_kw else "keyword_partial"
        scores[cid] = scores.get(cid, 0) + (1.0 if strong_kw else 0.35) / (k + rank)
        sources.setdefault(cid, set()).add(label)
        detail.setdefault(cid, {})["keyword"] = {"matched_groups": matched, "total_groups": total, "score": round(sc, 3)}
    for rank, (cid, sim) in enumerate(sem):
        strong_sem = sim >= SEMANTIC_STRONG
        scores[cid] = scores.get(cid, 0) + (0.8 if strong_sem else 0.25) / (k + rank)
        sources.setdefault(cid, set()).add("semantic" if strong_sem else "semantic_weak")
        detail.setdefault(cid, {})["semantic"] = round(sim, 4)
    seen_ent: set[str] = set()
    for rank, (cid, _, ent) in enumerate(ents):
        if cid in seen_ent:
            continue
        seen_ent.add(cid)
        scores[cid] = scores.get(cid, 0) + 1.2 / (k + rank)
        sources.setdefault(cid, set()).add("entity")
        detail.setdefault(cid, {})["entity"] = ent.entity_type
    if not scores:
        return pq, []
    top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: limit * 2]
    chunk_ids = [cid for cid, _ in top]
    chunks = {c.id: c for c in session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids))).scalars().all()}
    doc_names = {d.id: (d.title or d.filename) for d in session.execute(select(Document).where(Document.id.in_({c.document_id for c in chunks.values()}))).scalars().all()}

    # Section-aware boost: query terms appearing in the section title.
    terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    hits: list[SearchHit] = []
    for cid, score in top:
        c = chunks.get(cid)
        if not c:
            continue
        sec = (c.section or "").lower()
        if sec and any(t in sec for t in terms):
            score *= 1.15
        hits.append(
            SearchHit(
                chunk_id=c.id,
                document_id=c.document_id,
                document_name=doc_names.get(c.document_id, ""),
                page_number=c.page_number,
                section=c.section,
                text=c.text,
                bbox=[c.x0, c.y0, c.x1, c.y1],
                score=round(score, 5),
                sources=sorted(sources.get(cid, set())),
                highlights=_highlight_terms(c.text, pq),
                source_scores=detail.get(cid, {}),
                strong=bool(sources.get(cid, set()) & {"keyword", "semantic", "entity"}),
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return pq, hits[:limit]


def _highlight_terms(text: str, pq: ParsedQuery) -> list[str]:
    found: list[str] = []
    tl = text.lower()
    cands = set()
    for phrase, syns in pq.expansions.items():
        cands.add(phrase)
        cands.update(syns)
    for w in re.findall(r"[a-z0-9][a-z0-9/.\-²]{2,}", pq.raw.lower()):
        cands.add(w)
    for c in sorted(cands, key=len, reverse=True):
        if len(c) < 2:
            continue
        stem = _stem(c) if " " not in c else c
        if re.search(r"(?<![\w])" + re.escape(stem), tl):
            found.append(c)
    if pq.value is not None:
        vt = f"{pq.value:g}"
        if vt in tl:
            found.append(vt)
    return found[:8]
