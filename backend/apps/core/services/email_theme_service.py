from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings


VALID_VAR_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")

DEFAULT_THEME = {
    "rojo": "#931913",
    "celeste": "#8DBBC7",
    "blanco": "#ffffff",
    "gris": "#C7C6C6",
    "gris_oscuro": "#777777",
    "primary": "#931913",
    "secondary": "#8DBBC7",
    "text": "#1f2933",
    "text_muted": "#4b5563",
    "bg_dark": "#f6f4f4",
    "bg_dark_alt": "#d7d5d5",
    "radius": "12px",
    "radius_pill": "999px",
}


def _variables_path() -> Path:
    return Path(settings.FRONTEND_DIR) / "src" / "scss" / "base" / "_variables.scss"


def _strip_comment(line: str) -> str:
    in_single = False
    in_double = False

    for i in range(len(line) - 1):
        char = line[i]
        nxt = line[i + 1]

        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "/" and nxt == "/" and not in_single and not in_double:
            return line[:i].strip()

    return line.strip()


def _parse_scss_variable(line: str) -> tuple[str, str] | None:
    clean = _strip_comment(line)
    if not clean or not clean.startswith("$") or not clean.endswith(";"):
        return None

    body = clean[:-1].strip()  # quita ';'
    name_part, sep, value_part = body.partition(":")
    if not sep:
        return None

    name = name_part[1:].strip()  # quita '$'
    value = value_part.strip()

    if not name or not value:
        return None

    if not VALID_VAR_NAME.fullmatch(name):
        return None

    return name, value


def _is_scalar(value: str) -> bool:
    value = (value or "").strip().lower()

    return bool(
        value.startswith("#")
        or value.startswith("rgb(")
        or value.startswith("rgba(")
        or value.startswith("hsl(")
        or value.startswith("hsla(")
        or value.startswith("var(")
        or value.startswith("calc(")
        or value.endswith(("px", "rem", "em", "%"))
        or value.replace(".", "", 1).isdigit()
        or (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    )


@lru_cache(maxsize=1)
def get_email_theme_tokens() -> dict[str, str]:
    raw: dict[str, str] = {}
    variables_file = _variables_path()

    try:
        if variables_file.exists():
            for line in variables_file.read_text(encoding="utf-8").splitlines():
                parsed = _parse_scss_variable(line)
                if parsed:
                    name, value = parsed
                    raw[name] = value
    except OSError:
        raw = {}

    def resolve(name: str, *, visited: set[str] | None = None) -> str:
        visited = visited or set()
        if name in visited:
            return DEFAULT_THEME.get(name, "")

        visited.add(name)

        value = raw.get(name, DEFAULT_THEME.get(name, ""))
        if value.startswith("$"):
            return resolve(value[1:], visited=visited)
        if _is_scalar(value):
            return value
        return DEFAULT_THEME.get(name, value)

    primary = resolve("primary")
    secondary = resolve("secondary")
    surface = resolve("blanco")
    line = resolve("gris")

    return {
        "primary": primary,
        "secondary": secondary,
        "surface": surface,
        "canvas": resolve("bg_dark"),
        "line": line,
        "text": resolve("text"),
        "text_muted": resolve("text_muted"),
        "radius": resolve("radius"),
        "radius_pill": resolve("radius_pill"),
        "hero_background": primary,
        "hero_text": surface,
        "code_background": surface,
        "code_border": secondary,
        "button_background": primary,
        "button_text": surface,
        "panel_border": line,
        "meta_background": resolve("bg_dark_alt"),
    }