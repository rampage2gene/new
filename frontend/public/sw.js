/* A deliberately empty service worker.
 *
 * It exists so a phone browser offers "install"/"Add to Home Screen" for the
 * app. It caches nothing: the app is a window onto the computer running it, so
 * an offline copy could only show a shell that cannot answer a single request.
 */
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
