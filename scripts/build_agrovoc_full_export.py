"""
Export a broad AGROVOC concept dump via SPARQL.

This script is intentionally broad: it fetches all concepts reachable from the
endpoint paging loop rather than pre-filtering to a small seed list. The output
is a reusable full-concept store for downstream builders:

- semantic anchor generation
- runtime lexicon generation with filtering/overrides
- offline analysis and review
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List

import requests
from requests import Response

SPARQL_ENDPOINT = "https://agrovoc.fao.org/sparql"
DEFAULT_LANGS = ("en", "fr", "de", "es", "it", "el", "nl")
PAGE_SIZE = 250
MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
DETAIL_BATCH_SIZE = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data_model/build/agriculture/agrovoc_full_export.jsonl")
    parser.add_argument("--limit", type=int, default=0, help="0 means no explicit cap")
    parser.add_argument("--langs", nargs="*", default=list(DEFAULT_LANGS))
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--offset", type=int, default=0, help="Resume from this SPARQL offset")
    parser.add_argument("--max-retries", type=int, default=MAX_RETRIES)
    parser.add_argument("--detail-batch-size", type=int, default=DETAIL_BATCH_SIZE)
    parser.add_argument(
        "--checkpoint",
        default="data_model/build/agriculture/agrovoc_full_export.checkpoint.json",
        help="Checkpoint file storing the latest completed offset and row count",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the checkpoint file and append to the existing output if present",
    )
    return parser.parse_args()


def _raise_with_context(response: Response, query: str) -> None:
    if response.status_code >= 400:
        print("---- SPARQL query (first 1000 chars) ----")
        print(query[:1000])
        print("---- Response text (first 1000 chars) ----")
        print(response.text[:1000])
    response.raise_for_status()


def sparql_select(query: str, *, timeout_s: int = 60, max_retries: int = MAX_RETRIES) -> List[Dict[str, str]]:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                SPARQL_ENDPOINT,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=timeout_s,
            )
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                time.sleep(min(20.0, 1.5 * attempt))
                continue
            _raise_with_context(response, query)
            payload = response.json()
            return [
                {k: v.get("value", "") for k, v in row.items()}
                for row in payload.get("results", {}).get("bindings", [])
            ]
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            time.sleep(min(20.0, 1.5 * attempt))
    assert last_exc is not None
    raise last_exc


def _lang_clause(var_name: str, langs: List[str]) -> str:
    return " || ".join([f'lang(?{var_name}) = "{lang}"' for lang in langs])


def _split_concat(raw: str) -> List[str]:
    return [item.strip() for item in (raw or "").split("||") if item.strip()]


def _paged_concepts_query(*, limit: int, offset: int) -> str:
    return f"""
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?c (SAMPLE(STR(?prefEn)) AS ?pref)
    WHERE {{
      ?c a skos:Concept ;
         skos:prefLabel ?prefEn .
      FILTER(lang(?prefEn) = "en")
    }}
    GROUP BY ?c
    ORDER BY ?c
    LIMIT {limit}
    OFFSET {offset}
    """


def _detail_query(*, uris: List[str], langs: List[str]) -> str:
    uri_values = " ".join(f"<{uri}>" for uri in uris)
    pref_lang_filter = _lang_clause("prefLang", langs)
    alt_lang_filter = _lang_clause("altLang", langs)
    return f"""
    PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
    SELECT ?c
           (SAMPLE(STR(?prefEn)) AS ?pref)
           (GROUP_CONCAT(DISTINCT STR(?altEn); separator="||") AS ?alts_en)
           (GROUP_CONCAT(DISTINCT CONCAT(LANG(?prefLang), "::", STR(?prefLang)); separator="||") AS ?pref_labels)
           (GROUP_CONCAT(DISTINCT CONCAT(LANG(?altLang), "::", STR(?altLang)); separator="||") AS ?alt_labels)
           (SAMPLE(STR(?scopeNoteLit)) AS ?scopeNote)
           (SAMPLE(STR(?defLit)) AS ?definition)
           (GROUP_CONCAT(DISTINCT STR(?bprefEn); separator="||") AS ?broader_en)
    WHERE {{
      VALUES ?c {{ {uri_values} }}
      ?c skos:prefLabel ?prefEn .
      FILTER(lang(?prefEn) = "en")

      OPTIONAL {{
        ?c skos:altLabel ?altEn .
        FILTER(lang(?altEn) = "en")
      }}
      OPTIONAL {{
        ?c skos:prefLabel ?prefLang .
        FILTER({pref_lang_filter})
      }}
      OPTIONAL {{
        ?c skos:altLabel ?altLang .
        FILTER({alt_lang_filter})
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
    """


def _fetch_detail_rows(*, uris: List[str], langs: List[str], batch_size: int, max_retries: int) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for start in range(0, len(uris), batch_size):
        chunk = uris[start : start + batch_size]
        rows.extend(sparql_select(_detail_query(uris=chunk, langs=langs), max_retries=max_retries))
        time.sleep(0.1)
    return rows


def _load_checkpoint(path: Path) -> Dict[str, int] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {
        "offset": int(data.get("offset", 0)),
        "written": int(data.get("written", 0)),
    }


def _write_checkpoint(path: Path, *, offset: int, written: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "offset": offset,
        "written": written,
        "updated_at_epoch": int(time.time()),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = Path(args.checkpoint).resolve()

    offset = args.offset
    written = 0

    if args.resume:
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            offset = checkpoint["offset"]
            written = checkpoint["written"]

    file_mode = "a" if args.resume and out_path.exists() else "w"

    with out_path.open(file_mode, encoding="utf-8") as fh:
        while True:
            page_rows = sparql_select(
                _paged_concepts_query(limit=args.page_size, offset=offset),
                max_retries=args.max_retries,
            )
            if not page_rows:
                break

            uris = [row.get("c", "").strip() for row in page_rows if row.get("c", "").strip()]
            rows = _fetch_detail_rows(
                uris=uris,
                langs=args.langs,
                batch_size=args.detail_batch_size,
                max_retries=args.max_retries,
            )
            rows_by_uri = {row.get("c", "").strip(): row for row in rows if row.get("c", "").strip()}

            for summary_row in page_rows:
                uri = summary_row.get("c", "").strip()
                row = rows_by_uri.get(uri, summary_row)
                pref = row.get("pref", "").strip() or summary_row.get("pref", "").strip()
                if not pref:
                    continue
                record = {
                    "uri": uri,
                    "source": "agrovoc",
                    "prefLabel_en": pref,
                    "altLabels_en": _split_concat(row.get("alts_en", "")),
                    "pref_labels": _split_concat(row.get("pref_labels", "")),
                    "alt_labels": _split_concat(row.get("alt_labels", "")),
                    "broader_prefLabels_en": _split_concat(row.get("broader_en", "")),
                    "note_en": (row.get("scopeNote") or row.get("definition") or "").strip(),
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                written += 1
                if args.limit and written >= args.limit:
                    break

            print(f"[AGROVOC export] wrote {written} rows (offset={offset})")
            _write_checkpoint(checkpoint_path, offset=offset + args.page_size, written=written)
            if args.limit and written >= args.limit:
                break

            offset += args.page_size
            time.sleep(0.2)

    print(f"[OK] Wrote {out_path}")
    print(f"[OK] Checkpoint {checkpoint_path}")


if __name__ == "__main__":
    main()
