"""Extract introductions from academic PDFs using LLM assistance."""

import argparse
import json
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import pdfplumber
import requests
from tqdm import tqdm

from crossdisc_extractor.classifier.config import load_config
from crossdisc_extractor.classifier.utils.http import request_with_retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_write_lock = threading.Lock()
_processed_lock = threading.Lock()

# Introduction extraction prompt (Chinese, for Nature-style papers)
INTRO_EXTRACT_PROMPT = """你是一名熟悉 Nature 主刊及其子刊结构的论文结构分析器。输入文本来自 pdfplumber 抽取的 PDF 内容，包含行断裂与不规则排版。你的任务是严格按照规则，从中基于语义与结构位置精确提取论文的引言（Introduction）部分，而非依赖加粗或字号等样式线索。

核心结构知识（必须遵守）
1) Nature 主刊及多数子刊通常没有显式小节标题"Introduction"。
2) 引言的位置定义：摘要（Abstract）结束之后，到第一个明确的小节标题之前的全部连续段落。
3) 如存在显式"Introduction"标题，则以该标题为起点，在下一个小节标题前结束。

章节的语义判定与边界识别（不使用加粗/字号作决定性依据）
4) 摘要识别（语义）：
   - 起点关键词（大小写忽略）：Abstract、ABSTRACT、Summary。
   - 摘要文本特征：高度概括、少引文回顾、少方法细节，常出现目的/结论型句式。
   - 摘要结束：摘要标记后，直到出现首个非摘要风格的正文段落为止。
5) 引言语义特征（满足其一或多项）：
   - 提供研究背景与动机，回顾相关工作与知识缺口（gap）。
   - 引出研究问题与重要性，提出研究目标与总体贡献。
   - 常以"Here we (show/report/demonstrate/introduce/present) ..."过渡到工作概述。
6) 非引言/后续小节的语义特征（出现即触发引言结束）：
   - 结果/主体：Results、Main、Results and Discussion、Findings 等。
   - 方法：Methods、Materials and Methods、Experimental。
   - 讨论/结论：Discussion、Conclusion、Conclusions。
   - 其它常见小节：Data availability、Code availability、Acknowledgements、References。
7) 若无法可靠识别标题，使用语义优先策略：
   - 从摘要后连续收集背景/综述/问题陈述/研究目标类段落。
   - 一旦出现连续的结果陈述或方法细节，即判定为引言结束。

图片与表格图注处理
8) 图注/表注判定并从引言中剔除：
   - 开头模式：Fig., Figure, Extended Data Fig(ure), Table 等。
9) 其它非正文噪声剔除：页眉页脚、版权声明、参考文献列表等。

文本清洗
10) 行合并：将同一段被拆分的短行按句子级合并。
11) 连字符断词修复。

输出要求
12) 只输出引言原文，不得改写、总结、解释或补充。
13) 保持原始段落结构；不得输出任何标题、小节名或图注。
14) 若无法可靠判断引言，仅输出空字符串 ""。

论文全文：
{text}"""


def _load_processed(output_file: str) -> set:
    """Load already-processed PDF URLs from output file for checkpoint resumption."""
    processed = set()
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                url = obj.get("pdf_url") or obj.get("real_pdf_url") or obj.get("input_pdf_url")
                if url:
                    processed.add(url)
    return processed


def _save_result(result: Dict[str, Any], output_file: str) -> None:
    """Thread-safe append of a single result to the output JSONL file."""
    with _write_lock:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass


def _get_real_pdf_url(article_url: str) -> str:
    """Resolve actual PDF URL from a landing page or direct link."""
    # Nature 系列期刊：DOI → 直接 PDF 链接（免去 HTTP 请求）
    m = re.search(r"doi\.org/10\.1038/(.+)$", article_url)
    if m:
        pdf_url = f"https://www.nature.com/articles/{m.group(1)}.pdf"
        logger.info("Nature DOI → PDF: %s", pdf_url)
        return pdf_url

    try:
        if not article_url.endswith(".pdf"):
            response = request_with_retry(
                requests.get, article_url,
                headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
            )
            if response is None:
                return article_url
            if "application/pdf" in response.headers.get("content-type", "").lower():
                return article_url

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")
            meta_pdf = soup.find("meta", attrs={"name": "citation_pdf_url"})
            if meta_pdf and meta_pdf.get("content"):
                return meta_pdf["content"]
            pdf_link = soup.find("a", href=re.compile(r"\.pdf(\?.*)?$"))
            if pdf_link and pdf_link.get("href"):
                return urljoin(article_url, pdf_link["href"])
        return article_url
    except Exception as e:
        logger.warning("Failed to resolve PDF URL (%s): %s", article_url, e)
        return article_url


def _extract_text_from_pdf(pdf_url: str, max_pages: int = 4) -> Optional[str]:
    """Download a PDF and extract text from the first N pages."""
    try:
        response = request_with_retry(
            requests.get, pdf_url,
            headers={"User-Agent": "Mozilla/5.0"}, timeout=30,
        )
        if response is None:
            return None

        pdf_file = BytesIO(response.content)
        full_text = ""

        with pdfplumber.open(pdf_file) as pdf:
            for page_num, page in enumerate(pdf.pages[:max_pages]):
                if page_num == 0 and len(getattr(page, "chars", [])) < 100:
                    continue

                width, height = page.width, page.height
                body_top, body_bottom = 80, height - 80
                mid_gap = 20
                left_col_right = (width - mid_gap) / 2
                right_col_left = (width + mid_gap) / 2

                left_text = page.crop((0, body_top, left_col_right, body_bottom)).extract_text(
                    x_tolerance=1, y_tolerance=2
                ) or ""
                right_text = page.crop((right_col_left, body_top, width, body_bottom)).extract_text(
                    x_tolerance=1, y_tolerance=2
                ) or ""

                page_text = left_text + "\n\n" + right_text
                if page_text.strip():
                    full_text += page_text + "\n\n"

        # Clean extracted text
        clean_lines = []
        for line in full_text.split("\n"):
            stripped = line.strip()
            if not stripped or len(stripped) < 15:
                continue
            if re.match(r"^\d+$", stripped):
                continue
            if "doi.org" in stripped:
                continue
            if re.search(
                r"(University|Department|Accepted|Received|e\.?mail|&|,\s*[A-Z]\.)",
                stripped, re.IGNORECASE,
            ):
                continue
            clean_lines.append(stripped)

        return "\n".join(clean_lines).strip()[:30000]
    except Exception as e:
        logger.error("PDF extraction failed (%s): %s", pdf_url, e)
        return None


def _call_llm_extract_intro(
    text: str, model_name: str, api_base: str, api_key: str,
) -> Optional[str]:
    """Call LLM to extract the introduction section from PDF text."""
    if not text:
        return None

    prompt = INTRO_EXTRACT_PROMPT.format(text=text[:20000])
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 20000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = request_with_retry(
        requests.post, f"{api_base}/chat/completions",
        headers=headers, json=payload, timeout=300,
    )
    if response is None or response.status_code != 200:
        return None

    result = response.json()
    try:
        intro = result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        try:
            intro = result["choices"][0].get("text", "").strip()
        except (KeyError, IndexError):
            return ""

    if intro and intro.startswith("引言部分："):
        intro = intro[len("引言部分："):].strip()
    return intro


def pipeline(
    records: List[Dict[str, Any]],
    processed_set: set,
    output_file: str,
    cfg,
) -> None:
    """Run the download + LLM extraction pipeline with concurrent workers."""
    n = len(records)
    model_executor = ThreadPoolExecutor(max_workers=cfg.extraction.model_workers)
    model_futures = []

    def submit_model_task(idx: int, rec: Dict[str, Any], real_url: str, text: Optional[str]):
        if not text:
            res = {**rec, "real_pdf_url": real_url, "status": "failed", "introduction": ""}
            _save_result(res, output_file)
            with _processed_lock:
                processed_set.add(rec.get("pdf_url"))
            return

        def worker():
            try:
                intro = _call_llm_extract_intro(
                    text, cfg.llm.model_name, cfg.llm.api_base, cfg.llm.api_key,
                )
                status = "success" if intro and len(intro.strip()) > 50 else "failed"
                res = {
                    **rec, "real_pdf_url": real_url,
                    "status": status, "introduction": intro or "",
                }
                _save_result(res, output_file)
                with _processed_lock:
                    processed_set.add(rec.get("pdf_url"))

                if intro:
                    preview = intro[:cfg.extraction.print_preview_chars]
                    logger.info("[%d/%d] Extracted %d chars", idx + 1, n, len(intro))
                else:
                    logger.warning("[%d/%d] No introduction extracted", idx + 1, n)
            except Exception as e:
                logger.error("Model task error idx=%d: %s", idx, e)
                res = {**rec, "real_pdf_url": real_url, "status": "error", "introduction": ""}
                _save_result(res, output_file)
                with _processed_lock:
                    processed_set.add(rec.get("pdf_url"))

        model_futures.append(model_executor.submit(worker))

    download_executor = ThreadPoolExecutor(max_workers=cfg.extraction.download_workers)
    download_futures = []

    def download_worker(idx: int, rec: Dict[str, Any]):
        pdf_url = rec.get("pdf_url", "").strip()
        try:
            real_url = _get_real_pdf_url(pdf_url)
            text = _extract_text_from_pdf(real_url, max_pages=cfg.extraction.max_pdf_pages)
            submit_model_task(idx, rec, real_url, text)
        except Exception as e:
            logger.error("Download error idx=%d, url=%s: %s", idx, pdf_url, e)
            res = {**rec, "real_pdf_url": pdf_url, "status": "error", "introduction": ""}
            _save_result(res, output_file)
            with _processed_lock:
                processed_set.add(rec.get("pdf_url"))

    for i, rec in enumerate(records):
        download_futures.append(download_executor.submit(download_worker, i, rec))

    logger.info("Waiting for download tasks...")
    for fut in tqdm(as_completed(download_futures), total=len(download_futures), desc="Download"):
        try:
            fut.result()
        except Exception as e:
            logger.error("Download future error: %s", e)

    logger.info("Waiting for model tasks...")
    for fut in tqdm(as_completed(model_futures), total=len(model_futures), desc="LLM Extract"):
        try:
            fut.result()
        except Exception as e:
            logger.error("Model future error: %s", e)

    download_executor.shutdown(wait=True)
    model_executor.shutdown(wait=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract introductions from academic PDFs")
    parser.add_argument("--input", "-i", required=True, help="Input JSONL file")
    parser.add_argument("--output", "-o", required=True, help="Output JSONL file")
    parser.add_argument("--config", default=None, help="Path to YAML config file")
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--api-base", default=None, help="Override API base URL")
    parser.add_argument("--api-key", default=None, help="Override API key")
    args = parser.parse_args()

    cfg = load_config(args.config, model_name=args.model, api_base=args.api_base, api_key=args.api_key)

    processed_set = _load_processed(args.output)
    logger.info("Loaded %d already-processed records", len(processed_set))

    records = []
    skipped = 0
    with open(args.input, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("Line %d: JSON parse error, skipping: %s", lineno, e)
                continue
            pdf_url = obj.get("pdf_url", "").strip()
            if not pdf_url:
                continue
            with _processed_lock:
                if pdf_url in processed_set:
                    skipped += 1
                    continue
            records.append(obj)

    if not records:
        logger.info("No records to process (all done or no valid input)")
        return

    logger.info("Processing %d records (skipped %d already done)", len(records), skipped)
    try:
        pipeline(records, processed_set, args.output, cfg)
    except KeyboardInterrupt:
        logger.warning("Interrupted. Completed results have been saved.")
        return

    logger.info("Done! Results saved to %s", args.output)


if __name__ == "__main__":
    main()
