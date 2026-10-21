"""Icon and banner of Odoo modules for the Odoo Apps Store, in the Kalamiri style.

Draws static/description/icon.png (256x256) and banner.png (560x280) of each module listed in
modules.json from the HTML templates next to this script, with headless Microsoft Edge.

    python render.py [module ...]        (all modules of modules.json without arguments)

Needs Microsoft Edge and the Python package websocket-client.
"""
import base64
import html
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

HERE = Path(__file__).resolve().parent
ADDONS = HERE.parent.parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9341


class Browser:
    def __init__(self):
        self.process = subprocess.Popen([
            EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
            "--remote-allow-origins=*", f"--user-data-dir={tempfile.mkdtemp()}", "about:blank",
        ])
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                page = next(target for target in targets if target["type"] == "page")
                break
            except Exception:
                time.sleep(0.3)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.counter = 0

    def call(self, method, **params):
        self.counter += 1
        self.ws.send(json.dumps({"id": self.counter, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.counter:
                return message.get("result", {})

    def screenshot(self, page_html, width, height, out):
        path = Path(tempfile.mkdtemp()) / "page.html"
        path.write_text(page_html, encoding="utf-8")
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
        self.call("Emulation.setDefaultBackgroundColorOverride", color={"r": 0, "g": 0, "b": 0, "a": 0})
        self.call("Page.navigate", url=path.as_uri())
        time.sleep(1)
        data = self.call("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": width, "height": height, "scale": 1})
        out.write_bytes(base64.b64decode(data["data"]))

    def close(self):
        self.process.terminate()


def fill(template, values):
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def main():
    modules = json.loads((HERE / "modules.json").read_text(encoding="utf-8"))
    names = sys.argv[1:] or list(modules)
    browser = Browser()
    try:
        for name in names:
            spec = modules[name]
            glyph = (HERE / "glyphs" / f"{spec['glyph']}.svg").read_text(encoding="utf-8")
            values = {
                "glyph": glyph,
                "accent": spec["accent"],
                "title": html.escape(spec["title"]),
                "subtitle": html.escape(spec["subtitle"]),
                "points": "".join(f"<li>{html.escape(point)}</li>" for point in spec["points"]),
            }
            target = ADDONS / name / "static" / "description"
            target.mkdir(parents=True, exist_ok=True)
            browser.screenshot(fill((HERE / "icon.html").read_text(encoding="utf-8"), values), 256, 256, target / "icon.png")
            browser.screenshot(fill((HERE / "banner.html").read_text(encoding="utf-8"), values), 560, 280, target / "banner.png")
            print(name, "->", target)
    finally:
        browser.close()


if __name__ == "__main__":
    main()
