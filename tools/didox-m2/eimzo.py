"""E-IMZO bilan ishlash: kalitlar ro'yxati va PKCS#7 imzo.

Asosiy yo'l - E-IMZO ilovasining lokal WebSocket API'si (CAPIWS).
Parol faqat imzo chekishda (load_key) kerak; ro'yxatni olish uchun kerak emas.
Zaxira yo'l - DSKEYS papkasini fayl tizimi orqali skanerlash.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, asdict
from typing import Any


class EimzoError(RuntimeError):
    pass


@dataclass
class CertInfo:
    cn: str = ""            # kalit egasining F.I.Sh.
    tin: str = ""           # STIR (1.2.860.3.16.1.2)
    pinfl: str = ""         # JSHSHIR (1.2.860.3.16.1.1)
    org: str = ""           # tashkilot nomi (O)
    position: str = ""      # lavozim (T)
    serial: str = ""
    valid_from: str = ""
    valid_to: str = ""
    file_name: str = ""
    full_path: str = ""
    alias: str = ""
    disk: str = ""          # E-IMZO: disk (masalan "E:")
    path_only: str = ""     # E-IMZO: papka yo'li
    source: str = ""        # "eimzo" yoki "filescan"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# CAPIWS (WebSocket)
# --------------------------------------------------------------------------

class Capiws:
    """E-IMZO lokal WebSocket klienti."""

    def __init__(self, url: str = "ws://127.0.0.1:64646/service/cryptapi",
                 timeout: int = 20, apikey_arguments: list[str] | None = None):
        self.url = url
        self.timeout = timeout
        self.apikey_arguments = apikey_arguments or []
        self._ws = None

    def __enter__(self) -> "Capiws":
        try:
            import websocket  # websocket-client
        except ImportError as exc:  # pragma: no cover
            raise EimzoError(
                "websocket-client o'rnatilmagan. `pip install -r requirements.txt`"
            ) from exc
        try:
            self._ws = websocket.create_connection(self.url, timeout=self.timeout)
        except Exception as exc:
            raise EimzoError(
                f"E-IMZO'ga ulanib bo'lmadi ({self.url}). "
                "E-IMZO ilovasi ishga tushirilganini tekshiring."
            ) from exc
        if self.apikey_arguments:
            self.call({"plugin": "apikey", "name": "apikey",
                       "arguments": self.apikey_arguments}, raise_on_fail=False)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    def call(self, payload: dict[str, Any], raise_on_fail: bool = True) -> dict[str, Any]:
        if self._ws is None:
            raise EimzoError("WebSocket ochilmagan (with-block ichida ishlating).")
        self._ws.send(json.dumps(payload))
        raw = self._ws.recv()
        data = json.loads(raw)
        if raise_on_fail and not data.get("success", False):
            reason = data.get("reason") or data.get("message") or raw
            raise EimzoError(f"E-IMZO xatosi ({payload.get('name')}): {reason}")
        return data

    def list_certificates(self) -> list[CertInfo]:
        data = self.call({"plugin": "pfx", "name": "list_all_certificates"})
        items = data.get("certificates") or []
        return [_cert_from_capiws(item) for item in items]

    def load_key(self, cert: CertInfo) -> str:
        """Kalitni ochadi va key_id qaytaradi.

        Parolni E-IMZO ilovasining o'z oynasi so'raydi - bu skript parolni
        na so'raydi, na ko'radi, na saqlaydi.
        """
        data = self.call({
            "plugin": "pfx", "name": "load_key",
            "arguments": [cert.disk, cert.path_only, cert.file_name, cert.alias],
        })
        key_id = data["keyId"]
        self.call({"plugin": "pfx", "name": "verify_password", "arguments": [key_id]})
        return key_id

    def create_pkcs7(self, data_b64: str, key_id: str, detached: str = "no") -> str:
        data = self.call({
            "plugin": "pkcs7", "name": "create_pkcs7",
            "arguments": [data_b64, key_id, detached],
        })
        return data["pkcs7_64"]


_ALIAS_KEYS = {
    "cn": "cn",
    "name": "cn",
    "o": "org",
    "t": "position",
    "serialnumber": "serial",
    "validfrom": "valid_from",
    "validto": "valid_to",
    "1.2.860.3.16.1.2": "tin",
    "1.2.860.3.16.1.1": "pinfl",
}


def parse_alias(alias: str) -> dict[str, str]:
    """E-IMZO alias satrini lug'atga aylantiradi.

    Namuna: "1.2.860.3.16.1.2=312386763,cn=...,o=...,t=...,validfrom=...,validto=..."
    """
    out: dict[str, str] = {}
    for part in alias.split(","):
        if "=" not in part:
            continue
        raw_key, _, raw_val = part.partition("=")
        field_name = _ALIAS_KEYS.get(raw_key.strip().lower())
        if field_name and raw_val.strip() and not out.get(field_name):
            out[field_name] = raw_val.strip()
    return out


def _cert_from_capiws(item: dict[str, Any]) -> CertInfo:
    alias = item.get("alias", "") or ""
    parsed = parse_alias(alias)
    cert = CertInfo(
        cn=parsed.get("cn", ""),
        tin=parsed.get("tin", ""),
        pinfl=parsed.get("pinfl", ""),
        org=parsed.get("org", ""),
        position=parsed.get("position", ""),
        serial=parsed.get("serial", "") or item.get("serialNumber", ""),
        valid_from=parsed.get("valid_from", "") or item.get("validFrom", ""),
        valid_to=parsed.get("valid_to", "") or item.get("validTo", ""),
        file_name=item.get("name", ""),
        alias=alias,
        source="eimzo",
    )
    disk = item.get("disk", "")
    path = item.get("path", "")
    cert.disk = disk
    cert.path_only = path
    cert.full_path = _join_win(disk, path, cert.file_name)
    return cert


def _join_win(disk: str, path: str, name: str) -> str:
    parts = [p for p in (disk, path, name) if p]
    joined = "\\".join(p.strip("\\") for p in parts)
    if disk and not joined.startswith(disk):
        joined = disk + "\\" + joined
    return joined.replace("\\\\", "\\")


# --------------------------------------------------------------------------
# Zaxira: DSKEYS papkasini skanerlash
# --------------------------------------------------------------------------

_TIN_IN_NAME = re.compile(r"(?<!\d)(\d{9})(?!\d)")


def scan_keys_dir(keys_dir: str) -> list[CertInfo]:
    """DSKEYS papkasidagi .pfx/.p12/.crt fayllarini skanerlaydi.

    Sertifikat mazmuni parolsiz o'qilmasligi mumkin - u holda fayl nomi va
    yo'li qaytariladi, sanalar bo'sh qoladi.
    """
    results: list[CertInfo] = []
    if not os.path.isdir(keys_dir):
        return results

    patterns = ("*.pfx", "*.p12", "*.crt", "*.cer")
    files: list[str] = []
    for pattern in patterns:
        files.extend(glob.glob(os.path.join(keys_dir, "**", pattern), recursive=True))

    for path in sorted(set(files)):
        cert = CertInfo(
            file_name=os.path.basename(path),
            full_path=os.path.abspath(path),
            source="filescan",
        )
        found = _TIN_IN_NAME.search(cert.file_name)
        if found:
            cert.tin = found.group(1)
        _enrich_from_file(cert, path)
        results.append(cert)
    return results


def _enrich_from_file(cert: CertInfo, path: str) -> None:
    """Imkon bo'lsa sertifikatdan sana/F.I.Sh. o'qiydi (parolsiz)."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError:
        return

    try:
        with open(path, "rb") as handle:
            blob = handle.read()
    except OSError:
        return

    x509_cert = None
    lower = path.lower()
    try:
        if lower.endswith((".crt", ".cer")):
            x509_cert = x509.load_der_x509_certificate(blob)
    except Exception:
        try:
            x509_cert = x509.load_pem_x509_certificate(blob)
        except Exception:
            x509_cert = None

    if x509_cert is None and lower.endswith((".pfx", ".p12")):
        for pwd in (None, b""):
            try:
                _, x509_cert, _ = pkcs12.load_key_and_certificates(blob, pwd)
                break
            except Exception:
                x509_cert = None

    if x509_cert is None:
        return

    # cryptography < 42 da *_utc xossalari yo'q
    not_before = getattr(x509_cert, "not_valid_before_utc", None) or x509_cert.not_valid_before
    not_after = getattr(x509_cert, "not_valid_after_utc", None) or x509_cert.not_valid_after
    cert.valid_from = not_before.strftime("%Y-%m-%d %H:%M:%S")
    cert.valid_to = not_after.strftime("%Y-%m-%d %H:%M:%S")
    cert.serial = format(x509_cert.serial_number, "x")
    for attr in x509_cert.subject:
        oid = attr.oid.dotted_string
        value = str(attr.value)
        if oid == "2.5.4.3":
            cert.cn = cert.cn or value
        elif oid == "2.5.4.10":
            cert.org = cert.org or value
        elif oid == "2.5.4.12":
            cert.position = cert.position or value
        elif oid == "1.2.860.3.16.1.2":
            cert.tin = value
        elif oid == "1.2.860.3.16.1.1":
            cert.pinfl = value


def collect_certificates(cfg: dict[str, Any]) -> tuple[list[CertInfo], list[str]]:
    """E-IMZO orqali, bo'lmasa fayl skanerlash orqali sertifikatlarni yig'adi."""
    notes: list[str] = []
    eimzo_cfg = cfg.get("eimzo", {})
    try:
        with Capiws(eimzo_cfg.get("ws_url", "ws://127.0.0.1:64646/service/cryptapi"),
                    int(eimzo_cfg.get("timeout", 20)),
                    eimzo_cfg.get("apikey_arguments")) as ws:
            certs = ws.list_certificates()
        if certs:
            notes.append(f"Manba: E-IMZO lokal API ({len(certs)} ta kalit).")
            return certs, notes
        notes.append("E-IMZO ulandi, lekin kalit topilmadi.")
    except EimzoError as exc:
        notes.append(f"E-IMZO ishlatilmadi: {exc}")

    keys_dir = cfg.get("keys_dir", "")
    certs = scan_keys_dir(keys_dir)
    notes.append(f"Manba: papka skaneri {keys_dir} ({len(certs)} ta fayl).")
    return certs, notes
