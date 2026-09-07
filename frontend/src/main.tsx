import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { pairThisDevice } from "./api";
import "./styles.css";

// A phone arrives from the QR code with the pairing key in the address. Trade
// it for a cookie before the first request goes out, so nothing sees a 401.
pairThisDevice().finally(() => {
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
});

// Android only offers "install" for a page with a service worker. This one does
// nothing but pass requests through: the app is useless without the computer
// anyway, so caching it offline would only produce a screen that cannot answer.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* not served over a secure origin, or the browser refused: not important */
    });
  });
}
