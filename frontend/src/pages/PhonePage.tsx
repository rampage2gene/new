import { useEffect, useState } from "react";
import { api, isPhone } from "../api";
import type { LanInfo } from "../types";

/** "Use on your phone": the QR code that pairs a phone on the same Wi-Fi.
 *
 *  The desktop app serves the same UI on the local network. Scanning the code
 *  opens it on the phone and hands over the pairing key in one step; from then
 *  on the phone is a screen and a camera for the computer, which keeps doing
 *  all the reading, checking and storing. */
export default function PhonePage() {
  const [info, setInfo] = useState<LanInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const onPhone = isPhone();

  useEffect(() => {
    if (onPhone) return;
    api.lan().then(setInfo).catch((e) => setError(e?.message ?? String(e)));
  }, [onPhone]);

  if (onPhone) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>You are on your phone</h1>
            <p>This page is shown on the computer, where the QR code lives.</p>
          </div>
        </div>
        <div className="card">
          <p>
            You are connected to the app running on the computer at <b>{window.location.host}</b>. Everything you
            do here happens there: the documents, the reading and the exported files all stay on that machine.
          </p>
          <p className="muted small">
            If the app stops answering, check that the computer is still switched on and awake and that you are on
            the same Wi-Fi.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Use on your phone</h1>
          <p>Read, photograph and fill in values from your phone. Nothing leaves your Wi-Fi.</p>
        </div>
      </div>

      {error && <div className="alert crit">{error}</div>}

      {info && !info.enabled && (
        <div className="alert warn">
          Phone access is switched off (<span className="mono">MDI_LAN=false</span> in <span className="mono">settings.env</span>).
          Remove that line and restart the app.
        </div>
      )}

      {info && info.enabled && info.urls.length === 0 && (
        <div className="alert warn">
          This computer is not on a local network the phone could reach. Connect it to your Wi-Fi (or the boat's
          router) and reload this page.
        </div>
      )}

      {info && info.enabled && info.urls.length > 0 && (
        <div className="phone-pair">
          <div className="card qr-card">
            <img className="qr" src={api.lanQrUrl()} alt="QR code that opens the app on your phone" width={280} height={280} />
            <div className="small muted">Point the phone camera at this code</div>
          </div>
          <div className="card grow">
            <h2>Three steps</h2>
            <ol className="steps-plain">
              <li>Put the phone on the same Wi-Fi as this computer.</li>
              <li>Open the camera and point it at the code, then tap the link that appears.</li>
              <li>In the phone's browser menu choose <b>Add to Home Screen</b> so it opens like an app.</li>
            </ol>
            <h3>Or type the address</h3>
            {info.urls.map((u) => (
              <div key={u} className="mono small addr">{u}</div>
            ))}
            <p className="muted small">
              The <span className="mono">key</span> in the address is this installation's pairing code; the phone
              remembers it, so you only scan once.
            </p>
          </div>
        </div>
      )}

      <div className="card">
        <h2>Worth knowing</h2>
        <ul className="plain">
          <li><b>The computer has to stay on.</b> The phone is a screen and a camera; the app itself runs here.</li>
          <li><b>Windows asks once.</b> The first time the app listens on the network, Windows shows a firewall
            prompt: allow it on <b>private networks</b>. Without that the phone cannot connect.</li>
          <li><b>Nothing leaves the network.</b> Pages, values and exports stay on this computer, as they do now.</li>
          <li><b>Anyone who scans the code can use the app</b> while they are on this Wi-Fi. To lock it again,
            delete <span className="mono">phone-key.txt</span> in the data folder (Diagnostics shows where that is)
            and restart the app; the next code is a new one.</li>
          <li><b>Photograph a page</b> with <b>Scan with the camera</b> in the library: the shots become one
            document and are read exactly like a scan.</li>
        </ul>
      </div>
    </div>
  );
}
