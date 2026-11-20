"""Definisi jenis QR, kolom isian, dan pembuatan teks payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

KIND_LINE = "line"
KIND_MULTILINE = "multiline"
KIND_CHOICE = "choice"
KIND_BOOL = "bool"


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str = KIND_LINE
    required: bool = False
    placeholder: str = ""
    help: str = ""
    choices: tuple[tuple[str, str], ...] = ()  # (teks tampilan, nilai)


@dataclass(frozen=True)
class QRTypeSpec:
    type_id: str
    label: str
    description: str
    fields: tuple[FieldSpec, ...]


WIFI_SECURITY_CHOICES = (
    ("WPA / WPA2 / WPA3", "WPA"),
    ("WEP", "WEP"),
    ("Tanpa kata sandi", "nopass"),
)

QR_TYPES: tuple[QRTypeSpec, ...] = (
    QRTypeSpec(
        "url",
        "URL",
        "Mengarahkan pemindai ke sebuah alamat website.",
        (FieldSpec("url", "Alamat website", required=True, placeholder="contoh.id atau https://contoh.id/halaman"),),
    ),
    QRTypeSpec(
        "text",
        "Teks biasa",
        "Menampilkan teks apa adanya setelah dipindai.",
        (FieldSpec("text", "Teks", KIND_MULTILINE, required=True, placeholder="Tulis teks di sini"),),
    ),
    QRTypeSpec(
        "whatsapp",
        "WhatsApp",
        "Membuka percakapan WhatsApp dengan nomor tertentu, dengan pesan awal opsional.",
        (
            FieldSpec(
                "phone",
                "Nomor WhatsApp",
                required=True,
                placeholder="628123456789 atau +62 812 3456 789",
                help="Gunakan format internasional, diawali kode negara.",
            ),
            FieldSpec("message", "Pesan awal (opsional)", KIND_MULTILINE, placeholder="Halo, saya ingin bertanya"),
        ),
    ),
    QRTypeSpec(
        "wifi",
        "Wi-Fi",
        "Menyambungkan perangkat ke jaringan Wi-Fi tanpa mengetik kata sandi.",
        (
            FieldSpec("ssid", "Nama jaringan (SSID)", required=True),
            FieldSpec("security", "Keamanan", KIND_CHOICE, choices=WIFI_SECURITY_CHOICES),
            FieldSpec("password", "Kata sandi", help="Kosongkan bila jaringan tidak memakai kata sandi."),
            FieldSpec("hidden", "Jaringan tersembunyi", KIND_BOOL),
        ),
    ),
    QRTypeSpec(
        "email",
        "Email",
        "Membuka aplikasi email dengan penerima, subjek, dan isi yang sudah terisi.",
        (
            FieldSpec("to", "Alamat email tujuan", required=True, placeholder="nama@contoh.id"),
            FieldSpec("subject", "Subjek (opsional)"),
            FieldSpec("body", "Isi pesan (opsional)", KIND_MULTILINE),
        ),
    ),
    QRTypeSpec(
        "phone",
        "Nomor telepon",
        "Menyiapkan panggilan ke nomor telepon.",
        (FieldSpec("number", "Nomor telepon", required=True, placeholder="+62 21 1234 5678"),),
    ),
    QRTypeSpec(
        "vcard",
        "Kontak (vCard)",
        "Menyimpan data kontak ke buku alamat.",
        (
            FieldSpec("first_name", "Nama depan"),
            FieldSpec("last_name", "Nama belakang"),
            FieldSpec("org", "Organisasi"),
            FieldSpec("job_title", "Jabatan"),
            FieldSpec("phone", "Telepon", placeholder="+62 812 3456 789"),
            FieldSpec("email", "Email"),
            FieldSpec("website", "Website"),
            FieldSpec("street", "Alamat jalan"),
            FieldSpec("city", "Kota"),
            FieldSpec("region", "Provinsi"),
            FieldSpec("postal_code", "Kode pos"),
            FieldSpec("country", "Negara"),
        ),
    ),
    QRTypeSpec(
        "maps",
        "Lokasi Google Maps",
        "Membuka lokasi di Google Maps.",
        (
            FieldSpec(
                "location",
                "Lokasi",
                required=True,
                placeholder="-6.2088, 106.8456 atau Monumen Nasional, Jakarta",
                help="Isi dengan koordinat, nama tempat, atau tautan Google Maps.",
            ),
        ),
    ),
)

QR_TYPE_IDS = tuple(spec.type_id for spec in QR_TYPES)


def get_type_spec(type_id: str) -> QRTypeSpec:
    for spec in QR_TYPES:
        if spec.type_id == type_id:
            return spec
    raise ValueError(f"Jenis QR tidak dikenal: {type_id}")


def _wifi_escape(value: str) -> str:
    for char in ("\\", ";", ",", ":", '"'):
        value = value.replace(char, "\\" + char)
    return value


def _vcard_escape(value: str) -> str:
    value = value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n")
    return value.replace(";", "\\;").replace(",", "\\,")


def _build_url(n: Mapping[str, Any]) -> str:
    return n["url"]


def _build_text(n: Mapping[str, Any]) -> str:
    return n["text"]


def _build_whatsapp(n: Mapping[str, Any]) -> str:
    payload = f"https://wa.me/{n['phone']}"
    if n.get("message"):
        payload += "?text=" + quote(n["message"], safe="")
    return payload


def _build_wifi(n: Mapping[str, Any]) -> str:
    security = n["security"]
    parts = [f"T:{security}", f"S:{_wifi_escape(n['ssid'])}"]
    if security != "nopass" and n.get("password"):
        parts.append(f"P:{_wifi_escape(n['password'])}")
    if n.get("hidden"):
        parts.append("H:true")
    return "WIFI:" + ";".join(parts) + ";;"


def _build_email(n: Mapping[str, Any]) -> str:
    payload = "mailto:" + quote(n["to"], safe="@+!$'*-/=^_`{|}~.")
    query = []
    if n.get("subject"):
        query.append("subject=" + quote(n["subject"], safe=""))
    if n.get("body"):
        query.append("body=" + quote(n["body"], safe=""))
    if query:
        payload += "?" + "&".join(query)
    return payload


def _build_phone(n: Mapping[str, Any]) -> str:
    return "tel:" + n["number"]


def _build_vcard(n: Mapping[str, Any]) -> str:
    first, last = n.get("first_name", ""), n.get("last_name", "")
    full_name = " ".join(part for part in (first, last) if part)
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{_vcard_escape(last)};{_vcard_escape(first)};;;",
        f"FN:{_vcard_escape(full_name)}",
    ]
    if n.get("org"):
        lines.append(f"ORG:{_vcard_escape(n['org'])}")
    if n.get("job_title"):
        lines.append(f"TITLE:{_vcard_escape(n['job_title'])}")
    if n.get("phone"):
        lines.append(f"TEL;TYPE=CELL:{n['phone']}")
    if n.get("email"):
        lines.append(f"EMAIL:{n['email']}")
    if n.get("website"):
        lines.append(f"URL:{n['website']}")
    address = [n.get(key, "") for key in ("street", "city", "region", "postal_code", "country")]
    if any(address):
        lines.append("ADR;TYPE=WORK:;;" + ";".join(_vcard_escape(part) for part in address))
    lines.append("END:VCARD")
    return "\r\n".join(lines)


def _build_maps(n: Mapping[str, Any]) -> str:
    kind = n["kind"]
    if kind == "url":
        return n["url"]
    if kind == "coords":
        return f"https://www.google.com/maps/search/?api=1&query={n['lat']}%2C{n['lon']}"
    return "https://www.google.com/maps/search/?api=1&query=" + quote(n["query"], safe="")


_BUILDERS = {
    "url": _build_url,
    "text": _build_text,
    "whatsapp": _build_whatsapp,
    "wifi": _build_wifi,
    "email": _build_email,
    "phone": _build_phone,
    "vcard": _build_vcard,
    "maps": _build_maps,
}


def build_payload(type_id: str, normalized: Mapping[str, Any]) -> str:
    """Membuat teks yang akan dienkode ke QR dari data yang sudah divalidasi."""
    try:
        builder = _BUILDERS[type_id]
    except KeyError:
        raise ValueError(f"Jenis QR tidak dikenal: {type_id}") from None
    return builder(normalized)
