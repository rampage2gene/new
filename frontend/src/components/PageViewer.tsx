import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Block, DocumentDetail, Highlight, PageData } from "../types";

interface Props {
  doc: DocumentDetail;
  page: number;
  onPageChange: (p: number) => void;
  highlights: Highlight[];
  onBlockClick?: (b: Block) => void;
}

export default function PageViewer({ doc, page, onPageChange, highlights, onBlockClick }: Props) {
  const [zoom, setZoom] = useState(100);
  const [pageData, setPageData] = useState<PageData | null>(null);
  const [showBlocks, setShowBlocks] = useState(false);
  const meta = doc.pages.find((p) => p.page_number === page);

  useEffect(() => {
    let alive = true;
    setPageData(null);
    api.getPage(doc.id, page).then((d) => alive && setPageData(d)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [doc.id, page]);

  useEffect(() => {
    const el = document.querySelector(".hl.primary");
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlights, pageData]);

  const width = meta?.width || 612;
  const height = meta?.height || 792;
  const style = useMemo(() => ({ width: `${zoom}%`, aspectRatio: `${width} / ${height}` }), [zoom, width, height]);
  const toPct = (b: [number, number, number, number]) => ({
    left: `${(b[0] / width) * 100}%`,
    top: `${(b[1] / height) * 100}%`,
    width: `${((b[2] - b[0]) / width) * 100}%`,
    height: `${((b[3] - b[1]) / height) * 100}%`,
  });

  return (
    <>
      <div className="viewer-toolbar">
        <button className="btn sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>‹ Prev</button>
        <span>
          Page{" "}
          <input type="number" min={1} max={doc.page_count} value={page} onChange={(e) => { const v = Number(e.target.value); if (v >= 1 && v <= doc.page_count) onPageChange(v); }} />{" "}
          of {doc.page_count}
        </span>
        <button className="btn sm" disabled={page >= doc.page_count} onClick={() => onPageChange(page + 1)}>Next ›</button>
        <span className="muted small">
          {meta?.text_source === "ocr" ? <span className="badge warn">OCR {meta.ocr_confidence != null ? `${Math.round(meta.ocr_confidence * 100)}%` : ""}</span> : meta?.text_source === "embedded" ? <span className="badge ok">embedded text</span> : <span className="badge">no text</span>}{" "}
          {meta?.is_diagram && <span className="badge accent">diagram</span>}
        </span>
        <span className="grow" />
        <label className="small muted"><input type="checkbox" checked={showBlocks} onChange={(e) => setShowBlocks(e.target.checked)} /> text blocks</label>
        <button className="btn sm" onClick={() => setZoom((z) => Math.max(40, z - 15))}>−</button>
        <span className="small mono">{zoom}%</span>
        <button className="btn sm" onClick={() => setZoom((z) => Math.min(250, z + 15))}>+</button>
        <a className="btn sm" href={api.originalUrl(doc.id)} target="_blank" rel="noreferrer">Original</a>
      </div>
      <div className="page-scroll">
        <div className="page-canvas" style={style}>
          <img src={api.pageImageUrl(doc.id, page)} alt={`Page ${page}`} />
          {showBlocks && pageData?.blocks.map((b) => (
            <div key={b.id} className="block-hit" style={toPct(b.bbox)} title={`${b.block_type}${b.section ? " · " + b.section : ""}`} onClick={() => onBlockClick?.(b)} />
          ))}
          {highlights.map((h, i) => (
            <div key={i} className={`hl ${h.kind}${h.confidence ? " " + h.confidence : ""}`} style={toPct(h.bbox)} title={h.label}>
              {h.kind === "component" && h.label && <span className="tag">{h.label}</span>}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
