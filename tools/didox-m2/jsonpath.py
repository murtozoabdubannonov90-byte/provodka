"""JSON ichida yo'l bo'yicha o'qish/yozish va qiymat bo'yicha qidirish."""

from __future__ import annotations

from typing import Any, Iterator

Path = tuple[Any, ...]


def walk(node: Any, prefix: Path = ()) -> Iterator[tuple[Path, Any]]:
    """Barcha skalyar qiymatlarni (yo'l, qiymat) ko'rinishida qaytaradi."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, prefix + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, prefix + (index,))
    else:
        yield prefix, node


def get_path(node: Any, path: Path) -> Any:
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return None
    return node


def set_path(node: Any, path: Path, value: Any) -> bool:
    if not path:
        return False
    for step in path[:-1]:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError):
            return False
    last = path[-1]
    try:
        node[last] = value
    except (KeyError, IndexError, TypeError):
        return False
    return True


def _normalize(value: Any) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def find_paths_by_value(node: Any, needle: str, partial: bool = True) -> list[Path]:
    """Qiymati `needle` ga teng (yoki uni o'z ichiga olgan) yo'llarni topadi."""
    target = _normalize(needle)
    if not target:
        return []
    if len(target) < 3:
        partial = False  # qisqa qiymatlar (masalan hujjat raqami) faqat aniq mos
    matches: list[Path] = []
    for path, value in walk(node):
        if value is None or isinstance(value, bool):
            continue
        current = _normalize(value)
        if not current:
            continue
        if current == target or (partial and len(current) < 200 and target in current):
            matches.append(path)
    return matches


def path_to_str(path: Path) -> str:
    return ".".join(str(step) for step in path)


def str_to_path(text: str) -> Path:
    return tuple(int(step) if step.isdigit() else step for step in text.split("."))
