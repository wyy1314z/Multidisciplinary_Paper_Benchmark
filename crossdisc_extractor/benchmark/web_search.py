"""
crossdisc_extractor/benchmark/web_search.py

Web-search-augmented reference path retrieval.

Uses Semantic Scholar API to find similar papers, then extracts
knowledge paths via the existing extraction pipeline. The extracted
paths are formatted identically to GT paths so they can be seamlessly
merged into evaluation metrics.

Each invocation produces a detailed trace log (JSON) recording every
pipeline step and its outputs, saved alongside the path cache.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("eval_web_search")

# ---------------------------------------------------------------------------
#  Semantic Scholar API
# ---------------------------------------------------------------------------

_S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_API_KEY = os.environ.get("S2_API_KEY", "")  # optional, raises rate limit


def search_similar_papers(
    title: str,
    abstract: str = "",
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search Semantic Scholar for papers similar to the given one.

    Returns up to *limit* papers with title + abstract.
    """
    query = title.strip()
    if not query:
        logger.info("[Step1-Search] 空标题，跳过搜索")
        return []

    headers: Dict[str, str] = {}
    if _S2_API_KEY:
        headers["x-api-key"] = _S2_API_KEY

    params = {
        "query": query[:200],  # API limit on query length
        "limit": min(limit + 5, 50),  # fetch extra to account for self-match removal
        "fields": "title,abstract,externalIds",
    }

    logger.info("[Step1-Search] 查询 Semantic Scholar API ...")
    logger.info("[Step1-Search]   query  = '%s'", params["query"][:80])
    logger.info("[Step1-Search]   limit  = %d (请求 %d)", limit, params["limit"])

    results: List[Dict[str, Any]] = []
    raw_total = 0
    skipped_no_abstract = 0
    skipped_self_match = 0

    for attempt in range(3):
        try:
            resp = requests.get(
                _S2_SEARCH_URL,
                params=params,
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt + 1
                logger.warning("[Step1-Search] S2 rate limited (429), waiting %ds ... (attempt %d/3)", wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json().get("data", [])
            raw_total = len(data)

            # Filter: must have abstract, exclude self-match
            title_lower = title.strip().lower()
            for paper in data:
                if not paper.get("abstract"):
                    skipped_no_abstract += 1
                    continue
                if paper.get("title", "").strip().lower() == title_lower:
                    skipped_self_match += 1
                    continue
                results.append({
                    "title": paper["title"],
                    "abstract": paper["abstract"],
                    "paperId": paper.get("paperId", ""),
                })
                if len(results) >= limit:
                    break
            break
        except requests.RequestException as e:
            logger.warning("[Step1-Search] S2 search attempt %d/3 failed: %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2 ** attempt)

    logger.info("[Step1-Search] API 返回 %d 篇原始结果，过滤后保留 %d 篇 (无摘要跳过: %d, 自匹配跳过: %d)",
                raw_total, len(results), skipped_no_abstract, skipped_self_match)
    for i, p in enumerate(results):
        logger.info("[Step1-Search]   [%d/%d] title='%s'  paperId=%s",
                    i + 1, len(results), p["title"][:70], p["paperId"][:12])

    return results


# ---------------------------------------------------------------------------
#  Lightweight discipline classification via LLM
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """你是一位学科分类专家。请根据以下论文的标题和摘要，判断其主学科和涉及的辅助学科。

标题: {title}
摘要: {abstract}

请以严格JSON格式输出:
{{
  "primary": "主学科名称（中文）",
  "secondary_list": ["辅学科1", "辅学科2"]
}}

注意：学科名称应使用中文标准学科分类体系的名称（如"临床医学"、"计算机科学技术"、"基础医学"等）。
如果论文只涉及单一学科，secondary_list 填写 []。"""


def classify_paper(title: str, abstract: str) -> Tuple[str, List[str]]:
    """Classify a paper's disciplines using a single LLM call."""
    from crossdisc_extractor.utils.llm import chat_completion_with_retry

    logger.info("[Step2-Classify] 正在对论文进行学科分类: '%s'", title[:60])

    prompt = _CLASSIFY_PROMPT.format(
        title=title.strip(),
        abstract=(abstract or "")[:1500],
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = chat_completion_with_retry(messages, temperature=0.0, max_tokens=512)
        logger.debug("[Step2-Classify] LLM 原始响应:\n%s", raw[:500])
        # Parse JSON from response
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        data = json.loads(cleaned)
        primary = data.get("primary", "unknown")
        secondary_list = data.get("secondary_list", [])
        if not isinstance(secondary_list, list):
            secondary_list = []
        logger.info("[Step2-Classify] 分类结果: primary='%s', secondary=%s", primary, secondary_list)
        return primary, secondary_list
    except Exception as e:
        logger.warning("[Step2-Classify] 分类失败 '%s': %s", title[:50], e)
        return "unknown", []


# ---------------------------------------------------------------------------
#  Extract knowledge paths from a paper
# ---------------------------------------------------------------------------

def extract_paths_from_paper(
    title: str,
    abstract: str,
    primary: str,
    secondary_list: List[str],
) -> List[Dict[str, Any]]:
    """
    Run the full extraction pipeline on a paper and return its
    hypothesis paths in the gt_set format.
    """
    from crossdisc_extractor.extractor_multi_stage import run_pipeline_for_item

    logger.info("[Step3-Extract] 开始提取知识路径: '%s' (学科: %s)", title[:60], primary)

    try:
        extraction, _, _ = run_pipeline_for_item(
            title=title,
            abstract=abstract,
            primary=primary,
            secondary_list=secondary_list,
            pdf_url="",  # skip PDF download
            temperature_struct=0.2,
            temperature_query=0.2,
            temperature_hyp=0.3,
            seed=42,
            language_mode="chinese",
        )
    except Exception as e:
        logger.warning("[Step3-Extract] 提取失败 '%s': %s", title[:50], e)
        return []

    # Convert Extraction object to path list
    paths: List[Dict[str, Any]] = []
    hyp = extraction.假设 if hasattr(extraction, "假设") else None
    if hyp is None:
        # Try dict access
        if isinstance(extraction, dict):
            hyp_dict = extraction.get("假设", {})
        else:
            hyp_dict = extraction.model_dump().get("假设", {})
    else:
        hyp_dict = hyp.model_dump() if hasattr(hyp, "model_dump") else hyp

    level_map = {"一级": "L1", "二级": "L2", "三级": "L3"}
    for cn_level, en_level in level_map.items():
        level_paths = hyp_dict.get(cn_level, []) if isinstance(hyp_dict, dict) else []
        if not isinstance(level_paths, list):
            continue
        for p in level_paths:
            if not isinstance(p, list) or not p:
                continue
            paths.append({
                "path": p,
                "level": en_level,
                "discipline": primary,
                "source": "web_search",
                "source_paper": title,
            })

    logger.info("[Step3-Extract] 提取完成: '%s' -> %d 条路径 (L1: %d, L2: %d, L3: %d)",
                title[:50], len(paths),
                sum(1 for p in paths if p["level"] == "L1"),
                sum(1 for p in paths if p["level"] == "L2"),
                sum(1 for p in paths if p["level"] == "L3"))

    # Log each extracted path
    for i, p in enumerate(paths):
        steps_preview = " -> ".join(
            f"{s.get('head', '?')}--[{s.get('relation', '?')}]-->{s.get('tail', '?')}"
            for s in (p["path"] if isinstance(p["path"], list) else [])
        )
        logger.info("[Step3-Extract]   [%s-%d] %s", p["level"], i + 1, steps_preview[:150])

    return paths


# ---------------------------------------------------------------------------
#  Cache utilities
# ---------------------------------------------------------------------------

def _cache_key(title: str) -> str:
    return hashlib.md5(title.strip().lower().encode("utf-8")).hexdigest()


def _load_cache(cache_dir: str, key: str) -> Optional[List[Dict[str, Any]]]:
    path = os.path.join(cache_dir, f"{key}.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_cache(cache_dir: str, key: str, data: List[Dict[str, Any]]) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Failed to save cache: %s", e)


def _save_trace(cache_dir: str, key: str, trace: Dict[str, Any]) -> None:
    """Save the full pipeline trace to a separate JSON file for auditing."""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{key}_trace.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
        logger.info("[Trace] 流程追踪已保存: %s", path)
    except Exception as e:
        logger.warning("[Trace] 追踪保存失败: %s", e)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def search_and_extract_reference_paths(
    title: str,
    abstract: str,
    limit: int = 10,
    cache_dir: str = "web_search_cache",
    max_workers: int = 3,
) -> List[Dict[str, Any]]:
    """
    Search for similar papers and extract knowledge paths from them.

    1. Query Semantic Scholar for similar papers
    2. Classify each paper's disciplines (LLM)
    3. Run extraction pipeline to get hypothesis paths
    4. Return paths in gt_set-compatible format

    Results are cached to disk to avoid redundant API calls.
    A detailed trace JSON is also saved for each paper title.

    Parameters
    ----------
    title : str
        Title of the paper being evaluated.
    abstract : str
        Abstract of the paper being evaluated.
    limit : int
        Number of similar papers to search for.
    cache_dir : str
        Directory for caching extraction results.
    max_workers : int
        Number of parallel extraction workers.

    Returns
    -------
    List[Dict[str, Any]]
        List of path dicts, each with keys: path, level, discipline,
        source ("web_search"), source_paper.
    """
    key = _cache_key(title)
    cached = _load_cache(cache_dir, key)
    if cached is not None:
        logger.info("=" * 70)
        logger.info("[WebSearch] 缓存命中: '%s' (%d 条路径)", title[:50], len(cached))
        logger.info("=" * 70)
        return cached

    logger.info("=" * 70)
    logger.info("[WebSearch] 开始处理论文: '%s'", title[:80])
    logger.info("[WebSearch] abstract = '%s'", (abstract or "")[:120])
    logger.info("[WebSearch] limit=%d, max_workers=%d, cache_dir='%s'", limit, max_workers, cache_dir)
    logger.info("=" * 70)

    # Initialize trace record
    trace: Dict[str, Any] = {
        "timestamp": datetime.datetime.now().isoformat(),
        "input": {
            "title": title,
            "abstract": (abstract or "")[:500],
            "limit": limit,
        },
        "step1_search": {},
        "step2_classify": [],
        "step3_extract": [],
        "step4_aggregate": {},
    }

    # ── Step 1: Search ────────────────────────────────────────────────────
    logger.info("-" * 50)
    logger.info("[Step1-Search] >>> 搜索相似论文 ...")
    t0 = time.time()
    papers = search_similar_papers(title, abstract, limit=limit)
    elapsed_search = time.time() - t0
    logger.info("[Step1-Search] 耗时 %.1fs", elapsed_search)

    trace["step1_search"] = {
        "query": title.strip()[:200],
        "elapsed_sec": round(elapsed_search, 2),
        "num_results": len(papers),
        "papers": [
            {"title": p["title"], "paperId": p["paperId"], "abstract_len": len(p.get("abstract", ""))}
            for p in papers
        ],
    }

    if not papers:
        logger.warning("[Step1-Search] 未找到相似论文，流程终止")
        _save_cache(cache_dir, key, [])
        trace["step4_aggregate"] = {"total_paths": 0, "reason": "no_similar_papers"}
        _save_trace(cache_dir, key, trace)
        return []

    # ── Step 2 & 3: Classify + Extract (parallel) ────────────────────────
    logger.info("-" * 50)
    logger.info("[Step2+3] >>> 并行处理 %d 篇论文 (workers=%d) ...", len(papers), max_workers)
    all_paths: List[Dict[str, Any]] = []

    # Thread-safe collection for per-paper trace records
    paper_traces: List[Dict[str, Any]] = []
    import threading
    _trace_lock = threading.Lock()

    def _process_paper(paper: Dict[str, Any]) -> List[Dict[str, Any]]:
        p_title = paper["title"]
        p_abstract = paper["abstract"]
        p_trace: Dict[str, Any] = {
            "title": p_title,
            "paperId": paper.get("paperId", ""),
        }

        # Step 2: Classify
        t_cls = time.time()
        primary, secondary_list = classify_paper(p_title, p_abstract)
        elapsed_cls = time.time() - t_cls
        p_trace["classify"] = {
            "elapsed_sec": round(elapsed_cls, 2),
            "primary": primary,
            "secondary_list": secondary_list,
        }

        if primary == "unknown" and not secondary_list:
            logger.warning("[Step2-Classify] 分类失败，跳过该论文: '%s'", p_title[:50])
            p_trace["extract"] = {"skipped": True, "reason": "classification_failed"}
            with _trace_lock:
                paper_traces.append(p_trace)
            return []

        # Step 3: Extract
        t_ext = time.time()
        paths = extract_paths_from_paper(p_title, p_abstract, primary, secondary_list)
        elapsed_ext = time.time() - t_ext
        p_trace["extract"] = {
            "elapsed_sec": round(elapsed_ext, 2),
            "num_paths": len(paths),
            "paths_by_level": {
                "L1": sum(1 for p in paths if p["level"] == "L1"),
                "L2": sum(1 for p in paths if p["level"] == "L2"),
                "L3": sum(1 for p in paths if p["level"] == "L3"),
            },
            "paths": [
                {
                    "level": p["level"],
                    "steps": [
                        {"head": s.get("head", ""), "relation": s.get("relation", ""), "tail": s.get("tail", "")}
                        for s in (p["path"] if isinstance(p["path"], list) else [])
                    ],
                }
                for p in paths
            ],
        }

        with _trace_lock:
            paper_traces.append(p_trace)
        return paths

    t_all = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_paper, paper): paper["title"]
            for paper in papers
        }
        for future in as_completed(futures):
            p_title = futures[future]
            try:
                paths = future.result(timeout=300)  # 5 min per paper
                all_paths.extend(paths)
            except Exception as e:
                logger.warning("[Step2+3] 处理失败 '%s': %s", p_title[:50], e)
                with _trace_lock:
                    paper_traces.append({
                        "title": p_title,
                        "error": str(e),
                    })
    elapsed_all = time.time() - t_all

    # Sort traces by title for deterministic output
    paper_traces.sort(key=lambda x: x.get("title", ""))
    trace["step2_classify"] = [
        {"title": pt["title"][:80], **pt.get("classify", {})}
        for pt in paper_traces
    ]
    trace["step3_extract"] = [
        {"title": pt["title"][:80], **(pt.get("extract", {}))}
        for pt in paper_traces
    ]

    # ── Step 4: Aggregate ─────────────────────────────────────────────────
    logger.info("-" * 50)
    logger.info("[Step4-Aggregate] >>> 汇总结果")
    logger.info("[Step4-Aggregate] 并行处理总耗时: %.1fs", elapsed_all)
    logger.info("[Step4-Aggregate] 成功处理论文: %d/%d", sum(1 for pt in paper_traces if pt.get("extract", {}).get("num_paths", 0) > 0), len(papers))
    logger.info("[Step4-Aggregate] 提取路径总数: %d", len(all_paths))

    level_counts = {"L1": 0, "L2": 0, "L3": 0}
    for p in all_paths:
        level_counts[p["level"]] = level_counts.get(p["level"], 0) + 1
    logger.info("[Step4-Aggregate]   L1: %d 条, L2: %d 条, L3: %d 条",
                level_counts["L1"], level_counts["L2"], level_counts["L3"])

    # Log per-source-paper breakdown
    from collections import Counter
    source_counter = Counter(p["source_paper"] for p in all_paths)
    for src_paper, cnt in source_counter.most_common():
        logger.info("[Step4-Aggregate]   来源: '%s' -> %d 条路径", src_paper[:60], cnt)

    trace["step4_aggregate"] = {
        "elapsed_sec": round(elapsed_all, 2),
        "total_paths": len(all_paths),
        "paths_by_level": level_counts,
        "papers_with_paths": sum(1 for pt in paper_traces if pt.get("extract", {}).get("num_paths", 0) > 0),
        "papers_failed": sum(1 for pt in paper_traces if "error" in pt),
        "per_source_paper": dict(source_counter),
    }

    logger.info("=" * 70)
    logger.info("[WebSearch] 完成: '%s' -> 共 %d 条 web search 路径", title[:50], len(all_paths))
    logger.info("=" * 70)

    # 4. Cache and save trace
    _save_cache(cache_dir, key, all_paths)
    _save_trace(cache_dir, key, trace)
    return all_paths
