# # crossdisc_extractor/utils/pdf_utils.py
# from __future__ import annotations

# import logging
# import os
# import re
# import tempfile
# from collections import Counter
# from typing import Optional, List, Tuple

# import requests

# logger = logging.getLogger("crossdisc.pdf")

# # Prefer PyMuPDF (fitz). Keep a soft fallback to pdfminer for environments where PyMuPDF is unavailable.
# try:
#     import fitz  # PyMuPDF
# except Exception:  # pragma: no cover
#     fitz = None

# try:
#     from pdfminer.high_level import extract_text as pdf_extract_text  # type: ignore
# except Exception:  # pragma: no cover
#     pdf_extract_text = None


# def _clean_text(txt: str) -> str:
#     txt = txt.replace("\r", "\n")
#     txt = re.sub(r"[ \u00A0]{2,}", " ", txt)
#     txt = re.sub(r"\n{3,}", "\n\n", txt)
#     return txt


# def _norm_hf_line(s: str) -> str:
#     """Normalize header/footer candidate lines for frequency matching."""
#     s = (s or "").strip().lower()
#     s = re.sub(r"\s+", " ", s)
#     # drop pure page numbers and common 'page x of y' patterns
#     if re.fullmatch(r"\d{1,4}", s):
#         return ""
#     s = re.sub(r"^(page\s*)?\d{1,4}(\s*of\s*\d{1,4})?$", "", s).strip()
#     # mask DOI/URLs (vary across pages in some PDFs)
#     s = re.sub(r"\bdoi\s*:\s*\S+", "doi", s)
#     s = re.sub(r"https?://\S+", "url", s)
#     # collapse long digit runs
#     s = re.sub(r"\d{4,}", "####", s)
#     return s.strip()


# def _remove_repeated_header_footer(page_lines: List[List[str]], k: int = 3, min_frac: float = 0.6) -> List[List[str]]:
#     """Remove repeated header/footer lines across pages (a pragmatic de-noising step)."""
#     n_pages = max(1, len(page_lines))
#     thr = max(2, int(round(n_pages * min_frac)))

#     header_counter: Counter[str] = Counter()
#     footer_counter: Counter[str] = Counter()

#     for lines in page_lines:
#         if not lines:
#             continue
#         head = lines[:k]
#         tail = lines[-k:] if len(lines) >= k else lines[:]
#         for ln in head:
#             key = _norm_hf_line(ln)
#             if key:
#                 header_counter[key] += 1
#         for ln in tail:
#             key = _norm_hf_line(ln)
#             if key:
#                 footer_counter[key] += 1

#     header_remove = {k for k, c in header_counter.items() if c >= thr}
#     footer_remove = {k for k, c in footer_counter.items() if c >= thr}

#     # Also remove common boilerplate lines even if not repeated enough.
#     boilerplate_patterns = [
#         r"downloaded from",
#         r"preprint",
#         r"arxiv",
#         r"biorxiv",
#         r"medrxiv",
#         r"copyright",
#         r"creative commons",
#         r"license",
#         r"all rights reserved",
#     ]
#     boilerplate_re = re.compile("|".join(boilerplate_patterns), re.IGNORECASE)

#     cleaned_pages: List[List[str]] = []
#     for lines in page_lines:
#         out: List[str] = []
#         for ln in lines:
#             ln0 = (ln or "").strip()
#             if not ln0:
#                 continue
#             if boilerplate_re.search(ln0):
#                 continue
#             key = _norm_hf_line(ln0)
#             if key and (key in header_remove or key in footer_remove):
#                 continue
#             out.append(ln0)
#         cleaned_pages.append(out)

#     return cleaned_pages


# def _extract_intro_from_text(full_text: str, max_chars: int = 12000) -> Optional[str]:
#     """
#     简化版 Introduction 抽取：
#     - 找到含有 "Introduction" / "INTRODUCTION" / "引言" 的行；
#     - 从该行之后截取，直到下一个常见章节标题（Methods, Results, Discussion, Conclusion, References 等）。
#     """
#     if not full_text:
#         return None

#     txt = _clean_text(full_text)
#     lines = txt.split("\n")

#     intro_start = None
#     for i, ln in enumerate(lines):
#         low = ln.strip().lower()
#         if re.match(r"^(introduction)\b", low) or "引言" in ln:
#             intro_start = i + 1
#             break

#     if intro_start is None:
#         # 找不到引言：退化为开头部分（通常比空更有用）
#         head = "\n".join(lines[:300])
#         return head[:max_chars]

#     # 终止：下一个章节
#     stop_re = re.compile(
#         r"^(methods|materials\s+and\s+methods|results|discussion|conclusion|references|acknowledg|supplementary)\b",
#         re.IGNORECASE,
#     )
#     intro_lines: List[str] = []
#     for j in range(intro_start, len(lines)):
#         ln = lines[j].strip()
#         if not ln:
#             intro_lines.append("")
#             continue
#         if stop_re.match(ln.lower()):
#             break
#         intro_lines.append(lines[j])

#     intro = "\n".join(intro_lines).strip()
#     if not intro:
#         # 极端情况：引言段落提取为空，则退化为开头
#         head = "\n".join(lines[:300])
#         return head[:max_chars]

#     return intro[:max_chars]


# def _extract_text_with_pymupdf(pdf_bytes: bytes) -> str:
#     if fitz is None:
#         raise RuntimeError("PyMuPDF/fitz 不可用")
#     doc = fitz.open(stream=pdf_bytes, filetype="pdf")
#     page_lines: List[List[str]] = []
#     for page in doc:
#         txt = page.get_text("text") or ""
#         txt = _clean_text(txt)
#         lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
#         page_lines.append(lines)

#     page_lines = _remove_repeated_header_footer(page_lines, k=3, min_frac=0.6)

#     # Re-assemble full text
#     pages_joined = ["\n".join(lines) for lines in page_lines if lines]
#     return "\n\n".join(pages_joined).strip()


# def fetch_pdf_and_extract_intro(
#     pdf_url: str,
#     timeout: int = 25,
#     max_pdf_mb: int = 25,
# ) -> Optional[str]:
#     """
#     下载 PDF 并提取 Introduction（或退化为正文开头）。
#     现在优先使用 PyMuPDF/fitz 提取文本，并做页眉页脚清洗；
#     若 PyMuPDF 不可用，则回退到 pdfminer（若安装了）。
#     """
#     if not pdf_url:
#         return None

#     # doi.org 通常不是直接 PDF
#     if "doi.org/" in pdf_url:
#         logger.info("跳过 doi.org 链接（非直接 PDF）：%s", pdf_url)
#         return None

#     try:
#         resp = requests.get(pdf_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
#         resp.raise_for_status()

#         size_mb = len(resp.content) / (1024 * 1024)
#         if size_mb > max_pdf_mb:
#             logger.warning("PDF 过大（%.1fMB > %dMB），跳过解析", size_mb, max_pdf_mb)
#             return None

#         full_text = ""
#         if fitz is not None:
#             try:
#                 full_text = _extract_text_with_pymupdf(resp.content) or ""
#             except Exception as e:
#                 logger.warning("PyMuPDF 解析失败，将回退到 pdfminer：%s", e)

#         if not full_text.strip():
#             if pdf_extract_text is None:
#                 logger.warning("PDF 文本抽取失败：PyMuPDF 不可用/失败且 pdfminer 未安装")
#                 return None
#             # pdfminer fallback
#             with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
#                 tf.write(resp.content)
#                 tmp_path = tf.name
#             try:
#                 full_text = pdf_extract_text(tmp_path) or ""
#             finally:
#                 try:
#                     os.remove(tmp_path)
#                 except Exception:
#                     pass

#         if not full_text.strip():
#             logger.warning("PDF 提取文本为空")
#             return None

#         intro = _extract_intro_from_text(full_text)
#         return intro

#     except Exception as e:
#         logger.warning(f"获取/解析 PDF 失败：{e}")
#         return None



# crossdisc_extractor/utils/pdf_utils.py
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Optional

import requests
from pdfminer.high_level import extract_text as pdf_extract_text

logger = logging.getLogger("crossdisc.pdf")


def _clean_text(txt: str) -> str:
    txt = txt.replace("\r", "\n")
    txt = re.sub(r"[ \u00A0]{2,}", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt


def _extract_intro_from_text(full_text: str, max_chars: int = 6000) -> Optional[str]:
    """
    简化版 Introduction 抽取：
    - 找到含有 "Introduction" 或 "INTRODUCTION" 或 "引言" 的行；
    - 从该行之后截取，直到下一个常见章节标题（Methods, Results, Discussion, Conclusion, References 等）。
    """
    if not full_text:
        return None

    txt = _clean_text(full_text)
    lines = txt.split("\n")

    intro_start = None
    for i, ln in enumerate(lines):
        low = ln.strip().lower()
        if re.match(r"^(introduction)\b", low) or "引言" in ln:
            intro_start = i + 1
            break
    if intro_start is None:
        # fallback: 直接返回前 max_chars 作为“引言近似”
        return txt[:max_chars]

    # 找结束位置
    end = len(lines)
    for j in range(intro_start + 1, len(lines)):
        low = lines[j].strip().lower()
        if re.match(r"^(methods?|materials?|results?|discussion|conclusion|references?)\b", low):
            end = j
            break

    intro = "\n".join(lines[intro_start:end]).strip()
    if not intro:
        return None
    return intro[:max_chars]


def fetch_pdf_and_extract_intro(url: str, timeout: int = 40, max_chars: int = 6000) -> Optional[str]:
    """通过 URL 下载 PDF 并抽取 Introduction 段落。"""
    if not url or not isinstance(url, str):
        return None

    # Nature 系列期刊：DOI → 直接 PDF 链接
    if "doi.org" in url:
        m = re.search(r"doi\.org/10\.1038/(.+)$", url)
        if m:
            article_id = m.group(1)
            url = f"https://www.nature.com/articles/{article_id}.pdf"
            logger.info(f"Nature DOI 转换为直接 PDF 链接：{url}")
        else:
            logger.warning(f"检测到非 Nature DOI 链接（无法转换）：{url}，跳过 PDF 解析")
            return None

    try:
        logger.info(f"下载 PDF：{url}")
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) CrossBench/1.0"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
            tf.write(resp.content)
            tmp_path = tf.name

        full_text = pdf_extract_text(tmp_path) or ""
        os.remove(tmp_path)

        if not full_text.strip():
            logger.warning("PDF 提取文本为空")
            return None

        intro = _extract_intro_from_text(full_text, max_chars=max_chars)
        return intro
    except Exception as e:
        logger.warning(f"获取/解析 PDF 失败：{e}")
        return None
