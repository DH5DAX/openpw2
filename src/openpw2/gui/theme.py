"""HamRig design tokens adapted to Qt; no portal or network dependency.

Source: Gateway 3 webui/theme.css and drivers/amp/web/amps.css, commit
6e28350 (portal tokens dated 2026-10-05). See docs/design.md for the mapping.
"""

from pathlib import Path
from string import Template

TOKENS = {
    "hamrig_dark": "#16161A",
    "hamrig_dark_2": "#1F1F24",
    "hamrig_dark_3": "#24242B",
    "hamrig_dark_4": "#31313A",
    "hamrig_light": "#F2F2F7",
    "hamrig_light_2": "#AEAEB2",
    "hamrig_light_3": "#636366",
    "hamrig_light_muted": "#8E8E93",
    "hamrig_accent": "#8B1D1D",
    "hamrig_accent_tint": "#E05252",
    "hamrig_primary_dark": "#5F0F12",
    "hamrig_success": "#34C759",
    "hamrig_warning": "#FF9500",
    "hamrig_danger": "#FF3B30",
    "hamrig_info": "#0A84FF",
    "hamrig_border": "rgba(255, 255, 255, 20)",
    "hamrig_border_light": "rgba(255, 255, 255, 13)",
    "surface_high": "#2A2A32",
    "amp_bezel": "#1D1D22",
    "amp_rim": "#3A3A44",
    "amp_warn": "#F59E0B",
    "alarm_text": "#FF8A82",
    "font_primary": '"Inter", "Segoe UI", "DejaVu Sans"',
    "font_mono": '"JetBrains Mono", "Fira Code", "Consolas", "DejaVu Sans Mono"',
}


def stylesheet() -> str:
    """Expand CSS-token equivalents; Qt QSS has no CSS custom properties."""
    folder = Path(__file__).parent
    values = {
        **TOKENS,
        "chevron_down": (folder / "chevron-down.svg").as_posix(),
        "chevron_up": (folder / "chevron-up.svg").as_posix(),
    }
    return Template(folder.joinpath("theme.qss").read_text(encoding="utf-8")).substitute(values)


def set_tone(widget, tone: str) -> None:
    """Repolish only when a semantic state changes, not on every meter tick."""
    if widget.property("tone") != tone:
        widget.setProperty("tone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()
