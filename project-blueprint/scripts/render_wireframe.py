#!/usr/bin/env python3
"""Render a wireframe spec (JSON) to low-fidelity grayscale SVG, one file per screen.

Usage: render_wireframe.py spec.json --out <dir> [--theme light|dark]

Standard library only, no network, no external assets. Output is deterministic:
the same spec always produces byte-identical SVG (no timestamps, no random ids).
Validation is hand-written and reports the JSON path of every problem, e.g.
"screens[1].elements[2]: input requires 'label'".

Elements are laid out in a simple vertical stack. Element types that are valid
but not drawn yet are rendered as a labeled placeholder box such as "[table]".
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
INVALID_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

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
DRAWN_TYPES = {"header", "text", "input", "button", "link", "divider", "spacer"}


# ---------------------------------------------------------------- validation

def validate_elements(elements, path, errors):
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
        if etype in ("row", "column") and isinstance(el.get("children"), list):
            validate_elements(el["children"], f"{p}.children", errors)


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

    def line(self, x1, y1, x2, y2):
        self.parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{self.t["line"]}" stroke-width="1"/>')

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


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Render a wireframe spec to grayscale SVG files (one per screen).")
    p.add_argument("spec", help="Path to the wireframe spec JSON")
    p.add_argument("--out", required=True, help="Output directory for the SVG files")
    p.add_argument("--theme", choices=sorted(THEMES), default="light",
                   help="Color theme (default: light)")
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

    try:
        os.makedirs(args.out, exist_ok=True)
        for screen in spec["screens"]:
            path = os.path.join(args.out, f"{screen['id']}.svg")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(render_screen(spec, screen, args.theme))
    except OSError as exc:
        print(f"error: cannot write output: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered {len(spec['screens'])} screen(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
