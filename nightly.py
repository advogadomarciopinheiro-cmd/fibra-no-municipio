#!/usr/bin/env python3
"""Regenerate processed data (optional) and publish ONE new useful page.

Idempotent: skips municipalities already in published.json. Safe to run twice;
the second run publishes the next city in the queue, not a duplicate.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from scripts.paths import DATA_PROCESSED  # noqa: E402
from scripts.build import build, mes_extenso, fmt_int  # noqa: E402

TZ = ZoneInfo("America/Sao_Paulo")


def now_br() -> str:
    return datetime.now(TZ).strftime("%d/%m/%Y %H:%M") + " (horário de Brasília, UTC-3)"


def log(event: dict) -> None:
    path = DATA_PROCESSED / "nightly_log.jsonl"
    event = dict(event)
    event.setdefault("quando", now_br())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    print("log:", json.dumps(event, ensure_ascii=False))


def load_json(name: str):
    return json.loads((DATA_PROCESSED / name).read_text(encoding="utf-8"))


def save_json(name: str, obj) -> None:
    (DATA_PROCESSED / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def next_city(published: list[str], queue: list[str], munics: dict) -> dict | None:
    already = set(published)
    for ibge in queue:
        if ibge in already:
            continue
        city = munics.get(ibge)
        if not city:
            continue
        if not city.get("acessos_fibra"):
            continue
        return city
    return None


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if "--refresh" in argv:
        from scripts.fetch_and_process import main as fetch_main

        print("Atualizando dados oficiais…")
        fetch_main(["--refresh"] if "--refresh" in argv else [])

    if not (DATA_PROCESSED / "municipios.json").exists():
        print("Base processada ausente. Rode: python3 scripts/fetch_and_process.py")
        return 1

    published_doc = load_json("published.json")
    queue_doc = load_json("queue.json")
    munics = load_json("municipios.json")
    published = list(published_doc.get("ibge") or [])
    queue = list(queue_doc.get("ibge") or [])

    city = next_city(published, queue, munics)
    if not city:
        log({
            "tipo": "fila_vazia",
            "titulo": "Nenhum município novo na fila",
            "resumo": "Todas as cidades com fibra da fila atual já foram publicadas. Nada foi duplicado.",
            "href": "diario/",
        })
        build()
        return 0

    published.append(city["ibge"])
    queue_doc["ibge"] = [c for c in queue if c != city["ibge"] and c not in published]
    save_json("published.json", {"ibge": published})
    save_json("queue.json", queue_doc)

    resumo = (
        f"{city['nome']} ({city['uf']}): {fmt_int(city['acessos_fibra_pf_internet'])} "
        f"acessos de internet em fibra para pessoa física e {fmt_int(city['acessos_fibra'])} "
        f"acessos totais em fibra, mês {mes_extenso(city['mes_referencia'])}."
    )
    href = f"municipio/{city['slug']}/"
    log({
        "tipo": "municipio",
        "ibge": city["ibge"],
        "slug": city["slug"],
        "titulo": f"Internet fibra em {city['nome']} ({city['uf']})",
        "resumo": resumo,
        "href": href,
    })
    summary = build()
    print(f"Nova página: site/{href}")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
