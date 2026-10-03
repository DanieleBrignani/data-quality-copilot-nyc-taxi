"""Capture README screenshots of the running stack with headless Edge/Chrome via the DevTools protocol.

    docker compose up -d
    python scripts/screenshots.py            # writes docs/img/*.png

Plain `--screenshot` captures Streamlit before its websocket delivers the data, so this drives the
browser over CDP: navigate, wait for real content, optionally click a tab, then capture.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img"
PORT = 9333
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chromium", "google-chrome", "msedge"]

SHOTS = [
    # (file, url, text that must be on the page, tab to click or None, text expected after the click, viewport height)
    ("dashboard_overview.png", "http://127.0.0.1:8502", "Quality score & valid-record rate", None, None, 1300),
    ("dashboard_ml.png", "http://127.0.0.1:8502", "Quality score & valid-record rate", "ML model",
     "Rolling-origin backtest", 1900),
    ("dashboard_drift.png", "http://127.0.0.1:8502", "Quality score & valid-record rate", "Drift",
     "colour is never the only encoding", 1100),
    ("grafana.png", "http://127.0.0.1:3001/d/dq-copilot/data-quality-copilot-e28094-nyc-taxi?orgId=1&kiosk",
     "Quality score over time", None, None, 1450),
]


def browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("no Chromium-based browser found")


async def _ready(page: "Page") -> bool:
    return bool(await page.js("""(() => {
        const t = document.body ? document.body.innerText : "";
        if (location.port === "8502") {   // Streamlit: data rendered, no loading skeleton
            return t.includes("14,367,509")
                && !document.querySelector('[data-testid="stSkeleton"]');
        }
        return !t.includes("Cancel") && !t.includes("Loading") && !t.includes("Error loading");
    })()"""))


async def _wait_ready(self, timeout: float = 120) -> bool:
    t = time.time()
    while time.time() - t < timeout:
        if await _ready(self):
            return True
        await asyncio.sleep(1)
    return False


class Page:
    wait_ready = _wait_ready

    def __init__(self, ws):
        self.ws, self.i = ws, 0

    async def send(self, method: str, **params):
        self.i += 1
        await self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.i:
                return msg.get("result", {})

    async def js(self, expr: str):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def wait_text(self, text: str, timeout: float = 120):
        t = time.time()
        while time.time() - t < timeout:
            if await self.js(f"document.body && document.body.innerText.includes({json.dumps(text)})"):
                return
            await asyncio.sleep(1)
        raise TimeoutError(text)


async def capture(page: Page, name, url, must, tab, after, height):
    await page.send("Emulation.setDeviceMetricsOverride", width=1440, height=height, deviceScaleFactor=1, mobile=False)
    await page.send("Page.navigate", url=url)
    await page.wait_text(must)
    if tab:
        await page.js(f"""[...document.querySelectorAll('[role="tab"]')]
                          .find(b => b.innerText.trim() === {json.dumps(tab)}).click()""")
        await page.wait_text(after)
    if not await page.wait_ready():
        print(f"warning: {name} captured before every panel reported ready")
    await asyncio.sleep(4)   # let charts (Vega / Grafana panels) finish their transitions
    data = (await page.send("Page.captureScreenshot", format="png"))["data"]
    (OUT / name).write_bytes(base64.b64decode(data))
    print("wrote", OUT / name)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="dqc-shots-")
    proc = subprocess.Popen([browser(), "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                             f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json").read())
                break
            except OSError:
                time.sleep(0.5)
        target = next(t for t in targets if t["type"] == "page")
        async with websockets.connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            page = Page(ws)
            await page.send("Page.enable")
            for shot in SHOTS:
                await capture(page, *shot)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    asyncio.run(main())
