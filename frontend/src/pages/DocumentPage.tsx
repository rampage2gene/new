import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import PageViewer from "../components/PageViewer";
import AssistantPanel from "../components/AssistantPanel";
import TechnicalDataTab from "../components/TechnicalDataTab";
import StructureTab from "../components/StructureTab";
import QCTab from "../components/QCTab";
import DiagramTab from "../components/DiagramTab";
import type { BBox, DocumentDetail, Highlight } from "../types";

export type Jump = (page: number, bbox?: BBox | null, kind?: Highlight["kind"], label?: string) => void;

export default function DocumentPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(Number(params.get("page")) || 1);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const [tab, setTab] = useState<"assistant" | "data" | "structure" | "qc" | "diagram">("assistant");

  useEffect(() => {
    api.getDocument(id).then(setDoc).catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    const bb = params.get("bbox");
    if (bb) {
      const parts = bb.split(",").map(Number) as BBox;
      if (parts.length === 4 && parts.every((n) => !isNaN(n))) setHighlights([{ bbox: parts, kind: "primary" }]);
    }
    // only on first load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const jump: Jump = useCallback((p, bbox, kind = "primary", label) => {
    setPage(p);
    setHighlights(bbox ? [{ bbox, kind, label }] : []);
  }, []);

  const setComponentHighlights = useCallback((hs: Highlight[]) => setHighlights(hs), []);

  const counts = useMemo(() => ({
    data: doc?.stats?.entities ? Object.values(doc.stats.entities).reduce((a, b) => a + b, 0) : 0,
    qc: doc?.stats?.qc_flags || 0,
    diagram: doc?.structure?.diagram_pages?.length || 0,
  }), [doc]);

  if (error) return <div className="page"><div className="alert crit">{error}</div></div>;
  if (!doc) return <div className="page"><span className="spinner" /> Loading…</div>;

  return (
    <>
      <div className="viewer-toolbar" style={{ borderBottom: "1px solid var(--border)" }}>
        <Link to="/library" className="btn sm">‹ Library</Link>
        <b>{doc.title}</b>
        <span className="muted small">
          {[doc.manufacturer, doc.document_type, doc.model_number && `model ${doc.model_number}`, doc.revision && `rev ${doc.revision}`, doc.publication_date].filter(Boolean).join(" · ")}
        </span>
        <span className="grow" />
        <a className="btn sm" href={api.exportEntitiesUrl("xlsx", [doc.id])}>Export data (.xlsx)</a>
        <a className="btn sm" href={api.exportEntitiesUrl("json", [doc.id])}>JSON</a>
      </div>
      <div className="viewer">
        <div className="viewer-left">
          <PageViewer doc={doc} page={page} onPageChange={(p) => { setPage(p); setHighlights((h) => h.filter((x) => x.kind === "component")); }} highlights={highlights} onBlockClick={(b) => setHighlights([{ bbox: b.bbox, kind: "secondary", label: b.block_type }])} />
        </div>
        <div className="viewer-right">
          <div className="tabs">
            <button className={tab === "assistant" ? "active" : ""} onClick={() => setTab("assistant")}>AI Assistant</button>
            <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}>Technical Data<span className="badge count">{counts.data}</span></button>
            <button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}>Structure</button>
            <button className={tab === "qc" ? "active" : ""} onClick={() => setTab("qc")}>Verification{counts.qc ? <span className={`badge count ${doc.stats.critical_flags ? "crit" : "warn"}`}>{counts.qc}</span> : null}</button>
            <button className={tab === "diagram" ? "active" : ""} onClick={() => setTab("diagram")}>Diagram{counts.diagram ? <span className="badge count accent">{counts.diagram}</span> : null}</button>
          </div>
          <div className="tab-body" style={{ display: tab === "assistant" ? "flex" : "block", flexDirection: "column" }}>
            {tab === "assistant" && <AssistantPanel doc={doc} jump={jump} />}
            {tab === "data" && <TechnicalDataTab doc={doc} jump={jump} />}
            {tab === "structure" && <StructureTab doc={doc} jump={jump} />}
            {tab === "qc" && <QCTab doc={doc} jump={jump} />}
            {tab === "diagram" && <DiagramTab doc={doc} page={page} jump={jump} setHighlights={setComponentHighlights} />}
          </div>
        </div>
      </div>
    </>
  );
}
