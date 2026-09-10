import { useState } from "react";
import { api, isPhone } from "../api";

/** The one way to stop the app when it runs in a browser tab. The app's own
 *  window has a close box, and a phone must not switch the computer's app
 *  off, so this renders nothing in either of those cases. Asking happens in
 *  place - a second button, not a browser dialog - because stopping ends any
 *  reading in progress with no way back. */
export default function StopApp({ card = false }: { card?: boolean }) {
  const [arming, setArming] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (api.isDesktop() || isPhone()) return null;

  const stop = async () => {
    setError(null);
    try {
      await api.quit();
      setStopped(true);
    } catch (e: any) {
      setError(e?.message ?? String(e));
      setArming(false);
    }
  };
  const body = stopped ? (
    <div className="alert ok">The app has stopped. You can close this tab.</div>
  ) : (
    <>
      {arming ? (
        <div className="row">
          <button className="btn danger" onClick={stop}>Stop now</button>
          <button className="btn" onClick={() => setArming(false)}>Keep running</button>
          <span className="small">Anything being read stops now and carries on the next time the app starts.</span>
        </div>
      ) : (
        <button className="btn" onClick={() => setArming(true)} title="Stop the app running on this computer">Stop the app</button>
      )}
      {error && <div className="alert crit" style={{ marginTop: 8 }}>{error}</div>}
    </>
  );
  if (!card) return <div className="stop">{body}</div>;
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h2 style={{ marginTop: 0 }}>Stop the app</h2>
      <p className="small muted">The app is running in this browser tab rather than in a window of its own, so closing the tab does not stop it. This does.</p>
      {body}
    </div>
  );
}
