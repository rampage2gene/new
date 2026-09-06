import { useRef, useState } from "react";
import { api, formatBytes } from "../api";

type Target = "pdf" | "txt" | "md" | "json" | "png";

const TARGETS: { value: Target; label: string; hint: string }[] = [
  { value: "pdf", label: "PDF", hint: "photos and scans (JPG, PNG, TIFF…) become one PDF, one page per image; PDFs pass through" },
  { value: "md", label: "Markdown (.md)", hint: "text with headings, tables and warnings; scanned pages are OCR'd" },
  { value: "txt", label: "Plain text (.txt)", hint: "page-separated text; scanned pages are OCR'd" },
  { value: "json", label: "Structured JSON", hint: "pages, blocks with positions, tables, document outline" },
  { value: "png", label: "Page images (.zip of PNG)", hint: "one PNG per page at the chosen resolution" },
];

function FileDrop({ files, setFiles, multiple = true, accept }: { files: File[]; setFiles: (f: File[]) => void; multiple?: boolean; accept: string }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const add = (list: FileList | null) => {
    if (!list) return;
    const arr = Array.from(list);
    setFiles(multiple ? [...files, ...arr] : arr.slice(0, 1));
  };
  return (
    <>
      <div
        className={`dropzone${over ? " over" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
        onClick={() => ref.current?.click()}
      >
        {multiple ? "Drop files here, or click to choose" : "Drop a PDF here, or click to choose"}
      </div>
      <input ref={ref} type="file" multiple={multiple} accept={accept} style={{ display: "none" }} onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      {files.length > 0 && (
        <ul className="filelist">
          {files.map((f, i) => (
            <li key={i}><span>{f.name} <span className="muted">{formatBytes(f.size)}</span></span><button className="btn sm" onClick={() => setFiles(files.filter((_, j) => j !== i))}>✕</button></li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function ConvertPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [to, setTo] = useState<Target>("md");
  const [ocr, setOcr] = useState(true);
  const [dpi, setDpi] = useState(150);
  const [mergeFiles, setMergeFiles] = useState<File[]>([]);
  const [splitFile, setSplitFile] = useState<File[]>([]);
  const [ranges, setRanges] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: "ok" | "crit"; text: string } | null>(null);

  const run = async (label: string, fn: () => Promise<string>) => {
    setBusy(label);
    setMsg(null);
    try {
      const name = await fn();
      setMsg({ kind: "ok", text: `Saved ${name}` });
    } catch (e: any) {
      setMsg({ kind: "crit", text: e.message });
    } finally {
      setBusy(null);
    }
  };

  const target = TARGETS.find((t) => t.value === to)!;
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Convert &amp; Export</h1>
          <p>Convert files without adding them to the library: PDFs to text, Markdown, JSON or page images (scans are OCR'd), photos to PDF, and merge or split PDFs. Nothing here is stored. For a processed library document, use its Export menu instead: workbook with formulas, searchable PDF, report PDF.</p>
        </div>
      </div>
      {msg && <div className={`alert ${msg.kind}`}>{msg.text}</div>}
      <div className="convert-grid">
        <div className="card">
          <h2>Convert</h2>
          <FileDrop files={files} setFiles={setFiles} accept=".pdf,image/*" multiple={to === "pdf"} />
          <label className="field">
            <span className="lbl">Convert to</span>
            <select value={to} onChange={(e) => { const v = e.target.value as Target; setTo(v); if (v !== "pdf") setFiles((f) => f.slice(0, 1)); }}>
              {TARGETS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
            <div className="small muted">{target.hint}</div>
          </label>
          {(to === "md" || to === "txt" || to === "json") && (
            <label className="field row" style={{ gap: 6 }}>
              <input type="checkbox" checked={ocr} onChange={(e) => setOcr(e.target.checked)} style={{ width: "auto" }} /> <span>OCR pages without a text layer (slower)</span>
            </label>
          )}
          {to === "png" && (
            <label className="field">
              <span className="lbl">Resolution (DPI)</span>
              <input type="number" value={dpi} min={36} max={600} onChange={(e) => setDpi(Number(e.target.value) || 150)} />
            </label>
          )}
          <button className="btn primary" disabled={!files.length || !!busy} onClick={() => run("convert", () => api.convert(files, to, { ocr, dpi }))}>{busy === "convert" ? "Converting…" : "Convert & download"}</button>
        </div>
        <div className="card">
          <h2>Merge PDFs</h2>
          <p className="small muted">Combine PDFs and images into one PDF, in the order listed.</p>
          <FileDrop files={mergeFiles} setFiles={setMergeFiles} accept=".pdf,image/*" />
          <button className="btn primary" disabled={mergeFiles.length < 2 || !!busy} onClick={() => run("merge", () => api.merge(mergeFiles))}>{busy === "merge" ? "Merging…" : "Merge & download"}</button>
        </div>
        <div className="card">
          <h2>Split a PDF</h2>
          <p className="small muted">Page ranges like <kbd>1-3, 5, 7-</kbd> give one PDF per range; leave empty for one PDF per page. You get a .zip.</p>
          <FileDrop files={splitFile} setFiles={setSplitFile} accept=".pdf" multiple={false} />
          <label className="field">
            <span className="lbl">Page ranges (optional)</span>
            <input type="text" value={ranges} placeholder="1-3, 5, 7-" onChange={(e) => setRanges(e.target.value)} />
          </label>
          <button className="btn primary" disabled={!splitFile.length || !!busy} onClick={() => run("split", () => api.split(splitFile[0], ranges.trim() || undefined))}>{busy === "split" ? "Splitting…" : "Split & download"}</button>
        </div>
      </div>
    </div>
  );
}
