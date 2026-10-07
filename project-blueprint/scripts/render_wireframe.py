#!/usr/bin/env python3
"""Render a wireframe spec (JSON) to low-fidelity grayscale SVG, one file per screen.

Usage: render_wireframe.py spec.json --out <dir> [--theme light|dark] [--html]

Standard library only, no network, no external assets. Output is deterministic:
the same spec always produces byte-identical output (no timestamps, no random ids).
Validation is hand-written and reports the JSON path of every problem, e.g.
"screens[1].elements[2]: input requires 'label'".

Elements are laid out in a vertical stack; "row" lays its children out
horizontally and "column" vertically (nesting up to 3 levels). Besides the
<screen-id>.svg files the script always writes screen-flow.md (a Mermaid
flowchart built from every screen's navigates_to). With --html it also writes
index.html, a gallery that inlines every screen in both light and dark SVG
variants and switches between them with prefers-color-scheme.
"""

import argparse
import json
import os
import re
import sys
import textwrap
from xml.sax.saxutils import escape

PAD = 16
GAP = 12
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
DEFAULT_PRESETS = {"mobile": (390, 844), "desktop": (1280, 800)}
DEFAULT_VIEWPORT = "mobile"
SCREEN_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(--[a-z0-9]+(-[a-z0-9]+)*)?$")
INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")

THEMES = {
    "light": {"bg": "#ffffff", "fg": "#222222", "muted": "#8a8a8a", "line": "#b5b5b5",
              "fill": "#f1f1f1", "solid": "#333333", "on_solid": "#ffffff"},
    "dark": {"bg": "#1e1e1e", "fg": "#eeeeee", "muted": "#9a9a9a", "line": "#5a5a5a",
             "fill": "#2b2b2b", "solid": "#dddddd", "on_solid": "#111111"},
}

# element type -> required fields. Fields listed in LIST_FIELDS must be lists.
REQUIRED = {
    "header": ["text"], "text": ["text"], "image": [], "input": ["label"],
    "textarea": ["label"], "select": ["label"], "checkbox": ["label"], "radio": ["label"],
    "toggle": ["label"], "button": ["text"], "link": ["text"], "list": ["items"],
    "card": ["title"], "table": ["columns"], "tabs": ["items"], "nav": ["items"],
    "modal": ["title"], "divider": [], "spacer": [], "row": ["children"], "column": ["children"],
}
LIST_FIELDS = {"items", "columns", "children"}
MAX_NESTING = 3  # row/column levels
MERMAID_RESERVED = {"end", "graph", "flowchart", "subgraph", "style", "class", "click", "default"}


# ---------------------------------------------------------------- validation

def validate_elements(elements, path, errors, depth=0):
    if not isinstance(elements, list):
        errors.append(f"{path}: must be a list of elements")
        return
    for i, el in enumerate(elements):
        p = f"{path}[{i}]"
        if not isinstance(el, dict):
            errors.append(f"{p}: element must be an object")
            continue
        etype = el.get("type")
        if etype is None:
            errors.append(f"{p}: element requires 'type'")
            continue
        if etype not in REQUIRED:
            errors.append(f"{p}: unknown element type '{etype}'")
            continue
        for field in REQUIRED[etype]:
            if field not in el:
                errors.append(f"{p}: {etype} requires '{field}'")
            elif field in LIST_FIELDS:
                if not isinstance(el[field], list):
                    errors.append(f"{p}.{field}: must be a list")
                elif field != "children" and not el[field]:
                    errors.append(f"{p}.{field}: must not be empty")
            elif not isinstance(el[field], str) or not el[field].strip():
                errors.append(f"{p}.{field}: must be a non-empty string")
        if etype == "spacer" and "height" in el:
            h = el["height"]
            if not isinstance(h, int) or isinstance(h, bool) or h < 1:
                errors.append(f"{p}.height: must be a positive integer")
        if etype in ("tabs", "nav") and "active" in el:
            a = el["active"]
            if not isinstance(a, int) or isinstance(a, bool) or a < 0:
                errors.append(f"{p}.active: must be a non-negative integer")
        if etype in ("row", "column") and isinstance(el.get("children"), list):
            if depth + 1 > MAX_NESTING:
                errors.append(f"{p}: {etype} nesting is deeper than {MAX_NESTING} levels")
            else:
                validate_elements(el["children"], f"{p}.children", errors, depth + 1)


def presets_for(spec):
    presets = dict(DEFAULT_PRESETS)
    custom = spec.get("viewport_presets")
    if isinstance(custom, dict):
        for name, size in custom.items():
            if (isinstance(size, list) and len(size) == 2
                    and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in size)):
                presets[name] = tuple(size)
    return presets


def validate_spec(spec):
    errors = []
    if not isinstance(spec, dict):
        return ["(root): spec must be a JSON object"]
    if not isinstance(spec.get("project"), str) or not spec["project"].strip():
        errors.append("project: required non-empty string")
    custom = spec.get("viewport_presets")
    if custom is not None:
        if not isinstance(custom, dict):
            errors.append("viewport_presets: must be an object")
        else:
            for name, size in custom.items():
                if not (isinstance(size, list) and len(size) == 2
                        and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in size)):
                    errors.append(f"viewport_presets.{name}: must be [width, height] positive integers")
    screens = spec.get("screens")
    if not isinstance(screens, list) or not screens:
        errors.append("screens: required non-empty list")
        return errors
    presets = presets_for(spec)
    ids = [s.get("id") for s in screens if isinstance(s, dict) and isinstance(s.get("id"), str)]
    seen = set()
    for i, screen in enumerate(screens):
        p = f"screens[{i}]"
        if not isinstance(screen, dict):
            errors.append(f"{p}: screen must be an object")
            continue
        sid = screen.get("id")
        if not isinstance(sid, str) or not SCREEN_ID_RE.match(sid):
            errors.append(f"{p}.id: must be lowercase-kebab (e.g. 'login' or 'login--empty')")
        elif sid in seen:
            errors.append(f"{p}.id: duplicate screen id '{sid}'")
        else:
            seen.add(sid)
        if not isinstance(screen.get("name"), str) or not screen["name"].strip():
            errors.append(f"{p}.name: required non-empty string")
        viewport = screen.get("viewport", DEFAULT_VIEWPORT)
        if isinstance(viewport, str):
            if viewport not in presets:
                errors.append(f"{p}.viewport: unknown preset '{viewport}'")
        else:
            errors.append(f"{p}.viewport: must be a preset name")
        if "elements" not in screen:
            errors.append(f"{p}: screen requires 'elements'")
        else:
            validate_elements(screen["elements"], f"{p}.elements", errors)
        nav = screen.get("navigates_to", [])
        if not isinstance(nav, list):
            errors.append(f"{p}.navigates_to: must be a list")
            continue
        for j, link in enumerate(nav):
            lp = f"{p}.navigates_to[{j}]"
            if not isinstance(link, dict):
                errors.append(f"{lp}: must be an object")
                continue
            if not isinstance(link.get("element"), str) or not link["element"].strip():
                errors.append(f"{lp}: requires 'element'")
            target = link.get("screen")
            if not isinstance(target, str):
                errors.append(f"{lp}: requires 'screen'")
            elif target not in ids:
                errors.append(f"{lp}: unknown screen '{target}'")
    return errors


# ----------------------------------------------------------------- rendering

def esc(value):
    """Escape text for XML, dropping characters XML cannot represent."""
    value = INVALID_XML_CHARS_RE.sub("", str(value))
    return escape(value, {'"': "&quot;", "'": "&apos;"})


def clip(text, max_chars):
    text = str(text)
    return text if len(text) <= max_chars else text[:max(1, max_chars - 1)] + "…"


def chars_that_fit(width, size):
    return max(1, int(width / (size * 0.56)))


class Canvas:
    def __init__(self, theme):
        self.t = THEMES[theme]
        self.parts = []

    def rect(self, x, y, w, h, fill="none", stroke=None, rx=6, dash=False):
        stroke = stroke or self.t["line"]
        dash_attr = ' stroke-dasharray="6 4"' if dash else ""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"{dash_attr}/>')

    def line(self, x1, y1, x2, y2, stroke=None, width=1):
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{stroke or self.t["line"]}" stroke-width="{width}"/>')

    def circle(self, cx, cy, r, fill="none", stroke=None):
        self.parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
            f'stroke="{stroke or self.t["line"]}" stroke-width="1"/>')

    def polyline(self, points, stroke=None, width=2):
        pts = " ".join(f"{px},{py}" for px, py in points)
        self.parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{stroke or self.t["fg"]}" '
            f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>')

    def text(self, x, baseline, value, size, fill=None, weight=None, anchor="start", underline=False):
        extra = ""
        if weight:
            extra += f' font-weight="{weight}"'
        if anchor != "start":
            extra += f' text-anchor="{anchor}"'
        if underline:
            extra += ' text-decoration="underline"'
        self.parts.append(
            f'<text x="{x}" y="{baseline}" font-size="{size}" fill="{fill or self.t["fg"]}"{extra}>'
            f'{esc(value)}</text>')


def draw_element(cv, el, x, y, w):
    """Draw one element with its top-left corner at (x, y); return its height."""
    t = cv.t
    etype = el["type"]
    if etype == "header":
        cv.text(x, y + 24, clip(el["text"], chars_that_fit(w, 22)), 22, weight="bold")
        return 36
    if etype == "text":
        lines = textwrap.wrap(el["text"], width=chars_that_fit(w, 14)) or [""]
        for n, line in enumerate(lines):
            cv.text(x, y + 14 + n * 20, line, 14)
        return 20 * len(lines)
    if etype == "input":
        cv.text(x, y + 12, clip(el["label"], chars_that_fit(w, 12)), 12, fill=t["muted"])
        cv.rect(x, y + 20, w, 40, fill=t["fill"])
        if el.get("secret"):
            hint = "•" * 8
        else:
            hint = clip(el.get("placeholder", ""), chars_that_fit(w - 24, 14))
        if hint:
            cv.text(x + 12, y + 45, hint, 14, fill=t["muted"])
        return 60
    if etype == "button":
        primary = bool(el.get("primary"))
        cv.rect(x, y, w, 44, fill=t["solid"] if primary else "none",
                stroke=t["solid"] if primary else t["line"])
        cv.text(x + w // 2, y + 28, clip(el["text"], chars_that_fit(w - 24, 15)), 15,
                fill=t["on_solid"] if primary else t["fg"], weight="bold", anchor="middle")
        return 44
    if etype == "link":
        cv.text(x, y + 16, clip(el["text"], chars_that_fit(w, 14)), 14, underline=True)
        return 22
    if etype == "divider":
        cv.line(x, y, x + w, y)
        return 1
    if etype == "spacer":
        return int(el.get("height", 16))
    if etype == "image":
        h = 160
        cv.rect(x, y, w, h, fill=t["fill"])
        cv.line(x, y, x + w, y + h)
        cv.line(x, y + h, x + w, y)
        alt = el.get("alt")
        if alt:
            label = clip(alt, chars_that_fit(w - 24, 13))
            tw = int(len(label) * 13 * 0.56) + 16
            cv.rect(x + w // 2 - tw // 2, y + h // 2 - 12, tw, 24, fill=t["bg"], stroke=t["bg"], rx=4)
            cv.text(x + w // 2, y + h // 2 + 5, label, 13, fill=t["muted"], anchor="middle")
        if el.get("caption"):
            cv.text(x, y + h + 14, clip(el["caption"], chars_that_fit(w, 12)), 12, fill=t["muted"])
            h += 20
        return h
    if etype == "textarea":
        cv.text(x, y + 12, clip(el["label"], chars_that_fit(w, 12)), 12, fill=t["muted"])
        cv.rect(x, y + 20, w, 96, fill=t["fill"])
        hint = clip(el.get("placeholder", ""), chars_that_fit(w - 24, 14))
        if hint:
            cv.text(x + 12, y + 45, hint, 14, fill=t["muted"])
        return 116
    if etype == "select":
        cv.text(x, y + 12, clip(el["label"], chars_that_fit(w, 12)), 12, fill=t["muted"])
        cv.rect(x, y + 20, w, 40, fill=t["fill"])
        options = el.get("options") or []
        if options:
            cv.text(x + 12, y + 45, clip(options[0], chars_that_fit(w - 56, 14)), 14)
        cv.polyline([(x + w - 26, y + 37), (x + w - 20, y + 43), (x + w - 14, y + 37)])
        return 60
    if etype == "checkbox":
        cv.rect(x, y + 3, 18, 18, rx=3)
        if el.get("checked"):
            cv.polyline([(x + 4, y + 12), (x + 8, y + 16), (x + 15, y + 7)])
        cv.text(x + 28, y + 17, clip(el["label"], chars_that_fit(w - 28, 14)), 14)
        return 24
    if etype == "radio":
        options = el.get("options") or []
        if not options:
            cv.circle(x + 9, y + 12, 9)
            cv.text(x + 28, y + 17, clip(el["label"], chars_that_fit(w - 28, 14)), 14)
            return 24
        cv.text(x, y + 12, clip(el["label"], chars_that_fit(w, 12)), 12, fill=t["muted"])
        for n, option in enumerate(options):
            ry = y + 20 + n * 24
            cv.circle(x + 9, ry + 12, 9)
            cv.text(x + 28, ry + 17, clip(option, chars_that_fit(w - 28, 14)), 14)
        return 20 + 24 * len(options)
    if etype == "toggle":
        on = bool(el.get("on"))
        cv.text(x, y + 19, clip(el["label"], chars_that_fit(w - 56, 14)), 14)
        cv.rect(x + w - 44, y + 3, 44, 24, fill=t["solid"] if on else t["fill"], rx=12,
                stroke=t["solid"] if on else t["line"])
        cv.circle(x + w - 12 if on else x + w - 32, y + 15, 9,
                  fill=t["on_solid"] if on else t["bg"])
        return 30
    if etype == "list":
        items = el["items"]
        cv.rect(x, y, w, 36 * len(items))
        for n, item in enumerate(items):
            ry = y + n * 36
            if n:
                cv.line(x, ry, x + w, ry)
            cv.circle(x + 16, ry + 18, 3, fill=t["fg"], stroke=t["fg"])
            cv.text(x + 30, ry + 23, clip(item, chars_that_fit(w - 44, 14)), 14)
        return 36 * len(items)
    if etype == "card":
        lines = textwrap.wrap(el.get("text", ""), width=chars_that_fit(w - 32, 13))
        h = 36 + 18 * len(lines) + 16 if lines else 52
        cv.rect(x, y, w, h, fill=t["fill"])
        cv.text(x + 16, y + 28, clip(el["title"], chars_that_fit(w - 32, 16)), 16, weight="bold")
        for n, line in enumerate(lines):
            cv.text(x + 16, y + 52 + n * 18, line, 13, fill=t["muted"])
        return h
    if etype == "table":
        columns = el["columns"]
        rows = [r if isinstance(r, list) else [r] for r in el.get("rows") or [[], []]]
        cw = w // len(columns)
        h = 32 * (1 + len(rows))
        cv.rect(x, y, w, h)
        cv.rect(x, y, w, 32, fill=t["fill"])
        for i in range(1, len(columns)):
            cv.line(x + i * cw, y, x + i * cw, y + h)
        for n in range(1, len(rows) + 1):
            cv.line(x, y + n * 32, x + w, y + n * 32)
        fit = chars_that_fit(cw - 16, 13)
        for i, name in enumerate(columns):
            cv.text(x + i * cw + 8, y + 21, clip(name, fit), 13, weight="bold")
        for n, row in enumerate(rows):
            for i, cell in enumerate(row[:len(columns)]):
                cv.text(x + i * cw + 8, y + 32 * (n + 1) + 21, clip(cell, fit), 13)
        return h
    if etype == "tabs":
        items = el["items"]
        active = min(el.get("active", 0), len(items) - 1)
        tw = w // len(items)
        cv.line(x, y + 40, x + w, y + 40)
        for i, name in enumerate(items):
            on = i == active
            cv.text(x + i * tw + tw // 2, y + 25, clip(name, chars_that_fit(tw - 8, 14)), 14,
                    fill=t["fg"] if on else t["muted"], weight="bold" if on else None, anchor="middle")
            if on:
                cv.line(x + i * tw, y + 40, x + (i + 1) * tw, y + 40, stroke=t["fg"], width=3)
        return 41
    if etype == "nav":
        items = el["items"]
        active = min(el.get("active", 0), len(items) - 1)
        tw = w // len(items)
        cv.rect(x, y, w, 52, fill=t["fill"])
        for i, name in enumerate(items):
            on = i == active
            cv.text(x + i * tw + tw // 2, y + 31, clip(name, chars_that_fit(tw - 8, 13)), 13,
                    fill=t["fg"] if on else t["muted"], weight="bold" if on else None, anchor="middle")
        return 52
    if etype == "modal":
        lines = textwrap.wrap(el.get("text", ""), width=chars_that_fit(w - 32, 13))
        actions = el.get("actions") or []
        content_y = 48 + (18 * len(lines) + 8 if lines else 0)
        h = content_y + 36 + 16 if actions else content_y + 8
        cv.rect(x, y, w, h, fill=t["bg"], stroke=t["solid"], rx=10)
        cv.text(x + 16, y + 32, clip(el["title"], chars_that_fit(w - 32, 16)), 16, weight="bold")
        for n, line in enumerate(lines):
            cv.text(x + 16, y + 56 + n * 18, line, 13, fill=t["muted"])
        if actions:
            bw = min(110, (w - 32 - 8 * (len(actions) - 1)) // len(actions))
            bx = x + w - 16 - bw
            for n, name in enumerate(reversed(actions)):
                primary = n == 0
                cv.rect(bx, y + content_y, bw, 36, fill=t["solid"] if primary else "none",
                        stroke=t["solid"] if primary else t["line"])
                cv.text(bx + bw // 2, y + content_y + 23, clip(name, chars_that_fit(bw - 8, 13)), 13,
                        fill=t["on_solid"] if primary else t["fg"], weight="bold", anchor="middle")
                bx -= bw + 8
        return h
    if etype == "row" and el["children"]:
        n = len(el["children"])
        cw = (w - 8 * (n - 1)) // n
        return max(draw_element(cv, child, x + i * (cw + 8), y, cw)
                   for i, child in enumerate(el["children"]))
    if etype == "column" and el["children"]:
        cy = y
        for child in el["children"]:
            cy += draw_element(cv, child, x, cy, w) + 8
        return cy - y - 8
    cv.rect(x, y, w, 40, fill=t["fill"], dash=True)
    cv.text(x + w // 2, y + 25, f"[{etype}]", 14, fill=t["muted"], anchor="middle")
    return 40


def render_screen(spec, screen, theme):
    presets = presets_for(spec)
    vw, vh = presets[screen.get("viewport", DEFAULT_VIEWPORT)]
    cv = Canvas(theme)
    inner_w = vw - 2 * PAD
    y = PAD
    for el in screen["elements"]:
        y += draw_element(cv, el, PAD, y, inner_w) + GAP
    height = max(vh, y - GAP + PAD)
    t = THEMES[theme]
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{vw}" height="{height}" '
        f'viewBox="0 0 {vw} {height}" font-family="{FONT}" role="img" aria-label="{esc(screen["name"])}">\n'
        f'<title>{esc(screen["name"])}</title>\n'
        f'<rect x="0" y="0" width="{vw}" height="{height}" fill="{t["bg"]}"/>\n'
    )
    return head + "\n".join(cv.parts) + "\n</svg>\n"


# ------------------------------------------------------- screen flow + gallery

def mermaid_node_id(screen_id):
    """Mermaid-safe node id that stays recognizable as the screen id."""
    node = screen_id.replace("--", "__")
    return node + "_screen" if node.lower() in MERMAID_RESERVED else node


def mermaid_label(text):
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = text.replace("#", "#35;").replace('"', "#quot;")
    return text.replace("<", "#lt;").replace(">", "#gt;")


def build_screen_flow(spec):
    """Return (markdown, warnings) for the screen-flow Mermaid diagram."""
    screens = spec["screens"]
    lines = ["flowchart TD"]
    for s in screens:
        lines.append(f'    {mermaid_node_id(s["id"])}["{mermaid_label(s["name"])}"]')
    incoming = set()
    for s in screens:
        for link in s.get("navigates_to", []):
            if link["screen"] != s["id"]:
                incoming.add(link["screen"])
            lines.append(f'    {mermaid_node_id(s["id"])} -->|"{mermaid_label(link["element"])}"| '
                         f'{mermaid_node_id(link["screen"])}')
    warnings = [f"screen '{s['id']}' has no incoming navigation (not reachable from another screen)"
                for s in screens[1:] if s["id"] not in incoming]
    md = f"# Screen flow: {spec['project']}\n\n```mermaid\n" + "\n".join(lines) + "\n```\n"
    return md, warnings


GALLERY_CSS = """
:root { --bg:#f5f5f5; --fg:#222; --muted:#666; --card:#fff; --line:#d0d0d0; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161616; --fg:#eee; --muted:#9a9a9a; --card:#1e1e1e; --line:#444; }
}
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; line-height:1.5; }
header, main { max-width:1400px; margin:0 auto; }
h1 { margin:0 0 4px; font-size:1.5rem; }
.sub, .notes { color:var(--muted); margin:0; }
nav ul { list-style:none; padding:0; margin:16px 0 24px; display:flex; flex-wrap:wrap; gap:8px; }
nav a { display:inline-block; padding:4px 12px; border:1px solid var(--line); border-radius:16px;
  color:var(--fg); text-decoration:none; font-size:.9rem; }
main { display:flex; flex-wrap:wrap; gap:24px; align-items:flex-start; }
section { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px;
  max-width:100%; }
section h2 { margin:0 0 4px; font-size:1.1rem; }
.frame { margin-top:12px; overflow:auto; border:1px solid var(--line); }
.frame svg { display:block; max-width:100%; height:auto; }
.svg-dark { display:none; }
@media (prefers-color-scheme: dark) { .svg-light { display:none; } .svg-dark { display:block; } }
"""


def render_gallery(spec, light, dark):
    """Self-contained HTML gallery; light/dark SVG variants switch via prefers-color-scheme."""
    title = esc(spec["project"])
    items, sections = [], []
    for s in spec["screens"]:
        sid = esc(s["id"])
        items.append(f'<li><a href="#{sid}">{esc(s["name"])}</a></li>')
        notes = f'<p class="notes">{esc(s["notes"])}</p>' if s.get("notes") else ""
        sections.append(
            f'<section id="{sid}">\n<h2>{esc(s["name"])}</h2>\n{notes}\n'
            f'<div class="frame"><div class="svg-light">\n{light[s["id"]]}</div>'
            f'<div class="svg-dark">\n{dark[s["id"]]}</div></div>\n</section>')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title} wireframes</title>\n<style>{GALLERY_CSS}</style>\n</head>\n<body>\n'
        f'<header>\n<h1>{title}</h1>\n<p class="sub">{len(spec["screens"])} screen(s)</p>\n'
        f'<nav><ul>\n{chr(10).join(items)}\n</ul></nav>\n</header>\n'
        f'<main>\n{chr(10).join(sections)}\n</main>\n</body>\n</html>\n')


def write_text(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Render a wireframe spec to grayscale SVG files (one per screen) "
                    "plus a screen-flow.md Mermaid diagram.")
    p.add_argument("spec", help="Path to the wireframe spec JSON")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--theme", choices=sorted(THEMES), default="light",
                   help="Color theme of the SVG files (default: light)")
    p.add_argument("--html", action="store_true",
                   help="Also write index.html, a gallery with light and dark variants")
    args = p.parse_args(argv)

    try:
        with open(args.spec, encoding="utf-8") as fh:
            spec = json.load(fh)
    except OSError as exc:
        print(f"error: cannot read spec: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"error: spec is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors = validate_spec(spec)
    if errors:
        print(f"error: invalid wireframe spec ({len(errors)} problem(s)):", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1

    flow_md, flow_warnings = build_screen_flow(spec)
    try:
        os.makedirs(args.out, exist_ok=True)
        for screen in spec["screens"]:
            write_text(os.path.join(args.out, f"{screen['id']}.svg"),
                       render_screen(spec, screen, args.theme))
        write_text(os.path.join(args.out, "screen-flow.md"), flow_md)
        if args.html:
            light = {s["id"]: render_screen(spec, s, "light") for s in spec["screens"]}
            dark = {s["id"]: render_screen(spec, s, "dark") for s in spec["screens"]}
            write_text(os.path.join(args.out, "index.html"), render_gallery(spec, light, dark))
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1
    for message in flow_warnings:
        print(f"warning: {message}", file=sys.stderr)
    extras = "screen-flow.md" + (", index.html" if args.html else "")
    print(f"Rendered {len(spec['screens'])} screen(s) + {extras} to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
