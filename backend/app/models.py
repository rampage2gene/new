"""ORM models.

Storage is deliberately split into layers that mirror the pipeline:

* ``documents`` / ``pages``       - file identity and page geometry
* ``blocks``                      - extracted text with layout + OCR confidence
* ``chunks`` (+ FTS5 / embeddings) - retrieval units for search
* ``entities``                    - structured technical data with source refs
* ``qc_flags``                    - verification layer output
* ``invoices``                    - business document extraction
* ``diagram_analyses``            - visual pipeline output
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(16))  # pdf | image
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(1024))

    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|processing|ready|failed
    progress: Mapped[str | None] = mapped_column(String(256))
    error: Mapped[str | None] = mapped_column(Text)

    page_count: Mapped[int] = mapped_column(Integer, default=0)
    ocr_pages: Mapped[int] = mapped_column(Integer, default=0)
    embedded_text_pages: Mapped[int] = mapped_column(Integer, default=0)

    # Document understanding
    manufacturer: Mapped[str | None] = mapped_column(String(256))
    product: Mapped[str | None] = mapped_column(String(256))
    model_number: Mapped[str | None] = mapped_column(String(256))
    document_type: Mapped[str | None] = mapped_column(String(128))
    revision: Mapped[str | None] = mapped_column(String(128))
    publication_date: Mapped[str | None] = mapped_column(String(64))
    equipment_types: Mapped[list] = mapped_column(JSON, default=list)
    structure: Mapped[dict] = mapped_column(JSON, default=dict)  # sections, warnings, figures, tables
    stats: Mapped[dict] = mapped_column(JSON, default=dict)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pages: Mapped[list["Page"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    blocks: Mapped[list["Block"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    entities: Mapped[list["Entity"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    qc_flags: Mapped[list["QCFlag"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    diagram_analyses: Mapped[list["DiagramAnalysis"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)  # 1-based
    width: Mapped[float] = mapped_column(Float)  # PDF points (or pixels for images)
    height: Mapped[float] = mapped_column(Float)
    text_source: Mapped[str] = mapped_column(String(16))  # embedded | ocr | none
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    is_diagram: Mapped[bool] = mapped_column(Boolean, default=False)
    diagram_score: Mapped[float] = mapped_column(Float, default=0.0)
    image_path: Mapped[str | None] = mapped_column(String(1024))
    text: Mapped[str] = mapped_column(Text, default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    page_label: Mapped[str | None] = mapped_column(String(32))  # printed page number if detected

    document: Mapped[Document] = relationship(back_populates="pages")


class Block(Base):
    __tablename__ = "blocks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(32))  # paragraph|heading|table|caption|warning|note|label|footer
    text: Mapped[str] = mapped_column(Text)
    x0: Mapped[float] = mapped_column(Float)
    y0: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    section: Mapped[str | None] = mapped_column(String(512))
    section_level: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16))  # embedded | ocr
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    words: Mapped[list | None] = mapped_column(JSON)  # [{t, c, bbox:[x0,y0,x1,y1]}] for OCR blocks
    table: Mapped[dict | None] = mapped_column(JSON)  # {"rows": [[cell,...]]} for table blocks

    document: Mapped[Document] = relationship(back_populates="blocks")

    @property
    def bbox(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    section: Mapped[str | None] = mapped_column(String(512))
    block_ids: Mapped[list] = mapped_column(JSON, default=list)
    text: Mapped[str] = mapped_column(Text)
    x0: Mapped[float] = mapped_column(Float, default=0)
    y0: Mapped[float] = mapped_column(Float, default=0)
    x1: Mapped[float] = mapped_column(Float, default=0)
    y1: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Embedding(Base):
    __tablename__ = "embeddings"

    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, index=True)
    block_id: Mapped[str | None] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    value_text: Mapped[str] = mapped_column(String(128))  # normalised display form, e.g. "4/0 AWG"
    raw_text: Mapped[str] = mapped_column(String(128))  # exactly as it appeared
    qualifier: Mapped[str | None] = mapped_column(String(64))  # continuous|peak|surge|maximum|input|output|recommended|...
    application: Mapped[str | None] = mapped_column(String(256))
    circuit: Mapped[str | None] = mapped_column(String(128))  # dc|ac|control|unknown
    equipment: Mapped[str | None] = mapped_column(String(128))
    equipment_model: Mapped[str | None] = mapped_column(String(128))
    device_type: Mapped[str | None] = mapped_column(String(64))  # e.g. fuse class, breaker type
    section: Mapped[str | None] = mapped_column(String(512))
    snippet: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer, default=0)
    char_end: Mapped[int] = mapped_column(Integer, default=0)
    x0: Mapped[float] = mapped_column(Float, default=0)
    y0: Mapped[float] = mapped_column(Float, default=0)
    x1: Mapped[float] = mapped_column(Float, default=0)
    y1: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[Document] = relationship(back_populates="entities")


class QCFlag(Base):
    __tablename__ = "qc_flags"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(32), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(16))  # info | warning | critical
    flag_type: Mapped[str] = mapped_column(String(48))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="qc_flags")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    vendor: Mapped[str | None] = mapped_column(String(256))
    invoice_number: Mapped[str | None] = mapped_column(String(128))
    invoice_date: Mapped[str | None] = mapped_column(String(64))
    currency: Mapped[str | None] = mapped_column(String(8))
    subtotal: Mapped[float | None] = mapped_column(Float)
    tax: Mapped[float | None] = mapped_column(Float)
    total: Mapped[float | None] = mapped_column(Float)
    line_items: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    document: Mapped[Document] = relationship(back_populates="invoices")


class DiagramAnalysis(Base):
    __tablename__ = "diagram_analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(32))  # claude-vision | heuristic
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="diagram_analyses")
