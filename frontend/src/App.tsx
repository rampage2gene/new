import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import type { Status } from "./types";
import LibraryPage from "./pages/LibraryPage";
import DocumentPage from "./pages/DocumentPage";
import SearchPage from "./pages/SearchPage";
import CalculatorsPage from "./pages/CalculatorsPage";
import ComparePage from "./pages/ComparePage";
import InvoicesPage from "./pages/InvoicesPage";
import ConvertPage from "./pages/ConvertPage";
import DiagnosticsPage from "./pages/DiagnosticsPage";

const NAV = [
  { to: "/library", label: "Document Library", icon: "▤" },
  { to: "/search", label: "Search", icon: "⌕" },
  { to: "/calculators", label: "Calculators", icon: "∑" },
  { to: "/compare", label: "Compare Documents", icon: "⇄" },
  { to: "/invoices", label: "Invoices & Parts", icon: "¤" },
  { to: "/convert", label: "Convert & Export", icon: "⇩" },
  { to: "/diagnostics", label: "Diagnostics", icon: "⚙" },
];

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          Marine Electrical
          <br />
          Document Intelligence
          <small>OCR · extraction · cited answers · calculators</small>
        </div>
        <nav>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "active" : "")}>
              <span aria-hidden>{n.icon}</span> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="status">
          {status ? (
            <>
              OCR: <b>{status.ocr_engine}</b>
              <br />
              AI reasoning: <b>{status.ai_available ? status.ai_model : "not configured"}</b>
              <br />
              Embeddings: <b>{status.embedding_provider}</b>
              <br />
              <span className="muted">v{status.version}</span>
            </>
          ) : (
            "Connecting to API…"
          )}
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/library" replace />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/documents/:id" element={<DocumentPage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/calculators" element={<CalculatorsPage />} />
          <Route path="/calculators/:calcId" element={<CalculatorsPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/invoices" element={<InvoicesPage />} />
          <Route path="/convert" element={<ConvertPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
        </Routes>
      </main>
    </div>
  );
}
