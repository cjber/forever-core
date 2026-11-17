"""UI helpers shared by both app drivers: find by visible text, trusted click, wait."""

import json
import time

FIND_JS = """
((text, sel, within) => {
  const root = within ? [...document.querySelectorAll(within)].pop() : document;
  if (!root) return null;
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const norm = s => (s || '').replace(/\\s+/g, ' ').trim();
  const els = [...root.querySelectorAll(sel)].filter(e => vis(e) && norm(e.innerText) === text);
  if (!els.length) return null;
  // innermost match
  const e = els.find(x => !els.some(y => y !== x && x.contains(y))) || els[0];
  const r = e.getBoundingClientRect();
  return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
})(%s, %s, %s)
"""


def find(d, text, sel="button, a, [role=menuitem], [role=tab], li, span, div, p", within=None):
    return d.eval(FIND_JS % (json.dumps(text), json.dumps(sel), json.dumps(within)))


def click_text(d, text, timeout=30, **kw):
    end = time.time() + timeout
    while time.time() < end:
        p = find(d, text, **kw)
        if p:
            d.click(p["x"], p["y"])
            return p
        time.sleep(0.5)
    raise TimeoutError(f"no visible element with text {text!r}")


def wait_for(d, js, timeout=60, what=None):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = d.eval(js)
            if last:
                return last
        except RuntimeError as e:
            last = str(e)
        time.sleep(1)
    raise TimeoutError(f"timed out waiting for {what or js!r} (last={last!r})")


def text_present(d, text):
    return bool(d.eval(f"document.body.innerText.includes({json.dumps(text)})"))


def body_text(d, n=4000):
    return d.eval(f"document.body.innerText.slice(0,{n})")
