"""Screenshots of an Odoo instance for the Odoo Apps Store description of a module.

    python screenshots.py <spec.json>

spec.json: {"url": "https://odoo.example.com", "login": "...", "password_file": "...", "width": 1280,
            "shots": [{"module": "l10n_hr_price_list", "file": "screenshot_premises.png", "path": "/odoo/...",
                       "script": "optional JavaScript run before the shot", "height": 800}]}
Each shot is saved in <module>/static/description/. Needs Microsoft Edge and websocket-client.
"""
import base64
import json
import sys
import time
from pathlib import Path

from render import ADDONS, Browser


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    password = Path(spec["password_file"]).read_text(encoding="utf-8").strip()
    browser = Browser()
    try:
        browser.call("Page.enable")
        browser.call("Emulation.setDeviceMetricsOverride", width=spec.get("width", 1280), height=800, deviceScaleFactor=1, mobile=False)
        browser.call("Page.navigate", url=spec["url"] + "/web/login")
        time.sleep(3)
        browser.call("Runtime.evaluate", expression=(
            f"document.querySelector('#login').value = {json.dumps(spec['login'])};"
            f"document.querySelector('#password').value = {json.dumps(password)};"
            "document.querySelector('form.oe_login_form').submit();"
        ))
        time.sleep(5)
        for shot in spec["shots"]:
            width, height = spec.get("width", 1280), shot.get("height", 800)
            browser.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
            browser.call("Page.navigate", url=spec["url"] + shot["path"])
            time.sleep(shot.get("wait", 5))
            if shot.get("script"):
                browser.call("Runtime.evaluate", expression=shot["script"])
                time.sleep(1.5)
            out = ADDONS / shot["module"] / "static" / "description" / shot["file"]
            data = browser.call("Page.captureScreenshot", format="png", clip={"x": 0, "y": 0, "width": width, "height": height, "scale": 1})
            out.write_bytes(base64.b64decode(data["data"]))
            print(out)
    finally:
        browser.close()


if __name__ == "__main__":
    main()
