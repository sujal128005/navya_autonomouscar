"""Watch Navya from a phone: a small web server on the laptop streams the views and status.

The phone must be on the same network as the laptop. Easiest: switch on the laptop's
Windows Mobile Hotspot, join it from the phone, then open the address printed at
start-up (usually http://192.168.137.1:8080). Any phone browser works; nothing to install.
"""

import json
import os
import socket
import subprocess
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
.kv.ai{flex-basis:100%;background:#1d2a3a;padding:8px;border-radius:6px;line-height:1.35}
.panel{padding:8px 12px 0}
details summary{cursor:pointer;color:#8cf;font-weight:600;padding:6px 0}
.slider{display:grid;grid-template-columns:1fr auto;gap:2px 8px;margin:8px 0}
.slider input{grid-column:1/3;width:100%}
.ask{display:flex;gap:8px}
.ask input{flex:1;font-size:1em;padding:9px;border-radius:8px;border:0;background:#2a2a2a;color:#fff}
@media(min-width:900px){main{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><span id="mode" class="mode">...</span><span id="fields"></span><span id="age"></span></header>
<div class="btns">@BUTTONS@</div>
@ASK@
@TUNE@
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
function ask(){
  const q = document.getElementById('q');
  fetch('/ask?q=' + encodeURIComponent(q ? q.value : ''));
  if (q) q.value = '';
}
async function loadSettings(){
  const box = document.getElementById('sliders');
  if (!box) return;
  const r = await (await fetch('/settings', {cache: 'no-store'})).json();
  box.replaceChildren();
  for (const m of r.meta) {
    const row = document.createElement('label'); row.className = 'slider';
    const name = document.createElement('span'); name.textContent = m.label;
    const shown = document.createElement('b'); shown.textContent = r.values[m.name];
    const inp = document.createElement('input');
    Object.assign(inp, {type: 'range', min: m.low, max: m.high, step: m.step, value: r.values[m.name]});
    inp.oninput = () => { shown.textContent = inp.value; };
    inp.onchange = async () => {
      await fetch('/set?k=' + m.name + '&v=' + inp.value);
      setTimeout(loadSettings, 400);   // shows any value the car adjusted to stay consistent
    };
    row.append(name, shown, inp);
    box.append(row);
  }
}
loadSettings();
for (const img of document.querySelectorAll('img')) {
  img.onerror = () => setTimeout(() => { img.src = img.dataset.src + '?t=' + Date.now(); }, 1000);
}
</script></body></html>
"""


class PhoneStream:
    def __init__(self, title: str, views: dict[str, str], buttons: dict[str, str] | None = None,
                 port: int = 8080, max_fps: float = 10.0, settings=None, settings_values=None,
                 ask: bool = False):
        """views: {name: caption}; buttons: {caption: command} sent back through pop_commands().
        settings: list of objects with name/label/low/high/step shown as sliders, with
        settings_values() giving their current values; changes come back through pop_settings().
        ask: show an 'Ask Navya' box; questions come back through pop_questions()."""
        self.title, self.views, self.buttons = title, views, dict(buttons or {})
        self.port, self.max_fps = port, max_fps
        self.settings = list(settings or [])
        self._settings_values = settings_values
        self.ask = ask
        if self.settings:
            self.buttons.setdefault("Save settings", "save")
        self._cond = threading.Condition()
        self._jpeg: dict[str, bytes] = {}
        self._last_publish: dict[str, float] = {}
        self._status: dict = {}
        self._status_time = 0.0
        self._commands: list[str] = []
        self._setting_changes: list[tuple[str, float]] = []
        self._questions: list[str] = []
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
        if os.name != "nt":     # on Linux the host name resolves to 127.0.1.1 only
            try:
                ips.update(subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split())
            except OSError:
                pass
        return [f"http://{ip}:{self.port}" for ip in sorted(ips)
                if "." in ip and not ip.startswith(("127.", "172.17."))]   # 172.17 = Docker

    def print_addresses(self):
        print("Dashboard: from a laptop or phone on the same Wi-Fi, open one of:")
        for url in self.addresses() or [f"http://<this-computer's-ip>:{self.port}"]:
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

    def pop_settings(self) -> list[tuple[str, float]]:
        with self._cond:
            changes, self._setting_changes = self._setting_changes, []
        return changes

    def pop_questions(self) -> list[str]:
        with self._cond:
            questions, self._questions = self._questions, []
        return questions

    def close(self):
        self._server.shutdown()
        self._server.server_close()

    def _page(self) -> bytes:
        buttons = "".join(f'<button onclick="cmd(\'{cmd}\')">{caption}</button>'
                          for caption, cmd in self.buttons.items())
        views = "".join(f'<section><h2>{caption}</h2><img src="/stream/{name}" data-src="/stream/{name}"></section>'
                        for name, caption in self.views.items())
        ask = ('<div class="panel ask"><input id="q" placeholder="Ask Navya (or leave empty: what do you see?)">'
               '<button onclick="ask()">Ask Navya</button></div>') if self.ask else ""
        tune = ('<div class="panel"><details><summary>Tune settings (live)</summary>'
                '<div id="sliders"></div></details></div>') if self.settings else ""
        html = (PAGE.replace("@TITLE@", self.title).replace("@BUTTONS@", buttons)
                .replace("@ASK@", ask).replace("@TUNE@", tune).replace("@VIEWS@", views))
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
                elif url.path == "/settings" and stream.settings:
                    meta = [dict(name=s.name, label=s.label, low=s.low, high=s.high, step=s.step)
                            for s in stream.settings]
                    body = dict(meta=meta, values=stream._settings_values() if stream._settings_values else {})
                    self._send(200, "application/json", json.dumps(body).encode())
                elif url.path == "/set" and stream.settings:
                    q = parse_qs(url.query)
                    name, value = q.get("k", [""])[0], q.get("v", [""])[0]
                    try:
                        if name in {s.name for s in stream.settings}:
                            with stream._cond:
                                stream._setting_changes.append((name, float(value)))
                    except ValueError:
                        pass
                    self._send(204, "text/plain")
                elif url.path == "/ask" and stream.ask:
                    question = parse_qs(url.query).get("q", [""])[0][:300]
                    with stream._cond:
                        stream._questions.append(question)
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
