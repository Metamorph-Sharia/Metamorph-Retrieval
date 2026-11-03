"""The regulation retrieval service's answers, as it actually sends them."""

from __future__ import annotations

import json
from typing import Any

import httpx

PUBLISHED_AT = "2026-10-22T14:05:00+00:00"
BASE = "doc:ojk:pojk:2024:40"

MANIFEST: dict[str, Any] = {
    "name": "regulation-retrieval",
    "version": "0.1.0",
    "namespaces": ["doc"],
    "kinds": ["law", "regulation", "implementing_rule", "fatwa", "guideline", "circular", "explanatory"],
    "links": False,
    "tools": [
        {
            "name": "find_provision",
            "version": "0.1",
            "description": "Resolve a legal citation to its exact provision.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "citation": {"type": "string", "minLength": 4, "maxLength": 400},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8},
                },
                "required": ["citation"],
                "additionalProperties": False,
            },
            "output_schema": {"type": "object"},
        }
    ],
    "index_version": "bench_emb_r2p_full_bge_m3",
    "data_as_of": PUBLISHED_AT,
}


def evidence(address: str, wording: str) -> dict[str, Any]:
    return {
        "ref": f"{BASE}#{address}",
        "kind": "regulation",
        "citation": f"POJK 40/2024, {address}",
        "title": "LAYANAN PENDANAAN BERSAMA BERBASIS TEKNOLOGI INFORMASI",
        "legal_force": "binding",
        "qualifiers": {
            "status": "partly_revoked",
            "valid_from": "2024-12-27",
            "valid_to": None,
            "under_review": False,
            "provisional": False,
            "as_of": None,
        },
        "published_on": "2024-12-27",
        "url": None,
        "body": {"type": "text", "wording": wording, "pages": None},
        "provenance": {
            "provider": "regulation-retrieval",
            "index_version": "bench_emb_r2p_full_bge_m3",
            "source_published_at": PUBLISHED_AT,
        },
    }


HELD = {
    "pasal-137/ayat-3": evidence("pasal-137/ayat-3", "Batas maksimum pemberian pendanaan adalah Rp 4.000.000.000."),
    "pasal-137/ayat-4": evidence("pasal-137/ayat-4", "Batas maksimum ditetapkan berdasarkan kualitas pendanaan."),
}


def hit(rank: int, address: str, score: float) -> dict[str, Any]:
    return {"rank": rank, "score": score, "matched_by": ["semantic"], "evidence": HELD[address]}


def handle(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "GET" and path == "/manifest":
        return _json(MANIFEST)
    if request.method == "POST" and path == "/tools/search_regulations":
        body = json.loads(request.content or b"{}")
        limit = int(body.get("limit", 8))
        items = [hit(1, "pasal-137/ayat-3", 0.83), hit(2, "pasal-137/ayat-4", 0.79)][:limit]
        return _json({"items": items, "cursor": None, "empty_reason": None, "warnings": []})
    if request.method == "POST" and path == "/tools/read_regulation":
        body = json.loads(request.content or b"{}")
        _, _, address = str(body.get("ref", "")).partition("#")
        if address in HELD:
            return _json(HELD[address])
        return _json({"error": "unknown_ref", "message": f"{body.get('ref')}: not published"}, 404)
    if request.method == "POST" and path == "/tools/find_provision":
        return _json({"items": [HELD["pasal-137/ayat-3"]], "cursor": None, "empty_reason": None, "warnings": []})
    return _json({"error": "unknown_tool", "message": f"no tool at {path}"}, 404)


def client() -> httpx.Client:
    return httpx.Client(base_url="http://rag", transport=httpx.MockTransport(handle))


def _json(body: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=body)
