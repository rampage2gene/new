import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { openCount } from "../verification";
import PageViewer from "../components/PageViewer";
import AssistantPanel from "../components/AssistantPanel";
import TechnicalDataTab from "../components/TechnicalDataTab";
import StructureTab from "../components/StructureTab";
import QCTab from "../components/QCTab";
import FillInTab from "../components/FillInTab";
import DiagramTab from "../components/DiagramTab";
import ExportMenu from "../components/ExportMenu";
import type { BBox, DocumentDetail, Highlight } from "../types";

export type Jump = (page: number, bbox?: BBox | null, kind?: Highlight["kind"], label?: string) => void;
type Tab = "assistant" | "data" | "structure" | "fill" | "qc" | "diagram";
const TABS: Tab[] = ["assistant", "data", "structure", "fill", "qc", "diagram"];

export default function DocumentPage() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(Number(params.get("page")) || 1);
  const [highlights, setHighlights] = useState<Highlight[]>([]);
  const wanted = params.get("tab") as Tab | null;
  const [tab, setTab] = useState<Tab>(wanted && TABS.includes(wanted) ? wanted : "assistant");

  const reload = useCallback(() => api.getDocument(id).then(setDoc).catch((e) => setError(e.message)), [id]);
  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    const bb = params.get("bbox");
    if (bb) {
      const parts = bb.split(",").map(Number) as BBox;
      if (parts.length === 4 && parts.every((n) => !isNaN(n))) setHighlights([{ bbox: parts, kind: "primary" }]);
    }
    // only on first load
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Asking for the spot already on screen has to be a real no-op. In To fill in
  // every way of touching a row asks for its page, so one row can ask several
  // times over; handing back a fresh list each time would restart the page
  // view's scroll-to-the-value and drag the page away from someone who had
  // just scrolled it themselves.
  const jump: Jump = useCallback((p, bbox, kind = "primary", label) => {
    setPage(p);
    setHighlights((prev) => {
      if (!bbox) return prev.length === 0 ? prev : [];
      const cur = prev[0];
      const same = prev.length === 1 && cur.kind === kind && cur.label === label && cur.bbox.every((n, i) => n === bbox[i]);
      return same ? prev : [{ bbox, kind, label }];
    });
  }, []);

  const setComponentHighlights = useCallback((hs: Highlight[]) => setHighlights(hs), []);

  // Six tabs do not fit at any width, so the strip scrolls. Bring the active
  // one into view: arriving from the library's "N to fill in" link used to
  // land on a tab that was off-screen, with none of the visible tabs marked.
  const tabStrip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    tabStrip.current?.querySelector(".active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [tab, doc]);

  const counts = useMemo(() => ({
    data: doc?.stats?.entities ? Object.values(doc.stats.entities).reduce((a, b) => a + b, 0) : 0,
    qc: doc?.stats?.qc_flags || 0,
    fill: doc ? openCount(doc) : 0,  // the same rule the To fill in list uses
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
        <ExportMenu doc={doc} />
      </div>
      <div className="viewer">
        <div className="viewer-left">
          <PageViewer doc={doc} page={page} onPageChange={(p) => { setPage(p); setHighlights((h) => h.filter((x) => x.kind === "component")); }} highlights={highlights} onBlockClick={(b) => setHighlights([{ bbox: b.bbox, kind: "secondary", label: b.block_type }])} />
        </div>
        <div className="viewer-right">
          <div className="tabs" ref={tabStrip}>
            <button className={tab === "assistant" ? "active" : ""} onClick={() => setTab("assistant")}>AI Assistant</button>
            <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}>Technical Data<span className="badge count">{counts.data}</span></button>
            <button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}>Structure</button>
            <button className={tab === "fill" ? "active" : ""} onClick={() => setTab("fill")} title="Values the readers did not settle: fill them in or confirm them from the page">To fill in{counts.fill ? <span className="badge count warn">{counts.fill}</span> : null}</button>
            <button className={tab === "qc" ? "active" : ""} onClick={() => setTab("qc")}>Verification{counts.qc ? <span className={`badge count ${doc.stats.critical_flags ? "crit" : "warn"}`}>{counts.qc}</span> : null}</button>
            <button className={tab === "diagram" ? "active" : ""} onClick={() => setTab("diagram")}>Diagram{counts.diagram ? <span className="badge count accent">{counts.diagram}</span> : null}</button>
          </div>
          <div className="tab-body" style={{ display: tab === "assistant" ? "flex" : "block", flexDirection: "column" }}>
            {tab === "assistant" && <AssistantPanel doc={doc} jump={jump} />}
            {tab === "data" && <TechnicalDataTab doc={doc} jump={jump} />}
            {tab === "structure" && <StructureTab doc={doc} jump={jump} />}
            {tab === "fill" && <FillInTab doc={doc} jump={jump} page={page} onChanged={reload} />}
            {tab === "qc" && <QCTab doc={doc} jump={jump} />}
            {tab === "diagram" && <DiagramTab doc={doc} page={page} jump={jump} setHighlights={setComponentHighlights} />}
          </div>
        </div>
      </div>
    </>
  );
}
