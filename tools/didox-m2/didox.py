"""Didox API klienti.

Endpoint yo'llari va autentifikatsiya `config.json` dan olinadi, chunki
ular hujjatlarda o'zgarib turadi (api-docs.didox.uz). Har bir so'rovni
`--dry-run` bilan yubormasdan ko'rish mumkin.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_TIMEOUT = 60


class DidoxError(RuntimeError):
    pass


class DidoxClient:
    def __init__(self, cfg: dict[str, Any], dry_run: bool = False):
        didox_cfg = cfg.get("didox", {})
        self.base_url = didox_cfg.get("base_url", "").rstrip("/")
        self.token = didox_cfg.get("token", "")
        self.endpoints = didox_cfg.get("endpoints", {})
        self.extra_headers = didox_cfg.get("extra_headers", {}) or {}
        self.tin = cfg.get("tin", "")
        self.dry_run = dry_run
        self._session = None

    # ---------------------------------------------------------------- utils
    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            token = self.token
            headers["Authorization"] = (
                token if token.lower().startswith("bearer ") else f"Bearer {token}"
            )
        if self.tin:
            headers.setdefault("tin", self.tin)
        headers.update(self.extra_headers)
        return headers

    def _url(self, name: str, **fmt: Any) -> str:
        template = self.endpoints.get(name)
        if not template:
            raise DidoxError(
                f"config.json -> didox.endpoints.{name} to'ldirilmagan. "
                "Aniq yo'lni api-docs.didox.uz dan oling."
            )
        return self.base_url + template.format(**fmt)

    def _request(self, method: str, url: str, *, params: dict | None = None,
                 payload: Any = None) -> Any:
        if self.dry_run:
            print(f"[dry-run] {method} {url}")
            if params:
                print(f"[dry-run] params: {params}")
            if payload is not None:
                body = json.dumps(payload, ensure_ascii=False, indent=2)
                print("[dry-run] body:\n" + body)
            return {"dry_run": True}

        if not self.base_url:
            raise DidoxError("config.json -> didox.base_url to'ldirilmagan.")
        if not self.token:
            raise DidoxError(
                "config.json -> didox.token bo'sh. Partner token'ni Didox "
                "akkaunt menejeridan oling (@Didox_account)."
            )

        import requests

        if self._session is None:
            self._session = requests.Session()
        response = self._session.request(
            method, url, headers=self._headers(), params=params,
            json=payload, timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code >= 400:
            raise DidoxError(
                f"Didox {method} {url} -> {response.status_code}: {response.text[:800]}"
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    # ------------------------------------------------------------- methods
    def list_documents(self, **params: Any) -> Any:
        return self._request("GET", self._url("documents"), params=params or None)

    def get_document(self, document_id: str, owner: int = 0) -> Any:
        return self._request("GET", self._url("document_by_id", id=document_id),
                             params={"owner": owner})

    def create_document(self, payload: Any) -> Any:
        return self._request("POST", self._url("create"), payload=payload)

    def sign_document(self, document_id: str, pkcs7_b64: str) -> Any:
        return self._request("POST", self._url("sign", id=document_id),
                             payload={"sign": pkcs7_b64})
