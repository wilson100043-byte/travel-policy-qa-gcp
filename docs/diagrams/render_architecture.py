"""Render the interview RAG architecture with official Google Cloud service icons.

The SVG and HTML are self-contained. The diagrams.net file keeps every card,
icon, and connector editable. Only Python's standard library is required;
Playwright is optional for PNG export.
"""

from __future__ import annotations

import base64
import html
import json
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET


HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1880, 1150
TITLE = "差旅報帳規定問答｜Google Cloud 架構"

# The five product icons are from https://cloud.google.com/icons (legacy SVG set).
OFFICIAL_ICONS = {
    name: (HERE / "icons" / f"{name}.svg").read_text(encoding="utf-8")
    for name in ("cloud_storage", "cloud_run", "cloud_build", "artifact_registry", "secret_manager")
}
CUSTOM_ICONS = {
    "repo": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g fill="none" stroke="#34445A" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 10h25l9 9v35H15z"/><path d="M40 10v10h9"/><circle cx="25" cy="30" r="3" fill="#34445A"/><circle cx="39" cy="36" r="3" fill="#34445A"/><circle cx="25" cy="45" r="3" fill="#34445A"/><path d="M25 33v12m0-9h14"/></g></svg>',
    "terraform": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path fill="#7B42BC" d="M7 11v16l14 8V19zm18 10v16l14 8V29zM43 11v34l14-8V19zM7 32v16l14 8V40z"/></svg>',
    "browser": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><g fill="none" stroke="#2D70D5" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="10" width="50" height="39" rx="5"/><path d="M7 20h50M25 56h14M32 49v7"/><circle cx="15" cy="15" r="1" fill="#2D70D5"/><circle cx="21" cy="15" r="1" fill="#2D70D5"/></g></svg>',
    "proxy": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path d="M32 6 54 15v17c0 13-9 22-22 27C19 54 10 45 10 32V15z" fill="#EAF2FF" stroke="#2D70D5" stroke-width="3"/><rect x="23" y="28" width="18" height="17" rx="3" fill="#2D70D5"/><path d="M27 28v-4a5 5 0 0 1 10 0v4" fill="none" stroke="#2D70D5" stroke-width="3"/><circle cx="32" cy="36" r="2" fill="#fff"/></svg>',
    "gemini": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#4285F4"/><stop offset=".55" stop-color="#9B65CF"/><stop offset="1" stop-color="#D55FA8"/></linearGradient></defs><path d="M32 4c4 15 13 24 28 28-15 4-24 13-28 28C28 45 19 36 4 32 19 28 28 19 32 4Z" fill="url(#g)"/></svg>',
}

COLORS = {
    "green": "#178A62", "blue": "#2D70D5", "violet": "#7750BF",
    "orange": "#C7792E", "optional": "#9B5FBF", "ink": "#19273A",
}

NODES = [
    # id, x, y, width, height, icon, title, description lines, color
    ("browser", 70, 260, 290, 104, "browser", "使用者瀏覽器", ["載入前端；暫存近期對話"], "blue"),
    ("proxy", 70, 405, 290, 104, "proxy", "IAP 登入閘道", ["Google 帳號登入後轉送"], "blue"),
    ("repo", 70, 620, 290, 104, "repo", "GitHub 儲存庫", ["程式碼 + 四份虛構規定"], "violet"),
    ("terraform", 70, 765, 290, 104, "terraform", "Terraform", ["建資源；上傳 raw/ 文件"], "violet"),
    ("service", 825, 280, 255, 140, "cloud_run", "Cloud Run\nservice", ["前端：HTML/CSS/JS", "API：FastAPI /api/ask"], "blue"),
    ("index", 1150, 284, 255, 124, "cloud_storage", "Cloud Storage", ["processed/ 索引 JSON", "章節、向量、生效日期"], "green"),
    ("raw", 500, 563, 255, 124, "cloud_storage", "Cloud Storage", ["raw/ 原始 Markdown", "四份虛構報帳規定"], "green"),
    ("job", 825, 563, 255, 124, "cloud_run", "Cloud Run Job", ["手動清理、切段", "建立文件向量索引"], "green"),
    ("build", 500, 850, 255, 124, "cloud_build", "Cloud Build", ["從 GitHub 程式碼", "手動建置容器映像"], "violet"),
    ("registry", 825, 850, 255, 124, "artifact_registry", "Artifact Registry", ["保存共用映像", "供 Service / Job 執行"], "violet"),
    ("secret", 1150, 850, 255, 124, "secret_manager", "Secret Manager", ["Gemini API key", "供 Service / Job 讀取"], "orange"),
    ("gemini", 1555, 500, 275, 204, "gemini", "Gemini\nDeveloper API", ["選用：Embedding", "追問改寫與答案生成", "本次未呼叫"], "optional"),
]
NODE_BY_ID = {node[0]: node for node in NODES}

# Paths are intentionally routed through open corridors, away from service cards.
EDGES = [
    ("browser-proxy", "M 203 364 L 203 405", "blue", False, "browser", "proxy", "開啟網址／提問"),
    ("proxy-browser", "M 286 405 L 286 364", "blue", False, "proxy", "browser", "前端／答案與來源"),
    ("proxy-service", "M 360 452 L 409 452 L 409 344 L 825 344", "blue", False, "proxy", "service", "GET / · POST /api/ask"),
    ("service-proxy", "M 825 393 L 440 393 L 440 476 L 360 476", "blue", False, "service", "proxy", "HTML/CSS/JS · 答案 JSON + 來源"),
    ("service-index", "M 1080 345 L 1150 345", "blue", False, "service", "index", "搜尋現行索引"),
    ("index-service", "M 1150 386 L 1080 386", "green", False, "index", "service", "回傳相關小節"),
    ("repo-terraform", "M 215 724 L 215 765", "violet", True, "repo", "terraform", ""),
    ("terraform-raw", "M 360 817 L 410 817 L 410 625 L 500 625", "violet", True, "terraform", "raw", "上傳文件"),
    ("raw-job", "M 755 625 L 825 625", "green", False, "raw", "job", "讀取"),
    ("job-index", "M 1080 625 L 1440 625 L 1440 438 L 1278 438 L 1278 408", "green", False, "job", "index", "寫入索引"),
    ("service-gemini", "M 1035 280 L 1035 263 L 1515 263 L 1515 550 L 1555 550", "optional", True, "service", "gemini", "改寫／問題向量／回答"),
    ("job-gemini", "M 1018 687 L 1018 713 L 1515 713 L 1515 625 L 1555 625", "optional", True, "job", "gemini", "文件 Embedding"),
    ("build-registry", "M 755 912 L 825 912", "violet", True, "build", "registry", "推送"),
    ("registry-job", "M 952 850 L 952 687", "violet", True, "registry", "job", "提供映像"),
    ("secret-job", "M 1150 912 L 1120 912 L 1120 737 L 1035 737 L 1035 687", "orange", True, "secret", "job", "注入 key"),
]


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def icon_data(name: str) -> str:
    source = OFFICIAL_ICONS.get(name, CUSTOM_ICONS.get(name))
    if source is None:
        raise KeyError(name)
    return "data:image/svg+xml;base64," + base64.b64encode(source.encode("utf-8")).decode("ascii")


def text(x: float, y: float, value: str, css: str = "", extra: str = "") -> str:
    return f'<text x="{x}" y="{y}" class="{css}" {extra}>{esc(value)}</text>'


def icon(x: int, y: int, name: str, size: int = 54) -> str:
    return f'<image x="{x}" y="{y}" width="{size}" height="{size}" href="{icon_data(name)}"/>'


def node_svg(node: tuple) -> str:
    node_id, x, y, w, h, icon_name, title, details, color_name = node
    color = COLORS[color_name]
    icon_y = y + (28 if h >= 140 else 31)
    title_y = y + (42 if h >= 140 else 41)
    detail_y = y + (104 if "\n" in title else (73 if h >= 140 else 72))
    lines = [
        f'<g id="node-{node_id}" class="node">',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#fff" stroke="#DAE3EC" stroke-width="1.5" filter="url(#card-shadow)"/>',
        f'<rect x="{x}" y="{y+16}" width="5" height="{h-32}" rx="2.5" fill="{color}"/>',
        f'<rect x="{x+18}" y="{y+23}" width="68" height="68" rx="15" fill="#F4F7FB"/>',
        icon(x + 26, icon_y, icon_name),
    ]
    for offset, title_line in enumerate(title.split("\n")):
        lines.append(text(x + 92, title_y + offset * 24, title_line, "node-title"))
    for offset, detail in enumerate(details):
        lines.append(text(x + 92, detail_y + offset * 25, detail, "node-detail"))
    lines.append('</g>')
    return "".join(lines)


def pill(x: int, y: int, label: str, color: str, width: int) -> str:
    return (
        f'<g><rect x="{x}" y="{y}" width="{width}" height="30" rx="15" fill="#fff" stroke="{color}" stroke-opacity=".35"/>'
        + text(x + width / 2, y + 21, label, "edge-label", f'text-anchor="middle" fill="{color}"') + '</g>'
    )


def make_svg() -> str:
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
           f'<title id="title">{esc(TITLE)}</title>',
           '<desc id="desc">Google Cloud 規劃圖。使用者瀏覽器經 IAP 以 Google 帳號登入後存取 Cloud Run 的前端與 FastAPI；API 搜尋索引，回答與來源沿原路回到瀏覽器。另有文件索引和建置流程；Gemini 為選用外部 API。</desc>',
           '''<defs>
             <filter id="card-shadow" x="-15%" y="-20%" width="135%" height="150%"><feDropShadow dx="0" dy="5" stdDeviation="7" flood-color="#1D375A" flood-opacity=".08"/></filter>
             <marker id="arrow-green" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1 11 6 1 11" fill="none" stroke="#178A62" stroke-width="2.2"/></marker>
             <marker id="arrow-blue" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1 11 6 1 11" fill="none" stroke="#2D70D5" stroke-width="2.2"/></marker>
             <marker id="arrow-violet" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1 11 6 1 11" fill="none" stroke="#7750BF" stroke-width="2.2"/></marker>
             <marker id="arrow-orange" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1 11 6 1 11" fill="none" stroke="#C7792E" stroke-width="2.2"/></marker>
             <marker id="arrow-optional" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto"><path d="M1 1 11 6 1 11" fill="none" stroke="#9B5FBF" stroke-width="2.2"/></marker>
           </defs>
           <style>
             text{font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans CJK TC","Microsoft JhengHei",sans-serif}
             .kicker{font-size:17px;font-weight:800;letter-spacing:.12em;fill:#2D70D5}
             .title{font-size:38px;font-weight:800;fill:#19273A}
             .subtitle{font-size:17px;fill:#62738A}
             .boundary-title{font-size:18px;font-weight:800;fill:#40536D}
             .lane-title{font-size:20px;font-weight:800;fill:#24384F}
             .lane-note{font-size:15px;font-weight:600;fill:#6B7C90}
             .node-title{font-size:18px;font-weight:800;fill:#19273A}
             .node-detail{font-size:15px;fill:#5F7084}
             .edge-label{font-size:14px;font-weight:750}
             .footer{font-size:15px;fill:#596C82}
             .flow{transition:opacity .2s ease}
           </style>''',
           f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#F7F9FC"/>',
           '<rect x="0" y="0" width="470" height="9" fill="#4285F4"/><rect x="470" y="0" width="470" height="9" fill="#EA4335"/><rect x="940" y="0" width="470" height="9" fill="#FBBC05"/><rect x="1410" y="0" width="470" height="9" fill="#34A853"/>',
           text(55, 57, "CLOUD SYSTEM DESIGN / RAG DEMO", "kicker"),
           text(55, 109, TITLE, "title"),
           text(55, 142, "虛構企業文件 · 私人 Cloud Run · 手動索引 · 本機版已完成", "subtitle"),
           '<rect x="1538" y="67" width="280" height="48" rx="24" fill="#FFF4E8" stroke="#EFCBA5"/>',
           text(1678, 98, "雲端規劃圖｜尚未部署", "boundary-title", 'text-anchor="middle" fill="#A56724"'),
           '<rect x="42" y="181" width="340" height="866" rx="23" fill="#FFFFFF" stroke="#DDE5EE" stroke-width="2"/>',
           '<rect x="430" y="181" width="1070" height="866" rx="23" fill="#FFFFFF" stroke="#8DB0E8" stroke-width="2" stroke-dasharray="10 7"/>',
           '<rect x="1530" y="465" width="315" height="302" rx="23" fill="#FFFFFF" stroke="#D8B8E8" stroke-width="2" stroke-dasharray="9 7"/>',
           '<rect x="455" y="221" width="1020" height="239" rx="18" fill="#F2F7FF" stroke="#DBE8FA"/>',
           '<rect x="455" y="506" width="1020" height="244" rx="18" fill="#F2FAF6" stroke="#D9EFE3"/>',
           '<rect x="455" y="796" width="1020" height="226" rx="18" fill="#F8F5FC" stroke="#ECE5F6"/>',
           text(66, 215, "使用者", "boundary-title"),
           '<line x1="66" y1="562" x2="358" y2="562" stroke="#DDE5EE"/>',
           text(66, 597, "文件維護與部署", "boundary-title"),
           text(455, 205, "GOOGLE CLOUD PROJECT  ·  us-central1", "boundary-title"),
           text(1552, 497, "外部 AI 服務｜選用", "boundary-title"),
           text(480, 257, "01  使用者提問與回答", "lane-title"),
           text(480, 445, "前端與 API 同在 Cloud Run；回答和來源回傳瀏覽器", "lane-note"),
           text(480, 542, "02  文件建立索引", "lane-title"),
           text(1107, 542, "raw/ + processed/：同一個私人 bucket", "lane-note"),
           text(480, 832, "03  建置與金鑰", "lane-title"),
           text(1194, 832, "由 Terraform 建立資源", "lane-note"),
           '<rect x="1549" y="715" width="277" height="34" rx="12" fill="#F7F1FB"/>',
           text(1688, 737, "Gemini 模式需明確啟用", "lane-note", 'text-anchor="middle" fill="#83519E"')]
    # Draw connections first so all arrowheads tuck under their destination cards.
    for edge_id, path, flow, dashed, _source, _target, _label in EDGES:
        color = COLORS[flow]
        dash = ' stroke-dasharray="9 7"' if dashed else ''
        out.append(f'<g id="edge-{edge_id}" class="flow flow-{flow}"><path d="{path}" fill="none" stroke="{color}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#arrow-{flow})"/></g>')
    # Labels are reserved for actions that cannot be read from the node names.
    for x, y, value, flow, width in [
        (500, 305, "GET / · POST /api/ask", "blue", 205),
        (505, 358, "回傳頁面／答案＋來源", "blue", 210),
        (1100, 413, "相關小節", "green", 99),
        (376, 665, "上傳文件", "violet", 92),
        (755, 581, "讀取", "green", 66),
        (1228, 582, "寫入索引", "green", 99),
        (1260, 230, "Gemini（選用）", "optional", 133),
        (1268, 671, "文件 Embedding", "optional", 151),
        (760, 882, "推送", "violet", 60),
        (958, 761, "提供映像", "violet", 97),
        (1112, 744, "注入 key", "orange", 88),
    ]:
        out.append(f'<g class="flow flow-{flow}">{pill(x, y, value, COLORS[flow], width)}</g>')
    for node in NODES:
        out.append(node_svg(node))
    out.extend([
        '<rect x="69" y="903" width="286" height="111" rx="17" fill="#F4F7FB" stroke="#DCE5EF"/>',
        text(92, 936, "這張圖如何解讀", "boundary-title"),
        text(92, 970, "實線：問答與資料路徑", "footer"),
        text(92, 997, "虛線：建置或選用服務", "footer"),
        '<rect x="1530" y="805" width="315" height="213" rx="18" fill="#FFFFFF" stroke="#E1E7EF"/>',
        text(1553, 840, "目前的驗證範圍", "boundary-title"),
        text(1553, 874, "本機：FastAPI + 文字向量", "footer"),
        text(1553, 902, "文件與索引：本機檔案", "footer"),
        text(1553, 930, "GCP、Gemini：未部署 / 呼叫", "footer"),
        text(1553, 972, "無付費雲端資源", "footer"),
        '<line x1="55" y1="1074" x2="1825" y2="1074" stroke="#D7E0E9"/>',
        text(55, 1112, "儲存：raw/ 與 processed/ 是同一個 Cloud Storage bucket 的兩個路徑。", "footer"),
        text(1120, 1112, "部署：bootstrap → 建映像 → app → 手動執行 Job。", "footer"),
        '</svg>'
    ])
    return "\n".join(out)


def cell(root: ET.Element, cell_id: str, value: str, style: str, x: int, y: int, w: int, h: int) -> None:
    node = ET.SubElement(root, "mxCell", {"id": cell_id, "value": value, "style": style, "vertex": "1", "parent": "1"})
    ET.SubElement(node, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})


def make_drawio() -> str:
    outer = ET.Element("mxfile", {"host": "app.diagrams.net", "type": "device"})
    diagram = ET.SubElement(outer, "diagram", {"id": "travel-rag-gcp-icons", "name": "RAG GCP 架構圖"})
    model = ET.SubElement(diagram, "mxGraphModel", {"dx": "1880", "dy": "1150", "grid": "1", "gridSize": "10", "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1", "pageScale": "1", "pageWidth": str(WIDTH), "pageHeight": str(HEIGHT), "math": "0", "shadow": "0"})
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    base = "rounded=1;arcSize=12;whiteSpace=wrap;html=1;strokeWidth=2;fontFamily=Arial;"
    cell(root, "heading", TITLE, "text;html=1;align=left;verticalAlign=middle;fontSize=34;fontStyle=1;fontColor=#19273A;", 55, 45, 1350, 70)
    cell(root, "status", "雲端規劃圖｜尚未部署", base + "fillColor=#FFF4E8;strokeColor=#EFCBA5;fontColor=#A56724;fontSize=18;fontStyle=1;", 1538, 67, 280, 48)
    for ident, value, x, y, w, h, fill, stroke in [
        ("external-zone", "使用者／文件維護者", 42, 181, 340, 866, "#FFFFFF", "#DDE5EE"),
        ("gcp-zone", "GOOGLE CLOUD PROJECT · us-central1", 430, 181, 1070, 866, "#FFFFFF", "#8DB0E8"),
        ("gemini-zone", "外部 AI 服務 · 選用", 1530, 465, 315, 302, "#FFFFFF", "#D8B8E8"),
        ("ask-lane", "01 使用者提問與回答 · 前端與 API 同在 Cloud Run", 455, 221, 1020, 239, "#F2F7FF", "#DBE8FA"),
        ("index-lane", "02 文件建立索引 · raw/ 與 processed/ 共用私人 bucket", 455, 506, 1020, 244, "#F2FAF6", "#D9EFE3"),
        ("build-lane", "03 建置與金鑰 · Terraform 建資源", 455, 796, 1020, 226, "#F8F5FC", "#ECE5F6"),
    ]:
        cell(root, ident, value, base + f"fillColor={fill};strokeColor={stroke};fontColor=#40536D;fontSize=18;fontStyle=1;align=left;verticalAlign=top;spacingLeft=20;spacingTop=14;", x, y, w, h)
    for node_id, x, y, w, h, icon_name, title, details, color_name in NODES:
        color = COLORS[color_name]
        cell(root, node_id, f'<b>{esc(title).replace(chr(10), "<br>")}</b><br>{"<br>".join(esc(line) for line in details)}', base + f"fillColor=#FFFFFF;strokeColor={color};fontColor=#19273A;fontSize=17;align=left;verticalAlign=middle;spacingLeft=92;spacingRight=10;", x, y, w, h)
        svg = OFFICIAL_ICONS.get(icon_name, CUSTOM_ICONS.get(icon_name))
        uri = "data:image/svg+xml," + quote(svg, safe="")
        cell(root, f"{node_id}-icon", "", f"shape=image;image={uri};aspect=fixed;html=1;", x + 27, y + 32, 53, 53)
    for edge_id, _path, flow, dashed, source, target, value in EDGES:
        color = COLORS[flow]
        style = ("edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
                 + f"strokeColor={color};strokeWidth=3;endArrow=block;endFill=1;fontColor={color};fontSize=14;labelBackgroundColor=#FFFFFF;"
                 + ("dashed=1;dashPattern=9 7;" if dashed else ""))
        edge = ET.SubElement(root, "mxCell", {"id": edge_id, "value": value, "style": style, "edge": "1", "parent": "1", "source": source, "target": target})
        ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
    cell(root, "footer", "同一 Cloud Storage bucket：raw/ 放虛構規定文件，processed/ 放索引。Gemini 為選用；本次只驗證本機模式，沒有建立雲端資源。", "text;html=1;align=left;verticalAlign=middle;fontSize=16;fontColor=#596C82;", 55, 1080, 1760, 50)
    ET.indent(outer, space="  ")
    return ET.tostring(outer, encoding="unicode", xml_declaration=True)


def make_semantic_spec() -> dict:
    """Keep a small machine-readable component map beside the visual source."""
    types = {
        "repo": "external", "terraform": "external", "browser": "frontend",
        "proxy": "security", "raw": "database", "job": "backend",
        "index": "database", "service": "backend", "build": "cloud",
        "registry": "cloud", "secret": "security", "gemini": "external",
    }
    components = [
        {"id": node_id, "type": types[node_id], "label": title.replace("\n", " "),
         "sublabel": "；".join(details), "pos": [x, y], "size": [w, h]}
        for node_id, x, y, w, h, _icon, title, details, _color in NODES
    ]
    connections = []
    for edge_id, _path, _flow, dashed, source, target, label in EDGES:
        connection = {"id": edge_id.replace("-", "_"), "from": source, "to": target}
        if label:
            connection["label"] = label
        if dashed:
            connection["variant"] = "dashed"
        connections.append(connection)
    return {
        "schema_version": 1,
        "diagram_type": "architecture",
        "meta": {"title": TITLE, "quality_profile": "showcase", "viewBox": [WIDTH, HEIGHT]},
        "components": components,
        "boundaries": [{"kind": "region", "label": "Google Cloud · us-central1",
                        "wraps": ["raw", "job", "index", "service", "build", "registry", "secret"], "pad": 25}],
        "connections": connections,
    }


def make_html(svg: str) -> str:
    return f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(TITLE)}</title>
<style>body{{margin:0;background:#EAF0F6;color:#19273A;font-family:-apple-system,BlinkMacSystemFont,"PingFang TC",sans-serif}}.wrap{{max-width:1880px;margin:0 auto;padding:18px}}.toolbar{{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}}button{{font:inherit;border:1px solid #CAD6E4;background:#fff;border-radius:9px;padding:8px 13px;color:#40536D;cursor:pointer}}button.active{{background:#2D70D5;color:#fff;border-color:#2D70D5}}.hint{{color:#5F7084;font-size:14px;margin-left:8px}}.diagram{{background:#fff;border-radius:12px;box-shadow:0 14px 38px #1D375A16;overflow:auto}}svg{{display:block;width:min(100%,calc((100vh - 126px)*1.6348));height:auto;margin:auto}}.filtered .flow{{opacity:.12}}.filtered .flow.selected{{opacity:1}}.note{{padding:9px 4px;color:#53667C;font-size:14px;line-height:1.5;margin:0}}@media(max-width:700px){{.wrap{{padding:10px}}.hint{{width:100%}}svg{{min-width:1040px;width:1040px}}}}</style></head>
<body><main class="wrap"><nav class="toolbar" aria-label="突出顯示流程"><button class="active" data-flow="all">全部</button><button data-flow="green">文件索引</button><button data-flow="blue">問答</button><button data-flow="violet">建置</button><button data-flow="orange">金鑰</button><button data-flow="optional">Gemini 選用</button><span class="hint">點選流程可突出顯示連線；圖示採 Google Cloud 官方服務圖示。</span></nav><section class="diagram" aria-label="Google Cloud 架構圖">{svg}</section><p class="note">此圖是可審查的雲端設計，尚未部署。實際本機模式直接讀取專案內 Markdown 與 JSON 索引，不使用 GCP 或 Gemini。</p></main>
<script>const panel=document.querySelector('.diagram');document.querySelectorAll('[data-flow]').forEach(b=>b.addEventListener('click',()=>{{const flow=b.dataset.flow;document.querySelectorAll('[data-flow]').forEach(x=>x.classList.toggle('active',x===b));panel.classList.toggle('filtered',flow!=='all');panel.querySelectorAll('.flow').forEach(x=>x.classList.toggle('selected',x.classList.contains('flow-'+flow)));}}));</script></body></html>'''


def main() -> None:
    svg = make_svg()
    svg_path = HERE / "cloud-architecture.svg"
    html_path = HERE / "cloud-architecture.html"
    drawio_path = HERE / "cloud-architecture.drawio"
    spec_path = HERE / "cloud-architecture.archify.json"
    svg_path.write_text(svg, encoding="utf-8")
    html_path.write_text(make_html(svg), encoding="utf-8")
    drawio_path.write_text(make_drawio(), encoding="utf-8")
    spec_path.write_text(json.dumps(make_semantic_spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ET.fromstring(svg)
    ET.parse(drawio_path)
    print("Wrote SVG, HTML, diagrams.net source")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("PNG skipped: Python Playwright is unavailable")
    else:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": WIDTH + 20, "height": HEIGHT + 20}, device_scale_factor=1)
            page.goto(svg_path.as_uri(), wait_until="load")
            page.locator("svg").screenshot(path=str(HERE / "cloud-architecture.png"))
            browser.close()
        print("Wrote PNG")


if __name__ == "__main__":
    main()
