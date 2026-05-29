"""
Build anchor texts from AGROVOC via SPARQL.

This script is intended as an offline data-generation step for the agriculture
relevance pipeline. It produces multilingual anchor rows that can later be
converted into runtime lexicon entries and bucket centroids.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List

import requests

SPARQL_ENDPOINT = "https://agrovoc.fao.org/sparql"
DEFAULT_LANGS = ("en", "fr", "de", "es", "it", "el", "nl")
PAGE_SIZE = 1500


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data_model/build/agriculture/agrovoc_anchor_texts.jsonl")
    p.add_argument("--limit", type=int, default=20000)
    p.add_argument("--langs", nargs="*", default=list(DEFAULT_LANGS))
    return p.parse_args()


def sparql_select(query: str, timeout_s: int = 60) -> List[Dict[str, str]]:
    headers = {"Accept": "application/sparql-results+json"}
    response = requests.post(
        SPARQL_ENDPOINT,
        data={"query": query},
        headers=headers,
        timeout=timeout_s,
    )
    response.raise_for_status()
    payload = response.json()
    rows: List[Dict[str, str]] = []
    for binding in payload.get("results", {}).get("bindings", []):
        rows.append({k: v.get("value", "") for k, v in binding.items()})
    return rows


def _lang_clause(langs: List[str]) -> str:
    return " || ".join([f'lang(?label) = "{lang}"' for lang in langs])


def build_anchor_text(pref: str, alts: List[str], note: str, broader: List[str], labels: List[str]) -> str:
    parts = [f"Concept: {pref}."]
    if alts:
        parts.append("Alternative labels: " + "; ".join(sorted(set(alts[:20]))) + ".")
    if broader:
        parts.append("Broader terms: " + "; ".join(sorted(set(broader[:12]))) + ".")
    if labels:
        parts.append("Multilingual labels: " + "; ".join(sorted(set(labels[:24]))) + ".")
    if note:
        parts.append("Definition: " + note.strip())
    return " ".join(parts).strip()


def main() -> None:
    args = parse_args()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    offset = 0
    written = 0
    label_filter = _lang_clause(args.langs)

    with out_path.open("w", encoding="utf-8") as fh:
        while True:
            query = f"""
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT ?c
                   (SAMPLE(STR(?prefEn)) AS ?pref)
                   (GROUP_CONCAT(DISTINCT STR(?altEn); separator="||") AS ?alts)
                   (SAMPLE(STR(?scopeNoteLit)) AS ?scopeNote)
                   (SAMPLE(STR(?defLit)) AS ?definition)
                   (GROUP_CONCAT(DISTINCT STR(?bprefEn); separator="||") AS ?broader)
                   (GROUP_CONCAT(DISTINCT CONCAT(LANG(?mlabel), "::", STR(?mlabel)); separator="||") AS ?labels)
            WHERE {{
              ?c a skos:Concept ;
                 skos:prefLabel ?prefEn .
              FILTER(lang(?prefEn) = "en")

              OPTIONAL {{
                ?c skos:altLabel ?altEn .
                FILTER(lang(?altEn) = "en")
              }}
              OPTIONAL {{
                ?c skos:prefLabel ?mlabel .
                FILTER({label_filter})
              }}
              OPTIONAL {{
                ?c skos:scopeNote ?scopeNoteLit .
                FILTER(lang(?scopeNoteLit) = "en")
              }}
              OPTIONAL {{
                ?c skos:definition ?defLit .
                FILTER(lang(?defLit) = "en")
              }}
              OPTIONAL {{
                ?c skos:broader ?b .
                ?b skos:prefLabel ?bprefEn .
                FILTER(lang(?bprefEn) = "en")
              }}
            }}
            GROUP BY ?c
            ORDER BY ?c
            LIMIT {PAGE_SIZE}
            OFFSET {offset}
            """
            rows = sparql_select(query)
            if not rows:
                break

            for row in rows:
                pref = row.get("pref", "").strip()
                if not pref:
                    continue
                alts = [x.strip() for x in row.get("alts", "").split("||") if x.strip()]
                note = (row.get("scopeNote") or row.get("definition") or "").strip()
                broader = [x.strip() for x in row.get("broader", "").split("||") if x.strip()]
                labels = [x.strip() for x in row.get("labels", "").split("||") if x.strip()]
                anchor_text = build_anchor_text(pref, alts, note, broader, labels)
                fh.write(json.dumps({
                    "uri": row.get("c", ""),
                    "source": "agrovoc",
                    "prefLabel_en": pref,
                    "altLabels_en": alts,
                    "broader_prefLabels_en": broader,
                    "note_en": note,
                    "multilingual_labels": labels,
                    "anchor_text": anchor_text,
                }, ensure_ascii=False) + "\n")
                written += 1
                if args.limit and written >= args.limit:
                    break

            print(f"[AGROVOC] wrote {written} rows (offset={offset})")
            if args.limit and written >= args.limit:
                break
            offset += PAGE_SIZE
            time.sleep(0.2)

    print(f"[OK] Wrote {out_path}")


if __name__ == "__main__":
    main()
