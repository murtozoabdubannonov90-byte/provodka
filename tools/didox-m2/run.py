#!/usr/bin/env python3
"""SOLIDUM M-2 ishonchnoma quvuri: kalitlar -> oxirgi ishonchnoma -> Didox.

Bosqichlar:
  1) keys          DSKEYS'dan STIR bo'yicha sertifikatni topib kalitlar.md yozadi
  2) last          Hujjatlar papkasidan oxirgi ishonchnomani o'qiydi
  3) fetch-sample  Didox'dan haqiqiy ishonchnoma JSON'ini namuna qilib oladi
  4) build         Yangi M-2 payload'ini yasaydi (yubormaydi)
  5) send          Tasdiqlangandan keyin Didox'ga yuboradi va imzolaydi
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from typing import Any

import m2
import poa_source
from didox import DidoxClient, DidoxError
from eimzo import Capiws, EimzoError
from keys_report import write_report

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "state.json")


# --------------------------------------------------------------------------
# Konfiguratsiya va holat
# --------------------------------------------------------------------------

def load_config(path: str | None) -> dict[str, Any]:
    target = path or os.path.join(HERE, "config.json")
    if not os.path.exists(target):
        example = os.path.join(HERE, "config.example.json")
        raise SystemExit(
            f"config.json topilmadi.\nNusxa oling: copy \"{example}\" \"{target}\""
        )
    with open(target, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_state() -> dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(state: dict[str, Any]) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


# --------------------------------------------------------------------------
# 1. Kalitlar
# --------------------------------------------------------------------------

def cmd_keys(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    _print_header("Sertifikatlar")
    target, matched = write_report(cfg)
    print(f"Hisobot yozildi: {target}")
    if not matched:
        print("Mos sertifikat topilmadi — kalitlar.md ichidagi izohlarni ko'ring.")
        return 1
    for cert in matched:
        print(f"\n  F.I.Sh.        : {cert.cn or '—'}")
        print(f"  Berilgan sana  : {cert.valid_from or '—'}")
        print(f"  Tugash sanasi  : {cert.valid_to or '—'}")
        print(f"  Fayl nomi      : {cert.file_name or '—'}")
        print(f"  To'liq yo'l    : {cert.full_path or '—'}")
    return 0


# --------------------------------------------------------------------------
# 2. Oxirgi ishonchnoma
# --------------------------------------------------------------------------

def cmd_last(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    _print_header("Oxirgi ishonchnoma")
    person, notes = poa_source.read_last_poa(cfg.get("docs_dir", ""))
    for note in notes:
        print(f"  · {note}")
    if person is None:
        return 1

    print("\n  Ishonchli shaxs (o'zgartirilmagan holda):")
    print(f"    F.I.Sh.          : {person.fio or '—'}")
    print(f"    Lavozimi         : {person.position or '—'}")
    print(f"    Pasport          : {person.passport or '—'}")
    print(f"    Oldingi raqam    : {person.doc_number or '—'}")
    print(f"    Keyingi raqam    : {poa_source.next_number(person.doc_number) or '—'}")
    if person.context:
        print("\n  Hujjatdagi qatorlar:")
        for line in person.context:
            print(f"    | {line}")

    state = load_state()
    state["person"] = person.as_dict()
    state["next_number"] = poa_source.next_number(person.doc_number)
    save_state(state)
    print(f"\n  Holat saqlandi: {STATE_PATH}")
    if person.missing():
        print("  DIQQAT: quyidagilar qo'lda kiritilishi kerak: "
              + ", ".join(person.missing()))
        print("  state.json ichidagi \"person\" bo'limini to'ldiring.")
    return 0


# --------------------------------------------------------------------------
# 3. Didox'dan namuna
# --------------------------------------------------------------------------

def cmd_fetch_sample(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    _print_header("Didox'dan namuna ishonchnoma")
    client = DidoxClient(cfg, dry_run=args.dry_run)
    if args.document_id:
        sample = client.get_document(args.document_id)
    else:
        listing = client.list_documents(
            doctype=cfg.get("didox", {}).get("doc_type_doverennost", ""),
            limit=1, owner=1)
        print(json.dumps(listing, ensure_ascii=False, indent=2)[:2000])
        print("\nRo'yxatdan hujjat ID'sini oling va qayta ishga tushiring:")
        print("  python run.py fetch-sample --id <DOCUMENT_ID>")
        return 0

    if isinstance(sample, dict) and sample.get("dry_run"):
        return 0

    m2.save_json(m2.sample_path(HERE), sample)
    print(f"Namuna saqlandi: {m2.sample_path(HERE)}")

    state = load_state()
    person = state.get("person", {})
    old_values = {
        "owner_tin": cfg.get("tin", ""),
        "owner_name": cfg.get("org_name", ""),
        "agent_tin": cfg.get("m2", {}).get("receiver_tin", ""),
        "agent_name": cfg.get("m2", {}).get("receiver_name", ""),
        "fio": person.get("fio", ""),
        "position": person.get("position", ""),
        "passport": person.get("passport", ""),
        "number": person.get("doc_number", ""),
    }
    field_map = m2.build_field_map(sample, old_values)
    field_map = m2.complete_field_map(sample, field_map)
    m2.save_json(m2.field_map_path(HERE), field_map)

    print(f"Maydon xaritasi saqlandi: {m2.field_map_path(HERE)}")
    for field_name, title in m2.FIELD_TITLES.items():
        paths = field_map.get(field_name) or []
        mark = "OK " if paths else "!! "
        print(f"  {mark}{title:<28} {', '.join(paths) if paths else 'topilmadi'}")
    print("\nTopilmagan maydonlar bo'lsa, field_map.json'ni qo'lda to'g'rilang.")
    return 0


# --------------------------------------------------------------------------
# 4. Payload qurish
# --------------------------------------------------------------------------

def cmd_remap(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    """Mahalliy namuna faylidan maydon xaritasini qayta quradi.

    Didox tokeni hali yo'q bo'lsa: eski ishonchnomani Didox veb-interfeysidan
    JSON qilib eksport qiling va templates/doverennost.sample.json ga qo'ying.
    """
    _print_header("Maydon xaritasi")
    path = args.file or m2.sample_path(HERE)
    if not os.path.exists(path):
        raise SystemExit(f"Namuna fayl topilmadi: {path}")
    sample = m2.load_json(path)
    if path != m2.sample_path(HERE):
        m2.save_json(m2.sample_path(HERE), sample)

    person = load_state().get("person", {})
    old_values = {
        "owner_tin": cfg.get("tin", ""),
        "owner_name": cfg.get("org_name", ""),
        "agent_tin": cfg.get("m2", {}).get("receiver_tin", ""),
        "agent_name": cfg.get("m2", {}).get("receiver_name", ""),
        "fio": person.get("fio", ""),
        "position": person.get("position", ""),
        "passport": person.get("passport", ""),
        "number": person.get("doc_number", ""),
    }
    field_map = m2.complete_field_map(sample, m2.build_field_map(sample, old_values))
    m2.save_json(m2.field_map_path(HERE), field_map)
    for field_name, title in m2.FIELD_TITLES.items():
        paths = field_map.get(field_name) or []
        mark = "OK " if paths else "!! "
        print(f"  {mark}{title:<28} {', '.join(paths) if paths else 'topilmadi'}")
    print(f"\nSaqlandi: {m2.field_map_path(HERE)}")
    return 0


def _require_sample() -> tuple[dict[str, Any], dict[str, list[str]]]:
    if not os.path.exists(m2.sample_path(HERE)):
        raise SystemExit(
            "Namuna yo'q. Avval ishga tushiring: python run.py fetch-sample --id <ID>"
        )
    sample = m2.load_json(m2.sample_path(HERE))
    field_map = (m2.load_json(m2.field_map_path(HERE))
                 if os.path.exists(m2.field_map_path(HERE)) else {})
    return sample, field_map


def cmd_build(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    _print_header("Yangi M-2 ishonchnoma")
    sample, field_map = _require_sample()
    state = load_state()
    person = state.get("person") or {}
    number = args.number or state.get("next_number") or ""
    if not number:
        raise SystemExit("Raqam aniqlanmadi. --number bilan ko'rsating yoki "
                         "avval `python run.py last` ni ishga tushiring.")

    values = m2.new_values(cfg, number)
    # Ishonchli shaxs ma'lumotlari eski hujjatdan o'zgarishsiz ko'chiriladi
    values.update({
        "fio": person.get("fio", ""),
        "position": person.get("position", ""),
        "passport": person.get("passport", ""),
    })
    values = m2.align_date_formats(sample, field_map, values)

    payload, applied = m2.apply_values(sample, field_map, values)

    out_dir = cfg.get("out_dir") or os.path.join(HERE, "out")
    stamp = dt.date.today().isoformat()
    out_path = os.path.join(out_dir, f"m2_{number}_{stamp}.json")
    m2.save_json(out_path, payload)

    print("Almashtirilgan maydonlar:")
    for line in applied:
        print(f"  · {line}")
    print("\nYangi hujjat mazmuni:")
    print(m2.summarize(payload, field_map))
    print(f"\nSaqlandi: {out_path}")
    print("\nTekshiring. Yuborish uchun:")
    print(f"  python run.py send --file \"{out_path}\" --confirm")

    state["last_build"] = out_path
    save_state(state)
    return 0


# --------------------------------------------------------------------------
# 5. Yuborish
# --------------------------------------------------------------------------

def cmd_send(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    _print_header("Didox'ga yuborish")
    state = load_state()
    path = args.file or state.get("last_build")
    if not path or not os.path.exists(path):
        raise SystemExit("Yuboriladigan fayl topilmadi. Avval `python run.py build`.")
    payload = m2.load_json(path)

    if not args.confirm and not args.dry_run:
        print(f"Fayl: {path}")
        sample, field_map = _require_sample()
        print(m2.summarize(payload, field_map))
        print("\nTasdiqlash uchun --confirm qo'shing (yoki --dry-run bilan sinang).")
        return 1

    client = DidoxClient(cfg, dry_run=args.dry_run)
    created = client.create_document(payload)
    print(json.dumps(created, ensure_ascii=False, indent=2)[:2000])
    if args.dry_run:
        return 0

    document_id = _extract_id(created)
    if not document_id:
        print("Javobdan hujjat ID'si topilmadi — imzolash bosqichi o'tkazib "
              "yuborildi. ID'ni qo'lda berib: python run.py sign --id <ID>")
        return 0
    state["last_document_id"] = document_id
    save_state(state)
    print(f"Hujjat yaratildi: {document_id}")
    if args.sign:
        return _sign(cfg, document_id, created)
    print("Imzolash uchun: python run.py sign --id " + document_id)
    return 0


def _extract_id(response: Any) -> str:
    if not isinstance(response, dict):
        return ""
    for key in ("documentId", "document_id", "id", "doc_id", "uuid"):
        value = response.get(key)
        if value:
            return str(value)
    data = response.get("data")
    if isinstance(data, dict):
        return _extract_id(data)
    return ""


def cmd_sign(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    document_id = args.document_id or load_state().get("last_document_id")
    if not document_id:
        raise SystemExit("Hujjat ID'si ko'rsatilmagan (--id).")
    return _sign(cfg, document_id, None)


def _sign(cfg: dict[str, Any], document_id: str, created: Any) -> int:
    """E-IMZO bilan imzolab, imzoni Didox'ga yuboradi.

    Parolni E-IMZO ilovasining o'zi so'raydi — bu skript parolni ko'rmaydi.
    """
    import base64

    _print_header("Imzolash")
    from keys_report import filter_by_tin
    from eimzo import collect_certificates

    certs, notes = collect_certificates(cfg)
    matched = filter_by_tin(certs, cfg.get("tin", ""))
    if not matched:
        for note in notes:
            print(f"  · {note}")
        print("Imzolash uchun kalit topilmadi.")
        return 1
    cert = matched[0]
    print(f"Kalit: {cert.cn} ({cert.file_name})")

    to_sign = json.dumps(created or {"documentId": document_id},
                         ensure_ascii=False, separators=(",", ":"))
    data_b64 = base64.b64encode(to_sign.encode("utf-8")).decode("ascii")

    eimzo_cfg = cfg.get("eimzo", {})
    try:
        with Capiws(eimzo_cfg.get("ws_url", "ws://127.0.0.1:64646/service/cryptapi"),
                    int(eimzo_cfg.get("timeout", 20)),
                    eimzo_cfg.get("apikey_arguments")) as ws:
            print("E-IMZO oynasida parolni kiriting...")
            key_id = ws.load_key(cert)
            pkcs7 = ws.create_pkcs7(data_b64, key_id)
    except EimzoError as exc:
        print(f"Imzolash bajarilmadi: {exc}")
        return 1

    client = DidoxClient(cfg)
    result = client.sign_document(document_id, pkcs7)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="config.json yo'li")
    parser.add_argument("--dry-run", action="store_true",
                        help="Didox'ga so'rov yubormaydi, faqat ko'rsatadi")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("keys", help="Sertifikatlarni o'qib kalitlar.md yozadi")
    subparsers.add_parser("last", help="Oxirgi ishonchnomani o'qiydi")

    fetch = subparsers.add_parser("fetch-sample", help="Didox'dan namuna oladi")
    fetch.add_argument("--id", dest="document_id", help="Namuna hujjat ID'si")

    remap = subparsers.add_parser("remap",
                                  help="Mahalliy namunadan maydon xaritasini yasaydi")
    remap.add_argument("--file", help="Namuna JSON fayl yo'li")

    build = subparsers.add_parser("build", help="Yangi M-2 payload'ini yasaydi")
    build.add_argument("--number", help="Ishonchnoma raqami (avtomatik: oldingisi+1)")

    send = subparsers.add_parser("send", help="Didox'ga yuboradi")
    send.add_argument("--file", help="Yuboriladigan JSON fayl")
    send.add_argument("--confirm", action="store_true", help="Tasdiqlash")
    send.add_argument("--sign", action="store_true", help="Yuborgach imzolaydi")

    sign = subparsers.add_parser("sign", help="Mavjud hujjatni imzolaydi")
    sign.add_argument("--id", dest="document_id", help="Hujjat ID'si")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)

    handlers = {
        "keys": cmd_keys, "last": cmd_last, "fetch-sample": cmd_fetch_sample,
        "remap": cmd_remap, "build": cmd_build, "send": cmd_send,
        "sign": cmd_sign,
    }
    for name in ("dry_run", "document_id", "number", "file", "confirm", "sign"):
        if not hasattr(args, name):
            setattr(args, name, None)
    return handlers[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
