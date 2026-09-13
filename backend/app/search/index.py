"""Chunking and index maintenance (FTS5 + embeddings)."""
from __future__ import annotations

import numpy as np
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from ..ingest.types import RawPage
from ..models import Chunk, Embedding, new_id
from .semantic import get_embedding_provider

MAX_CHUNK_CHARS = 700


def build_chunks(document_id: str, pages: list[RawPage], block_ids: dict[tuple[int, int], str]) -> list[Chunk]:
    """Group consecutive blocks (same page, same section) into retrieval chunks.
    Tables and warnings always form their own chunk so they cite cleanly."""
    chunks: list[Chunk] = []
    for page in pages:
        cur_blocks: list[tuple[int, object]] = []
        cur_len = 0
        cur_section = None

        def flush():
            nonlocal cur_blocks, cur_len
            if not cur_blocks:
                return
            texts = []
            for _, b in cur_blocks:
                if b.block_type == "heading":
                    texts.append(f"## {b.text.strip()}")
                elif b.block_type == "warning":
                    texts.append(f"[WARNING] {b.text.strip()}")
                else:
                    texts.append(b.text.strip())
            xs0 = min(b.bbox[0] for _, b in cur_blocks)
            ys0 = min(b.bbox[1] for _, b in cur_blocks)
            xs1 = max(b.bbox[2] for _, b in cur_blocks)
            ys1 = max(b.bbox[3] for _, b in cur_blocks)
            confs = [b.confidence for _, b in cur_blocks]
            chunks.append(
                Chunk(
                    id=new_id(),
                    document_id=document_id,
                    page_number=page.page_number,
                    section=cur_blocks[0][1].section,
                    block_ids=[block_ids[(page.page_number, i)] for i, _ in cur_blocks],
                    text="\n".join(texts),
                    x0=xs0, y0=ys0, x1=xs1, y1=ys1,
                    confidence=sum(confs) / len(confs),
                )
            )
            cur_blocks = []
            cur_len = 0

        for i, b in enumerate(page.blocks):
            if b.block_type in ("header", "footer", "page_number") or not b.text.strip():
                continue
            standalone = b.block_type in ("table", "warning")
            if standalone or (cur_blocks and (b.section != cur_section or cur_len + len(b.text) > MAX_CHUNK_CHARS)):
                flush()
            if b.block_type == "heading" and cur_blocks:
                flush()
            cur_section = b.section
            cur_blocks.append((i, b))
            cur_len += len(b.text)
            if standalone:
                flush()
        flush()
    return chunks


def index_chunks(session: Session, chunks: list[Chunk]) -> None:
    provider = get_embedding_provider()
    rows = [
        {"chunk_id": c.id, "document_id": c.document_id, "page_number": c.page_number, "section": c.section or "", "body": c.text}
        for c in chunks
    ]
    if rows:
        session.execute(
            sql_text(
                "INSERT INTO chunks_fts(chunk_id, document_id, page_number, section, body) "
                "VALUES (:chunk_id, :document_id, :page_number, :section, :body)"
            ),
            rows,
        )
    if chunks:
        vectors = provider.embed([c.text for c in chunks])
        for c, v in zip(chunks, vectors):
            session.add(
                Embedding(chunk_id=c.id, document_id=c.document_id, provider=provider.name, dim=int(v.shape[0]), vector=np.asarray(v, dtype=np.float32).tobytes())
            )


def remove_document_index(session: Session, document_id: str) -> None:
    session.execute(sql_text("DELETE FROM chunks_fts WHERE document_id = :d"), {"document_id": document_id, "d": document_id})
    session.execute(sql_text("DELETE FROM embeddings WHERE document_id = :d"), {"d": document_id})
