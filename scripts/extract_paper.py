"""Extract paper metadata from CSV and resolve PDF links."""

import argparse
import json
import logging
import re

import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

COLUMNS_TO_EXTRACT = [
    "title", "abstract",
    "primary_location.source.display_name",
    "topics.field.display_name",
    "best_oa_location.pdf_url",
    "primary_location.pdf_url",
    "best_oa_location.landing_page_url",
    "publication_year",
]


def _safe_str(x) -> str:
    if isinstance(x, str):
        return x.strip()
    elif pd.isna(x):
        return ""
    return str(x).strip()


def _fetch_pdf_from_landing(landing_url: str) -> str:
    """Try to resolve a PDF URL from a landing page."""
    if not landing_url:
        return ""
    try:
        resp = requests.get(landing_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            if ".pdf" in a["href"].lower():
                return urljoin(landing_url, a["href"])
        for tag in soup.find_all(["meta", "script"]):
            content = tag.get("content") or str(tag)
            if ".pdf" in content.lower():
                start = content.lower().find("http")
                end = content.lower().find(".pdf") + 4
                if start != -1:
                    return content[start:end]
    except Exception as e:
        logger.warning("Failed to fetch PDF from landing page %s: %s", landing_url, e)
    return ""


def extract_paper_info(input_csv: str, output_json: str, max_workers: int = 50) -> None:
    """Extract paper metadata from CSV, resolve PDF links, write JSONL output."""
    logger.info("Reading CSV: %s", input_csv)
    df = pd.read_csv(input_csv, usecols=COLUMNS_TO_EXTRACT, dtype=str)

    df.rename(columns={
        "primary_location.source.display_name": "journal",
        "topics.field.display_name": "field",
        "best_oa_location.pdf_url": "pdf_best",
        "primary_location.pdf_url": "pdf_primary",
        "best_oa_location.landing_page_url": "landing_url",
        "publication_year": "year",
    }, inplace=True)

    df = df.dropna(subset=["abstract", "title"])
    df = df[df["abstract"].str.strip() != ""]
    df = df[df["title"].str.strip() != ""]

    logger.info("Loaded %d valid records, resolving PDF links...", len(df))

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for _, row in df.iterrows():
            title = _safe_str(row["title"])
            abstract = _safe_str(row["abstract"])
            journal = _safe_str(row.get("journal", ""))
            field = _safe_str(row.get("field", ""))
            year = _safe_str(row.get("year", ""))
            pdf_url = _safe_str(row.get("pdf_best")) or _safe_str(row.get("pdf_primary"))
            landing_url = _safe_str(row.get("landing_url"))

            if not pdf_url and landing_url:
                future = executor.submit(_fetch_pdf_from_landing, landing_url)
                future_map[future] = (title, abstract, journal, field, year)
            else:
                results.append({
                    "title": title, "abstract": abstract, "journal": journal,
                    "field": field, "year": year, "pdf_url": pdf_url,
                })

        for future in tqdm(as_completed(future_map), total=len(future_map), desc="Fetching PDFs"):
            title, abstract, journal, field, year = future_map[future]
            try:
                pdf_url = future.result()
            except Exception as e:
                logger.warning("PDF fetch failed: %s", e)
                pdf_url = ""
            results.append({
                "title": title, "abstract": abstract, "journal": journal,
                "field": field, "year": year, "pdf_url": pdf_url,
            })

    with open(output_json, "w", encoding="utf-8") as f:
        for record in results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("Done: %d records written to %s", len(results), output_json)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract paper info from CSV")
    parser.add_argument("--input", "-i", required=True, help="Input CSV path")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL path")
    parser.add_argument("--max-workers", type=int, default=50, help="Thread pool size")
    args = parser.parse_args()

    extract_paper_info(args.input, args.output, max_workers=args.max_workers)


if __name__ == "__main__":
    main()
