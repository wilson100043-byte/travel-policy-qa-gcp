"""Check the architecture diagram for text overflow, then export its SVG as a 2x PNG.

Usage (needs Python Playwright with Chromium):
    python3 docs/diagrams/export_png.py
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHECK = """() => {
  const out = [];
  document.querySelectorAll('#diagram .node').forEach(g => {
    const r = g.querySelector('rect.box').getBBox();
    g.querySelectorAll(':scope > text').forEach(t => {
      const b = t.getBBox();
      if (b.x + b.width > r.x + r.width - 8 || b.y + b.height > r.y + r.height - 4) out.push(g.id + ': ' + t.textContent);
    });
  });
  const boxes = [...document.querySelectorAll('#diagram .node')].map(g => [g.id, g.querySelector('rect.box').getBBox()]);
  document.querySelectorAll('#diagram .elabel').forEach(l => {
    const b = l.getBBox(), name = l.querySelector('text').textContent;
    boxes.forEach(([id, r]) => {
      if (b.x < r.x + r.width && b.x + b.width > r.x && b.y < r.y + r.height && b.y + b.height > r.y) out.push('LABEL ' + name + ' overlaps ' + id);
    });
  });
  return out;
}"""

HERE = Path(__file__).resolve().parent
html = HERE / "cloud-architecture.html"
out = HERE / "cloud-architecture.png"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1700, "height": 1200}, device_scale_factor=2, color_scheme="light")
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(html.as_uri())
    page.evaluate("document.documentElement.dataset.theme = 'light'")
    page.wait_for_timeout(500)
    problems = page.evaluate(CHECK)
    print(json.dumps({"problems": problems, "errors": errors}, ensure_ascii=False))
    if problems or errors:
        sys.exit(1)
    page.locator("#diagram").screenshot(path=str(out))
    browser.close()
print("saved", out)
