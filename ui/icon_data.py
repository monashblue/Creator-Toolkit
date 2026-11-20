"""Data ikon SVG bergaya garis (24x24). Digambar sendiri untuk proyek ini."""

from __future__ import annotations

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">{body}</svg>'
)

ICON_BODIES: dict[str, str] = {
    "dashboard": (
        '<rect width="7" height="9" x="3" y="3" rx="1"/>'
        '<rect width="7" height="5" x="14" y="3" rx="1"/>'
        '<rect width="7" height="9" x="14" y="12" rx="1"/>'
        '<rect width="7" height="5" x="3" y="16" rx="1"/>'
    ),
    "qr": (
        '<rect width="6" height="6" x="3" y="3" rx="1"/>'
        '<rect width="6" height="6" x="15" y="3" rx="1"/>'
        '<rect width="6" height="6" x="3" y="15" rx="1"/>'
        '<path d="M15 15h.01M21 15h.01M15 21h.01M21 21h.01M18 18h.01M12 3v4M12 11v2M12 17v4"/>'
    ),
    "background": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/>'
        '<circle cx="9" cy="9" r="2"/>'
        '<path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>'
    ),
    "resizer": (
        '<path d="M15 3h6v6"/><path d="M9 21H3v-6"/>'
        '<path d="m21 3-7 7"/><path d="m3 21 7-7"/>'
    ),
    "converter": (
        '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/>'
        '<path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>'
    ),
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "settings": (
        '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/>'
        '<path d="M1 14h6M9 8h6M17 16h6"/>'
    ),
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
}


def build_svg(name: str, color: str) -> str:
    """Membuat string SVG untuk ikon bernama `name` dengan warna garis `color`."""
    return _SVG_TEMPLATE.format(color=color, body=ICON_BODIES[name])
