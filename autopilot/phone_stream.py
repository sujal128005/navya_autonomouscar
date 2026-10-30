"""Watch Navya from a phone: a small web server on the laptop streams the views and status.

The phone must be on the same network as the laptop. Easiest: switch on the laptop's
Windows Mobile Hotspot, join it from the phone, then open the address printed at
start-up (usually http://192.168.137.1:8080). Any phone browser works; nothing to install.
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cv2

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>@TITLE@</title>
<style>
body{margin:0;background:#111;color:#eee;font-family:system-ui,sans-serif}
header{position:sticky;top:0;z-index:1;background:#1b1b1b;padding:8px 12px;display:flex;flex-wrap:wrap;
  gap:6px 14px;align-items:center;border-bottom:1px solid #333}
.mode{font-weight:700;font-size:1.3em;padding:2px 10px;border-radius:6px;background:#555}
.AUTO{background:#1e7d32}.MANUAL{background:#8a6d00}.NO_RC,.NO_LINK,.STALE{background:#b71c1c}
.kv b{color:#8cf;font-weight:600;margin-right:4px}
.obstacle{font-size:1.4em;font-weight:700}
#age{color:#f66;font-weight:700}
.btns{display:flex;gap:8px;flex-wrap:wrap;padding:8px 12px 0}
button{font-size:1em;padding:10px 16px;border-radius:8px;border:0;background:#3a3a3a;color:#fff}
main{padding:8px;display:grid;gap:10px}
h2{font-size:.85em;margin:2px 0 4px;color:#aaa;font-weight:500}
img{width:100%;height:auto;border-radius:6px;background:#000;display:block}
@media(min-width:900px){main{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><span id="mode" class="mode">...</span><span id="fields"></span><span id="age"></span></header>
<div class="btns">@BUTTONS@</div>
<main>@VIEWS@</main>
<script>
async function tick(){
  try{
    const s = await (await fetch('/status',{cache:'no-store'})).json();
    const stale = s._age_s > 2;
    const m = document.getElementById('mode');
    m.textContent = stale ? 'NO UPDATES' : (s.mode || '?');
    m.className = 'mode ' + (stale ? 'STALE' : (s.mode || ''));
    const f = document.getElementById('fields'); f.replaceChildren();
    for (const [k, v] of Object.entries(s)) {
      if (k === 'mode' || k.startsWith('_')) continue;
      const span = document.createElement('span'); span.className = 'kv ' + k;
      const b = document.createElement('b'); b.textContent = k; span.append(b, String(v));
      f.append(span, ' ');
    }
    document.getElementById('age').textContent = stale ? 'program stopped or laptop busy' : '';
  } catch (e) { document.getElementById('age').textContent = 'connection lost'; }
}
setInterval(tick, 500); tick();
function cmd(k){ fetch('/cmd?k=' + encodeURIComponent(k)); }
for (const img of document.querySelectorAll('img')) {
  img.onerror = () => setTimeout(() => { img.src = img.dataset.src + '?t=' + Date.now(); }, 1000);
}
</script></body></html>
"""


class PhoneStream:
    def __init__(self, title: str, views: dict[str, str], buttons: dict[str, str] | None = None,
                 port: int = 8080, max_fps: float = 10.0):
        """views: {name: caption}; buttons: {caption: command} sent back through pop_commands()."""
        self.title, self.views, self.buttons = title, views, buttons or {}
        self.port, self.max_fps = port, max_fps
        self._cond = threading.Condition()
        self._jpeg: dict[str, bytes] = {}
        self._last_publish: dict[str, float] = {}
        self._status: dict = {}
        self._status_time = 0.0
        self._commands: list[str] = []
        self._viewers = 0
        self._server = ThreadingHTTPServer(("0.0.0.0", port), self._handler_class())
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def addresses(self) -> list[str]:
        ips = set()
        try:
            ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        return [f"http://{ip}:{self.port}" for ip in sorted(ips) if not ip.startswith("127.")]

    def print_addresses(self):
        print("Phone view: join the laptop's network, then open one of:")
        for url in self.addresses() or [f"http://<laptop-ip>:{self.port}"]:
            print("   ", url)

    def publish(self, name: str, image_bgr):
        """Offer a new picture for a view; skipped when nobody is watching or faster than max_fps."""
        now = time.monotonic()
        if self._viewers == 0 or now - self._last_publish.get(name, 0.0) < 1.0 / self.max_fps:
            return
        self._last_publish[name] = now
        ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self._cond:
                self._jpeg[name] = buf.tobytes()
                self._cond.notify_all()

    def set_status(self, **fields):
        with self._cond:
            self._status = fields
            self._status_time = time.monotonic()

    def pop_commands(self) -> list[str]:
        with self._cond:
            cmds, self._commands = self._commands, []
        return cmds

    def close(self):
        self._server.shutdown()
        self._server.server_close()

    def _page(self) -> bytes:
        buttons = "".join(f'<button onclick="cmd(\'{cmd}\')">{caption}</button>'
                          for caption, cmd in self.buttons.items())
        views = "".join(f'<section><h2>{caption}</h2><img src="/stream/{name}" data-src="/stream/{name}"></section>'
                        for name, caption in self.views.items())
        html = PAGE.replace("@TITLE@", self.title).replace("@BUTTONS@", buttons).replace("@VIEWS@", views)
        return html.encode("utf-8")

    def _handler_class(self):
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                url = urlparse(self.path)
                if url.path == "/":
                    self._send(200, "text/html; charset=utf-8", stream._page())
                elif url.path == "/status":
                    with stream._cond:
                        body = dict(stream._status, _age_s=round(time.monotonic() - stream._status_time, 1))
                    self._send(200, "application/json", json.dumps(body).encode())
                elif url.path == "/cmd":
                    k = parse_qs(url.query).get("k", [""])[0]
                    if k in stream.buttons.values():
                        with stream._cond:
                            stream._commands.append(k)
                    self._send(204, "text/plain")
                elif url.path.startswith("/stream/") and url.path[8:] in stream.views:
                    self._stream(url.path[8:])
                else:
                    self._send(404, "text/plain", b"not found")

            def _send(self, code, ctype, body=b""):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _stream(self, name):
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                with stream._cond:
                    stream._viewers += 1
                last = None
                try:
                    while True:
                        with stream._cond:
                            stream._cond.wait_for(lambda: stream._jpeg.get(name) is not last, timeout=2.0)
                            jpg = stream._jpeg.get(name)
                        if jpg is None or jpg is last:
                            continue
                        last = jpg
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                except OSError:
                    pass  # phone went away
                finally:
                    with stream._cond:
                        stream._viewers -= 1

        return Handler
