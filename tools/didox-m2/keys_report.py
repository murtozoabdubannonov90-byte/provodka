"""DSKEYS sertifikatlarini o'qib `kalitlar.md` hisobotini yozadi.

Faqat ochiq sertifikat ma'lumotlari o'qiladi: F.I.Sh., berilgan sana,
tugash sanasi, fayl nomi va to'liq yo'l. Parol so'ralmaydi va saqlanmaydi.
"""

from __future__ import annotations

import os
from typing import Any

from eimzo import CertInfo, collect_certificates


def filter_by_tin(certs: list[CertInfo], tin: str) -> list[CertInfo]:
    tin = (tin or "").strip()
    if not tin:
        return certs
    exact = [c for c in certs if c.tin == tin]
    if exact:
        return exact
    # STIR sertifikatdan o'qilmagan bo'lsa - fayl nomi/yo'li bo'yicha qidiramiz
    return [c for c in certs
            if tin in c.file_name or tin in c.full_path or tin in c.alias]


def _row(label: str, value: str) -> str:
    return f"| {label} | {value or '—'} |\n"


def render_markdown(certs: list[CertInfo], tin: str, org_name: str,
                    notes: list[str], keys_dir: str) -> str:
    lines = [
        "# Kalitlar (sertifikatlar) hisoboti\n\n",
        f"- **Qidirilgan STIR:** {tin} ({org_name})\n",
        f"- **Kalitlar papkasi:** `{keys_dir}`\n",
        f"- **Topilgan mos sertifikat:** {len(certs)} ta\n\n",
        "> Parol so'ralmadi va hech qayerga yozilmadi — faqat ochiq "
        "sertifikat maydonlari o'qildi.\n\n",
    ]

    if not certs:
        lines.append("## Natija\n\nMos sertifikat topilmadi.\n\n")
    for index, cert in enumerate(certs, start=1):
        lines.append(f"## {index}. {cert.cn or cert.file_name}\n\n")
        lines.append("| Maydon | Qiymat |\n|---|---|\n")
        lines.append(_row("Kalit egasining F.I.Sh.", cert.cn))
        lines.append(_row("Berilgan sana", cert.valid_from))
        lines.append(_row("Tugash sanasi", cert.valid_to))
        lines.append(_row("Fayl nomi", f"`{cert.file_name}`" if cert.file_name else ""))
        lines.append(_row("To'liq yo'l", f"`{cert.full_path}`" if cert.full_path else ""))
        lines.append("\n")
        extra = [
            ("STIR", cert.tin), ("Tashkilot", cert.org),
            ("Lavozim", cert.position), ("Seriya raqami", cert.serial),
        ]
        shown = [(k, v) for k, v in extra if v]
        if shown:
            lines.append("<details><summary>Qo'shimcha maydonlar</summary>\n\n")
            lines.append("| Maydon | Qiymat |\n|---|---|\n")
            lines.extend(_row(k, v) for k, v in shown)
            lines.append("\n</details>\n\n")

    if notes:
        lines.append("---\n\n### Izohlar\n\n")
        lines.extend(f"- {note}\n" for note in notes)
    return "".join(lines)


def build_report(cfg: dict[str, Any]) -> tuple[str, list[CertInfo]]:
    all_certs, notes = collect_certificates(cfg)
    tin = cfg.get("tin", "")
    matched = filter_by_tin(all_certs, tin)
    if not matched and all_certs:
        notes.append(
            f"STIR {tin} bo'yicha moslik yo'q. Jami {len(all_certs)} ta kalit ko'rildi: "
            + ", ".join(sorted({c.file_name for c in all_certs if c.file_name})[:20])
        )
    markdown = render_markdown(matched, tin, cfg.get("org_name", ""), notes,
                               cfg.get("keys_dir", ""))
    return markdown, matched


def write_report(cfg: dict[str, Any]) -> tuple[str, list[CertInfo]]:
    markdown, matched = build_report(cfg)
    target = cfg.get("keys_md") or os.path.join(os.getcwd(), "kalitlar.md")
    parent = os.path.dirname(os.path.abspath(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    return target, matched
