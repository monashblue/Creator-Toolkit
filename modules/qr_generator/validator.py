"""Validasi dan normalisasi input untuk setiap jenis QR."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

MAX_TEXT_BYTES = 2900  # di bawah kapasitas QR versi 40 level L (2953 byte)

_PHONE_STRIP = re.compile(r"[\s\-().]")
_DIGITS = re.compile(r"[0-9]+")
_HEX = re.compile(r"[0-9A-Fa-f]+")
_EMAIL = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9-]{2,63}$")
_COORDS = re.compile(r"^(-?\d{1,3}(?:\.\d+)?)\s*[,;\s]\s*(-?\d{1,3}(?:\.\d+)?)$")
_MAPS_HOSTS = {"google.com", "www.google.com", "maps.google.com", "maps.app.goo.gl", "goo.gl"}


@dataclass
class ValidationResult:
    normalized: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _text(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def _check_length(value: str, key: str, limit: int, label: str, r: ValidationResult) -> None:
    if len(value) > limit:
        r.errors[key] = f"{label} terlalu panjang (maksimal {limit} karakter)."


def _valid_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return False
    return bool(_DOMAIN.match(ascii_host))


def _check_url(raw: str, key: str, r: ValidationResult, required: bool = True) -> str:
    if not raw:
        if required:
            r.errors[key] = "Masukkan alamat website."
        return ""
    if re.search(r"\s", raw):
        r.errors[key] = "Alamat website tidak boleh mengandung spasi."
        return ""
    if len(raw) > 2000:
        r.errors[key] = "Alamat website terlalu panjang (maksimal 2000 karakter)."
        return ""
    candidate = raw
    if "://" not in candidate:
        candidate = "https://" + candidate
        r.warnings.append("Awalan https:// ditambahkan otomatis pada alamat website.")
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        _ = parts.port
    except ValueError:
        r.errors[key] = "Alamat website tidak valid."
        return ""
    if parts.scheme not in ("http", "https") or not host or not _valid_host(host):
        r.errors[key] = "Alamat website tidak valid. Contoh: https://contoh.id"
        return ""
    if parts.scheme == "http":
        r.warnings.append("Alamat memakai http tanpa enkripsi. Pertimbangkan https.")
    return candidate


def _check_phone(raw: str, key: str, r: ValidationResult, required: bool = True) -> str:
    cleaned = _PHONE_STRIP.sub("", raw)
    if not cleaned:
        if required:
            r.errors[key] = "Masukkan nomor telepon."
        return ""
    plus = cleaned.startswith("+")
    digits = cleaned[1:] if plus else cleaned
    if not _DIGITS.fullmatch(digits):
        r.errors[key] = "Nomor hanya boleh berisi angka, spasi, tanda hubung, tanda kurung, dan awalan +."
        return ""
    if not 5 <= len(digits) <= 15:
        r.errors[key] = "Nomor telepon harus terdiri dari 5 sampai 15 digit."
        return ""
    if not plus and digits.startswith("0"):
        r.warnings.append(
            "Nomor tanpa kode negara hanya dapat dihubungi dari negara yang sama. "
            "Awali dengan + dan kode negara bila perlu."
        )
    return ("+" if plus else "") + digits


def _check_email(raw: str, key: str, r: ValidationResult, required: bool = True) -> str:
    if not raw:
        if required:
            r.errors[key] = "Masukkan alamat email."
        return ""
    local = raw.split("@", 1)[0]
    if len(raw) > 254 or len(local) > 64 or not _EMAIL.match(raw):
        r.errors[key] = "Alamat email tidak valid. Contoh: nama@contoh.id"
        return ""
    return raw


def _validate_url(values: Mapping[str, Any], r: ValidationResult) -> None:
    url = _check_url(_text(values, "url"), "url", r)
    if url:
        r.normalized["url"] = url


def _validate_text(values: Mapping[str, Any], r: ValidationResult) -> None:
    text = _text(values, "text")
    if not text:
        r.errors["text"] = "Masukkan teks."
    elif len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        r.errors["text"] = "Teks terlalu panjang untuk dimuat dalam satu kode QR."
    else:
        r.normalized["text"] = text


def _validate_whatsapp(values: Mapping[str, Any], r: ValidationResult) -> None:
    raw = _PHONE_STRIP.sub("", _text(values, "phone"))
    message = _text(values, "message")
    if not raw:
        r.errors["phone"] = "Masukkan nomor WhatsApp."
    else:
        if raw.startswith("+"):
            digits = raw[1:]
        elif raw.startswith("00"):
            digits = raw[2:]
        elif raw.startswith("0"):
            r.errors["phone"] = (
                "Nomor diawali 0 tidak dapat dipakai. Gunakan kode negara, "
                "misalnya 62812... untuk nomor Indonesia."
            )
            digits = ""
        else:
            digits = raw
        if "phone" not in r.errors:
            if not _DIGITS.fullmatch(digits):
                r.errors["phone"] = "Nomor hanya boleh berisi angka dan awalan +."
            elif not 8 <= len(digits) <= 15:
                r.errors["phone"] = "Nomor WhatsApp harus terdiri dari 8 sampai 15 digit termasuk kode negara."
            else:
                r.normalized["phone"] = digits
    _check_length(message, "message", 1000, "Pesan", r)
    r.normalized["message"] = message


def _validate_wifi(values: Mapping[str, Any], r: ValidationResult) -> None:
    ssid = values.get("ssid", "")
    ssid = ssid if isinstance(ssid, str) else ""
    password = values.get("password", "")
    password = password if isinstance(password, str) else ""
    security = _text(values, "security") or "WPA"
    hidden = bool(values.get("hidden", False))

    if security not in ("WPA", "WEP", "nopass"):
        r.errors["security"] = "Jenis keamanan tidak dikenal."
        security = "WPA"
    if not ssid.strip():
        r.errors["ssid"] = "Masukkan nama jaringan (SSID)."
    elif len(ssid.encode("utf-8")) > 32:
        r.errors["ssid"] = "Nama jaringan maksimal 32 byte."

    if security == "WPA":
        if not password:
            r.errors["password"] = "Masukkan kata sandi, atau pilih Tanpa kata sandi."
        elif not (8 <= len(password) <= 63 or (len(password) == 64 and _HEX.fullmatch(password))):
            r.errors["password"] = "Kata sandi WPA harus 8 sampai 63 karakter."
    elif security == "WEP":
        valid_ascii = len(password) in (5, 13)
        valid_hex = len(password) in (10, 26) and bool(_HEX.fullmatch(password))
        if not (valid_ascii or valid_hex):
            r.errors["password"] = "Kata sandi WEP harus 5 atau 13 karakter, atau 10 atau 26 digit heksadesimal."
        r.warnings.append("WEP sudah tidak aman. Gunakan WPA bila memungkinkan.")
    elif password:
        r.warnings.append("Kata sandi diabaikan karena jaringan dipilih tanpa kata sandi.")
        password = ""

    r.normalized.update(ssid=ssid, security=security, password=password, hidden=hidden)


def _validate_email(values: Mapping[str, Any], r: ValidationResult) -> None:
    to = _check_email(_text(values, "to"), "to", r)
    subject = _text(values, "subject")
    body = _text(values, "body")
    _check_length(subject, "subject", 200, "Subjek", r)
    _check_length(body, "body", 1000, "Isi pesan", r)
    r.normalized.update(to=to, subject=subject, body=body)


def _validate_phone(values: Mapping[str, Any], r: ValidationResult) -> None:
    number = _check_phone(_text(values, "number"), "number", r)
    if number:
        r.normalized["number"] = number


def _validate_vcard(values: Mapping[str, Any], r: ValidationResult) -> None:
    fields = {
        key: _text(values, key)
        for key in (
            "first_name", "last_name", "org", "job_title", "phone", "email",
            "website", "street", "city", "region", "postal_code", "country",
        )
    }
    labels = {
        "first_name": "Nama depan", "last_name": "Nama belakang", "org": "Organisasi",
        "job_title": "Jabatan", "street": "Alamat jalan", "city": "Kota",
        "region": "Provinsi", "postal_code": "Kode pos", "country": "Negara",
    }
    for key, label in labels.items():
        _check_length(fields[key], key, 100, label, r)
    if not fields["first_name"] and not fields["last_name"]:
        r.errors["first_name"] = "Isi nama depan atau nama belakang."
    fields["phone"] = _check_phone(fields["phone"], "phone", r, required=False)
    fields["email"] = _check_email(fields["email"], "email", r, required=False)
    fields["website"] = _check_url(fields["website"], "website", r, required=False)
    r.normalized.update(fields)


def _validate_maps(values: Mapping[str, Any], r: ValidationResult) -> None:
    raw = _text(values, "location")
    if not raw:
        r.errors["location"] = "Masukkan koordinat, nama tempat, atau tautan Google Maps."
        return

    match = _COORDS.match(raw)
    if match:
        lat, lon = match.group(1), match.group(2)
        if not -90 <= float(lat) <= 90:
            r.errors["location"] = "Lintang harus antara -90 dan 90."
        elif not -180 <= float(lon) <= 180:
            r.errors["location"] = "Bujur harus antara -180 dan 180."
        else:
            r.normalized.update(kind="coords", lat=lat, lon=lon)
        return

    if re.match(r"^https?://", raw, re.IGNORECASE):
        try:
            parts = urlsplit(raw)
            host = (parts.hostname or "").lower()
        except ValueError:
            host = ""
            parts = None
        is_maps = host in _MAPS_HOSTS and (
            host in ("maps.google.com", "maps.app.goo.gl")
            or (parts is not None and parts.path.startswith(("/maps", "/maps/")))
        )
        if is_maps and not re.search(r"\s", raw):
            r.normalized.update(kind="url", url=raw)
        else:
            r.errors["location"] = "Tautan harus berasal dari Google Maps. Atau isi koordinat atau nama tempat."
        return

    if len(raw) < 2:
        r.errors["location"] = "Nama tempat terlalu pendek."
    elif len(raw) > 300:
        r.errors["location"] = "Nama tempat terlalu panjang (maksimal 300 karakter)."
    else:
        r.normalized.update(kind="query", query=raw)
        r.warnings.append("Hasil pencarian nama tempat ditentukan Google Maps. Koordinat lebih tepat.")


_VALIDATORS: dict[str, Callable[[Mapping[str, Any], ValidationResult], None]] = {
    "url": _validate_url,
    "text": _validate_text,
    "whatsapp": _validate_whatsapp,
    "wifi": _validate_wifi,
    "email": _validate_email,
    "phone": _validate_phone,
    "vcard": _validate_vcard,
    "maps": _validate_maps,
}


def validate(type_id: str, values: Mapping[str, Any]) -> ValidationResult:
    """Memvalidasi nilai isian dan mengembalikan data ternormalisasi, kesalahan per kolom, dan peringatan."""
    try:
        validator = _VALIDATORS[type_id]
    except KeyError:
        raise ValueError(f"Jenis QR tidak dikenal: {type_id}") from None
    result = ValidationResult()
    validator(values, result)
    return result
