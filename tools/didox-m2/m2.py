"""M-2 ishonchnoma payload'ini eski hujjat namunasi asosida quradi.

Didox JSON sxemasi taxmin qilinmaydi: u sizning akkauntingizdan yuklab
olingan haqiqiy ishonchnomadan (`templates/doverennost.sample.json`) olinadi.
Maydonlar shu namunadagi eski qiymatlar bo'yicha topiladi va almashtiriladi.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
from typing import Any

from jsonpath import (Path, find_paths_by_value, get_path, path_to_str,
                      set_path, str_to_path, walk)

# Mantiqiy maydon -> to'liq JSON yo'lidagi ishorat so'zlar (zaxira usul).
# Yo'l normallashtiriladi: kichik harf, nuqta/pastki chiziq va indekslar olib
# tashlanadi. Masalan "doverennost.owner.name" -> "doverennostownername".
KEY_HINTS: dict[str, tuple[str, ...]] = {
    "owner_tin": ("ownertin", "sellertin", "fromtin", "ownerinn", "doverennosttin"),
    "owner_name": ("ownername", "sellername", "fromname", "ownercompany"),
    "agent_tin": ("agenttin", "buyertin", "totin", "contractortin", "receivertin"),
    "agent_name": ("agentname", "buyername", "toname", "contractorname",
                   "receivername"),
    "number": ("doverennostno", "docno", "documentno", "docnumber", "documentnumber"),
    "date": ("doverennostdate", "docdate", "documentdate"),
    "expire_date": ("expiredate", "dateofexpire", "validuntil", "enddate",
                    "dateexpire"),
    "fio": ("personfio", "agentfio", "trustedfio", "fio", "personname"),
    "position": ("position", "lavozim", "dolzhnost", "personpost"),
    "passport": ("passport", "pasport", "personseriya", "persondocument"),
    "goods": ("productsname", "productname", "goodsname", "itemsname", "tovar"),
}

FIELD_TITLES = {
    "owner_tin": "Beruvchi STIR",
    "owner_name": "Beruvchi nomi",
    "agent_tin": "Oluvchi STIR",
    "agent_name": "Oluvchi nomi",
    "number": "Ishonchnoma raqami",
    "date": "Sana",
    "expire_date": "Amal qilish muddati",
    "fio": "Ishonchli shaxs F.I.Sh.",
    "position": "Ishonchli shaxs lavozimi",
    "passport": "Pasport seriya-raqami",
    "goods": "Tovar",
}


# --------------------------------------------------------------------------
# Maydon xaritasi
# --------------------------------------------------------------------------

def build_field_map(sample: dict[str, Any],
                    old_values: dict[str, str]) -> dict[str, list[str]]:
    """Namunadagi eski qiymatlar bo'yicha maydon -> JSON yo'llar xaritasi."""
    field_map: dict[str, list[str]] = {}
    for field_name, old_value in old_values.items():
        if not old_value:
            continue
        paths = find_paths_by_value(sample, str(old_value))
        if paths:
            field_map[field_name] = [path_to_str(p) for p in paths]
    return field_map


def _normalize_path(path: Path) -> str:
    parts = [str(step).lower() for step in path if not isinstance(step, int)]
    return "".join(part.replace("_", "").replace("-", "") for part in parts)


def heuristic_paths(sample: dict[str, Any], field_name: str) -> list[str]:
    """To'liq yo'l bo'yicha taxminiy mosliklar (eski qiymat topilmaganda)."""
    hints = KEY_HINTS.get(field_name, ())
    found: list[tuple[int, str]] = []
    for path, value in walk(sample):
        if isinstance(value, (dict, list)):
            continue
        flat = _normalize_path(path)
        for rank, hint in enumerate(hints):
            if hint in flat:
                found.append((rank, path_to_str(path)))
                break
    found.sort()
    return [p for _rank, p in found]


def complete_field_map(sample: dict[str, Any],
                       field_map: dict[str, list[str]]) -> dict[str, list[str]]:
    """Topilmagan maydonlar uchun yo'l nomi bo'yicha taxmin qo'shadi.

    Bir yo'l ikki xil maydonga biriktirilmaydi.
    """
    result = {name: list(paths) for name, paths in field_map.items() if paths}
    claimed = {p for paths in result.values() for p in paths}
    for field_name in FIELD_TITLES:
        if result.get(field_name):
            continue
        for guess in heuristic_paths(sample, field_name):
            if guess not in claimed:
                result[field_name] = [guess]
                claimed.add(guess)
                break
    return result


# --------------------------------------------------------------------------
# Qurish
# --------------------------------------------------------------------------

def new_values(cfg: dict[str, Any], person_number: str,
               today: dt.date | None = None) -> dict[str, str]:
    today = today or dt.date.today()
    m2_cfg = cfg.get("m2", {})
    days = int(m2_cfg.get("valid_days", 30))
    return {
        "owner_tin": cfg.get("tin", ""),
        "owner_name": cfg.get("org_name", ""),
        "agent_tin": m2_cfg.get("receiver_tin", ""),
        "agent_name": m2_cfg.get("receiver_name", ""),
        "number": person_number,
        "date": today.isoformat(),
        "expire_date": (today + dt.timedelta(days=days)).isoformat(),
        "goods": m2_cfg.get("goods_text", ""),
    }


def apply_values(sample: dict[str, Any], field_map: dict[str, list[str]],
                 values: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Namunadan yangi payload yasaydi. Ishonchli shaxs maydonlari tegilmaydi
    agar `values` ichida bo'lmasa."""
    payload = copy.deepcopy(sample)
    applied: list[str] = []
    for field_name, value in values.items():
        if value in (None, ""):
            continue
        for raw_path in field_map.get(field_name, []):
            path = str_to_path(raw_path)
            old = get_path(payload, path)
            new = _match_type(old, value)
            if set_path(payload, path, new):
                applied.append(f"{FIELD_TITLES.get(field_name, field_name)}: "
                               f"{raw_path} = {new!r} (eski: {old!r})")
    return payload, applied


def _match_type(old: Any, value: str) -> Any:
    """Yangi qiymat turini eskisiga moslashtiradi (raqam bo'lsa raqam qiladi)."""
    if isinstance(old, bool) or old is None:
        return value
    if isinstance(old, int) and str(value).isdigit():
        return int(value)
    if isinstance(old, float):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def date_format_of(sample_value: Any) -> str | None:
    """Namunadagi sana formatini aniqlaydi (ISO yoki DD.MM.YYYY)."""
    text = str(sample_value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return "%Y-%m-%d"
    if len(text) >= 10 and text[2] == "." and text[5] == ".":
        return "%d.%m.%Y"
    return None


def align_date_formats(sample: dict[str, Any], field_map: dict[str, list[str]],
                       values: dict[str, str]) -> dict[str, str]:
    """Sana maydonlarini namunadagi formatga keltiradi."""
    out = dict(values)
    for field_name in ("date", "expire_date"):
        paths = field_map.get(field_name) or []
        if not paths or not out.get(field_name):
            continue
        fmt = date_format_of(get_path(sample, str_to_path(paths[0])))
        if fmt and fmt != "%Y-%m-%d":
            parsed = dt.date.fromisoformat(out[field_name])
            out[field_name] = parsed.strftime(fmt)
    return out


# --------------------------------------------------------------------------
# Fayl bilan ishlash
# --------------------------------------------------------------------------

def template_dir(base: str | None = None) -> str:
    return os.path.join(base or os.path.dirname(os.path.abspath(__file__)), "templates")


def sample_path(base: str | None = None) -> str:
    return os.path.join(template_dir(base), "doverennost.sample.json")


def field_map_path(base: str | None = None) -> str:
    return os.path.join(template_dir(base), "field_map.json")


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def summarize(payload: dict[str, Any], field_map: dict[str, list[str]]) -> str:
    """Payload'dagi asosiy maydonlarni odam o'qiydigan ko'rinishda beradi."""
    rows = []
    for field_name, title in FIELD_TITLES.items():
        paths = field_map.get(field_name) or []
        value = get_path(payload, str_to_path(paths[0])) if paths else None
        rows.append(f"  {title:<28} {value if value not in (None, '') else '—'}")
    return "\n".join(rows)
