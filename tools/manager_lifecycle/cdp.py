"""Drive an Electron app's main window over the DevTools protocol.

Two transports, one interface (eval JS in the window, screenshot, trusted click):
- Page: the renderer target on --remote-debugging-port (WowUp).
- MainBridge: the main process on --inspect, reaching the window through Electron's
  webContents API. The CurseForge app lists no renderer targets on its debugging port, so
  this is the only way in without modifying the app.

CLI: python3 cdp.py page PORT eval 'expr' | shot OUT.png
     python3 cdp.py main PORT eval 'expr' | shot OUT.png | maineval 'expr'
"""

import base64
import itertools
import json
import sys
import urllib.request


def _targets(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        return json.load(r)


class _Conn:
    def __init__(self, url):
        from websockets.sync.client import connect

        self.ws = connect(url, max_size=64 * 1024 * 1024, open_timeout=10, ping_interval=None)
        self.ids = itertools.count(1)

    def send(self, method, **params):
        i = next(self.ids)
        self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            d = json.loads(self.ws.recv(timeout=180))
            if d.get("id") == i:
                if "error" in d:
                    raise RuntimeError(d["error"])
                return d["result"]

    def evaluate(self, expr, **extra):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True, **extra)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:2000])
        return r["result"].get("value")

    def close(self):
        self.ws.close()


class Page:
    def __init__(self, port):
        t = next(x for x in _targets(port) if x["type"] == "page" and not x["url"].startswith("devtools"))
        self.c = _Conn(t["webSocketDebuggerUrl"])

    def eval(self, expr):
        return self.c.evaluate(expr, userGesture=True)

    def shot(self, path):
        r = self.c.send("Page.captureScreenshot", format="png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(r["data"]))
        return path

    def click(self, x, y, button="left"):
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.c.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button=button, clickCount=1)

    def hover(self, x, y):
        self.c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)

    def type_text(self, text):
        self.c.send("Input.insertText", text=text)

    def key(self, key):
        code = {"Enter": 13, "Escape": 27}[key]
        for t in ("keyDown", "keyUp"):
            self.c.send("Input.dispatchKeyEvent", type=t, key=key, code=key, windowsVirtualKeyCode=code)

    def close(self):
        self.c.close()


class MainBridge:
    WIN = "require('electron').BrowserWindow.getAllWindows().filter(w=>w.isVisible())[0].webContents"

    def __init__(self, port):
        t = next(x for x in _targets(port) if x["type"] == "node")
        self.c = _Conn(t["webSocketDebuggerUrl"])

    def maineval(self, expr):
        return self.c.evaluate(expr, includeCommandLineAPI=True)

    def eval(self, expr):
        js = json.dumps(f"(async()=>JSON.stringify(await ({expr})))()")
        v = self.maineval(f"(async()=>{{const wc={self.WIN}; return await wc.executeJavaScript({js}, true)}})()")
        return None if v in (None, "undefined") else json.loads(v)

    def shot(self, path):
        b64 = self.maineval(f"(async()=>(await {self.WIN}.capturePage()).toPNG().toString('base64'))()")
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        return path

    def click(self, x, y, button="left"):
        self.maineval(
            f"(()=>{{const wc={self.WIN}; for (const type of ['mouseMove','mouseDown','mouseUp'])"
            f" wc.sendInputEvent({{type,x:{x},y:{y},button:'{button}',clickCount:1}}); return 1}})()"
        )

    def hover(self, x, y):
        self.maineval(f"({self.WIN}.sendInputEvent({{type:'mouseMove',x:{x},y:{y}}}), 1)")

    def type_text(self, text):
        self.maineval(f"({self.WIN}.insertText({json.dumps(text)}), 1)")

    def key(self, key):
        self.maineval(
            f"(()=>{{const wc={self.WIN}; wc.sendInputEvent({{type:'keyDown',keyCode:{json.dumps(key)}}});"
            f" wc.sendInputEvent({{type:'char',keyCode:{json.dumps(key)}}});"
            f" wc.sendInputEvent({{type:'keyUp',keyCode:{json.dumps(key)}}}); return 1}})()"
        )

    def close(self):
        self.c.close()


if __name__ == "__main__":
    kind, port, cmd, *rest = sys.argv[1:]
    d = (Page if kind == "page" else MainBridge)(port)
    try:
        if cmd == "shot":
            print(d.shot(rest[0]))
        elif cmd == "click":
            d.click(int(rest[0]), int(rest[1]))
        else:
            v = getattr(d, cmd)(rest[0])
            print(v if isinstance(v, str) else json.dumps(v, indent=1))
    finally:
        d.close()
