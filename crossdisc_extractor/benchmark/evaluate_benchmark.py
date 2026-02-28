import json
import argparse
import random
import numpy as np
import logging
import math
import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
from tqdm import tqdm

from crossdisc_extractor.utils.llm import chat_completion_with_retry
from crossdisc_extractor.benchmark.eval_prompts import PROMPT_EVAL_L1, PROMPT_EVAL_DEEP

# 设置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("eval_kg")

class GraphMetricEvaluator:
    """
    基于图结构的客观评测指标计算器
    """
    @staticmethod
    def calculate_path_consistency(gen_path: List[Dict], gt_paths: List[Dict]) -> float:
        """
        计算路径一致性 (Path Consistency)：
        生成路径中的三元组 (Head, Relation, Tail) 在 Ground Truth 知识库中的覆盖率。
        这反映了生成路径的“事实准确性”。
        """
        if not gen_path:
            return 0.0
            
        # 1. 构建 GT 三元组集合 (归一化处理)
        gt_triples = set()
        for gt_item in gt_paths:
            for step in gt_item.get("path", []):
                h = (step.get("head") or "").strip().lower()
                t = (step.get("tail") or "").strip().lower()
                # 关系通常比较多样，这里只匹配头尾实体作为松弛条件，或者包含关系
                # 为了严格一点，我们尝试匹配头尾
                gt_triples.add((h, t))
        
        if not gt_triples:
            return 0.0

        # 2. 计算生成路径的匹配度
        matched_steps = 0
        for step in gen_path:
            h = (step.get("head") or "").strip().lower()
            t = (step.get("tail") or "").strip().lower()
            if (h, t) in gt_triples:
                matched_steps += 1
            else:
                # 尝试反向匹配 (如果是无向图或误判方向)
                if (t, h) in gt_triples:
                    matched_steps += 0.5 # 给予一半分数
        
        return matched_steps / len(gen_path)

    @staticmethod
    def calculate_bridging_score(gen_path: List[Dict]) -> float:
        """
        计算桥接分数 (Bridging Score)：
        衡量路径首尾实体的语义距离。跨学科假设通常连接语义距离较远的实体。
        使用 Jaccard Distance 估算：1 - (交集/并集)
        """
        if not gen_path:
            return 0.0
            
        start_node = (gen_path[0].get("head") or "").lower()
        end_node = (gen_path[-1].get("tail") or "").lower()
        
        start_terms = set(re.findall(r'\w+', start_node))
        end_terms = set(re.findall(r'\w+', end_node))
        
        if not start_terms or not end_terms:
            return 0.0
            
        intersection = len(start_terms & end_terms)
        union = len(start_terms | end_terms)
        
        if union == 0:
            return 0.0
            
        # 距离越远 (交集越小)，桥接分数越高
        return 1.0 - (intersection / union)

def normalize_paths_structure(raw_data: List[Any]) -> List[List[Dict[str, Any]]]:
    """
    规范化路径数据结构。
    兼容两种格式：
    1. 嵌套列表: [[step1, step2], [step1, step2]] (标准格式)
    2. 扁平列表: [step1, step2, step1, step2] (Build Dataset Bug 导致)
    """
    if not raw_data:
        return []
        
    # 检查是否已经是嵌套列表（第一个元素是列表）
    if isinstance(raw_data[0], list):
        return raw_data
        
    # 如果是字典，说明是扁平列表，需要重组
    if isinstance(raw_data[0], dict):
        paths = []
        current_path = []
        for step in raw_data:
            step_num = step.get("step")
            # 如果遇到 step 1 且 current_path 不为空，说明新路径开始
            # 或者如果 current_path 长度达到 3 (假设每条路径3步)
            if step_num == 1 and current_path:
                paths.append(current_path)
                current_path = []
            current_path.append(step)
        
        if current_path:
            paths.append(current_path)
        return paths
        
    return []

class GlobalKG:
    """
    基于 Benchmark 数据集构建的全局知识图谱（按学科索引路径）。
    """
    def __init__(self, benchmark_path: str):
        self.paths_by_discipline: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self.path_vectors = {} # Cache for vectors
        self.load_benchmark(benchmark_path)

    def load_benchmark(self, path: str):
        logger.info(f"正在加载 Benchmark 数据集构建知识图谱: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        count = 0
        for item in data:
            # 兼容 Extractor 输出格式
            if "parsed" in item:
                parsed = item["parsed"]
                meta = parsed.get("meta", {})
                primary = meta.get("primary", "unknown")
                hyp = parsed.get("假设", {})
                paths_dict = {
                    "L1": hyp.get("一级", []),
                    "L2": hyp.get("二级", []),
                    "L3": hyp.get("三级", [])
                }
                item_id = str(hash(meta.get("title", "")))
                abstract = item.get("abstract", "")
            else:
                # Benchmark 标准格式
                primary = item["input"].get("primary_discipline", "unknown")
                gt = item.get("ground_truth", {})
                paths_dict = gt.get("hypothesis_paths", {})
                item_id = item["id"]
                abstract = item["input"].get("abstract", "")
            
            # 将所有层级的路径都加入到该学科的集合中
            for level in ["L1", "L2", "L3"]:
                raw_paths = paths_dict.get(level, [])
                # 规范化路径：处理扁平化列表 vs 嵌套列表
                normalized_paths = normalize_paths_structure(raw_paths)
                
                for path in normalized_paths:
                    path_obj = {
                        "path": path,
                        "level": level,
                        "source_id": item_id,
                        "context": abstract 
                    }
                    self.paths_by_discipline[primary].append(path_obj)
                    
                    # Precompute vector for this path
                    path_str = json.dumps(path, ensure_ascii=False)
                    self.path_vectors[id(path_obj)] = self._text_to_vector(path_str)
                    
                    count += 1
        
        logger.info(f"KG 构建完成。共索引 {count} 条路径，覆盖 {len(self.paths_by_discipline)} 个学科。")

    def _text_to_vector(self, text: str) -> Counter:
        words = re.findall(r'\w+', text.lower())
        return Counter(words)

    def _cosine_sim(self, vec1: Counter, vec2: Counter) -> float:
        intersection = set(vec1.keys()) & set(vec2.keys())
        numerator = sum([vec1[x] * vec2[x] for x in intersection])
        
        sum1 = sum([vec1[x]**2 for x in vec1.keys()])
        sum2 = sum([vec2[x]**2 for x in vec2.keys()])
        denominator = math.sqrt(sum1) * math.sqrt(sum2)
        
        if not denominator:
            return 0.0
        return numerator / denominator

    def retrieve_relevant_paths(self, discipline: str, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        根据学科和查询检索最相关的 K 条路径作为 Ground Truth Set。
        使用 TF-IDF/Cosine Similarity 进行语义检索。
        """
        candidates = self.paths_by_discipline.get(discipline, [])
        if not candidates:
            # 如果该学科没有路径，尝试从所有路径中随机采样（兜底）
            all_paths = [p for paths in self.paths_by_discipline.values() for p in paths]
            if not all_paths:
                return []
            return random.sample(all_paths, min(k, len(all_paths)))

        # 语义检索：计算 Query 与 Candidate Paths 的 Cosine Similarity
        query_vec = self._text_to_vector(query)
        
        scored_candidates = []
        for cand in candidates:
            cand_vec = self.path_vectors.get(id(cand))
            if not cand_vec:
                # Fallback if not cached (should not happen)
                path_str = json.dumps(cand["path"], ensure_ascii=False)
                cand_vec = self._text_to_vector(path_str)
            
            score = self._cosine_sim(query_vec, cand_vec)
            scored_candidates.append((score, cand))
        
        # 按分数降序
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        top_k = [c[1] for c in scored_candidates[:k]]
        return top_k

def format_path_for_prompt(path_obj: List[Dict[str, Any]]) -> str:
    """将路径对象格式化为易读的字符串"""
    lines = []
    for step in path_obj:
        lines.append(f"  Step {step.get('step')}: {step.get('head')} --[{step.get('relation')}]--> {step.get('tail')} (Claim: {step.get('claim')})")
    return "\n".join(lines)

def format_gt_set(gt_paths: List[Dict[str, Any]]) -> str:
    """将检索到的 GT 路径集合格式化"""
    out = []
    for i, item in enumerate(gt_paths, 1):
        p_str = format_path_for_prompt(item["path"])
        out.append(f"参考路径 #{i} (Level {item['level']}):\n{p_str}")
    return "\n\n".join(out)

def parse_llm_score(response: str) -> Dict[str, float]:
    """解析 LLM 返回的 JSON 分数"""
    try:
        # 尝试清理 Markdown 代码块标记
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        
        data = json.loads(cleaned)
        return {
            "innovation": float(data.get("innovation_score", 0)),
            "feasibility": float(data.get("feasibility_score", 0)),
            "scientificity": float(data.get("scientificity_score", 0))
        }
    except Exception as e:
        logger.warning(f"解析评分失败: {e}. Response: {response}")
        return {"innovation": 0.0, "feasibility": 0.0, "scientificity": 0.0}

def evaluate_single_path(
    path: List[Dict[str, Any]], 
    gt_paths: List[Dict[str, Any]], 
    query: str, 
    discipline: str, 
    level: str,
    gen_query: str = ""
) -> Dict[str, float]:
    """调用 LLM 评估单条路径，并结合图指标"""
    
    # 1. 计算图指标 (客观)
    consistency_score = GraphMetricEvaluator.calculate_path_consistency(path, gt_paths)
    bridging_score = GraphMetricEvaluator.calculate_bridging_score(path)

    # 2. LLM 评估 (主观)
    path_str = format_path_for_prompt(path)
    gt_str = format_gt_set(gt_paths)
    
    if level == "L1":
        prompt_tmpl = PROMPT_EVAL_L1
        sys_prompt = prompt_tmpl.format(
            query=query,
            discipline=discipline,
            gt_paths=gt_str,
            gen_path=path_str
        )
    else:
        prompt_tmpl = PROMPT_EVAL_DEEP
        sys_prompt = prompt_tmpl.format(
            level_name="中层" if level == "L2" else "深层",
            level=level,
            query=query, # 上层 Query
            gen_query=gen_query, # 本层 Query
            gt_paths=gt_str,
            gen_path=path_str
        )

    messages = [{"role": "user", "content": sys_prompt}]
    
    try:
        resp = chat_completion_with_retry(messages, temperature=0.0) # 评估需要确定性
        scores = parse_llm_score(resp)
    except Exception as e:
        logger.error(f"LLM 评估请求失败: {e}")
        scores = {"innovation": 0.0, "feasibility": 0.0, "scientificity": 0.0}
    
    # 合并分数
    scores["consistency"] = consistency_score
    scores["bridging"] = bridging_score
    
    return scores

def main():
    parser = argparse.ArgumentParser(description="Evaluate Hypotheses using KG-based Ground Truth")
    parser.add_argument("--benchmark", required=True, help="Benchmark dataset JSON (用于构建 KG)")
    parser.add_argument("--predictions", required=True, help="Predictions JSON (待评估文件)")
    parser.add_argument("--output", default="eval_results.json", help="评估结果输出路径")
    parser.add_argument("--max-items", type=int, default=None, help="仅评估前 N 条")
    args = parser.parse_args()

    # 1. 构建全局知识图谱
    kg = GlobalKG(args.benchmark)

    # 2. 加载预测结果
    with open(args.predictions, 'r', encoding='utf-8') as f:
        predictions = json.load(f)
    
    if args.max_items:
        predictions = predictions[:args.max_items]

    results = []
    
    # 3. 逐条评估
    for item in tqdm(predictions, desc="Evaluating"):
        if "parsed" in item:
            parsed = item["parsed"]
            meta = parsed.get("meta", {})
            title = meta.get("title", "")
            primary_disc = meta.get("primary", "unknown")
            item_id = str(hash(title))
            hyp = parsed.get("假设", {})
            pred_paths_dict = {
                "L1": hyp.get("一级", []),
                "L2": hyp.get("二级", []),
                "L3": hyp.get("三级", [])
            }
        else:
            item_id = item.get("id")
            input_info = item.get("input", {})
            title = input_info.get("title", "")
            primary_disc = input_info.get("primary_discipline", "unknown")
            pred_paths_dict = item.get("ground_truth", {}).get("hypothesis_paths", {})

        # 假设 L1 Query 就是题目或者基于题目的查询
        l1_query = f"关于 {primary_disc} 的 {title} 的跨学科研究假设" 
        
        # 获取 Ground Truth Set (基于 L1 学科)
        gt_set = kg.retrieve_relevant_paths(primary_disc, l1_query, k=3)
        
        if not gt_set:
            logger.warning(f"ID {item_id}: 未找到任何相关 GT 路径 (学科: {primary_disc})")
            continue

        item_scores = defaultdict(list)
        
        # --- 评估 L1 ---
        l1_paths = normalize_paths_structure(pred_paths_dict.get("L1", []))
        for path in l1_paths:
            s = evaluate_single_path(path, gt_set, l1_query, primary_disc, "L1")
            for k, v in s.items():
                item_scores[f"L1_{k}"].append(v)
                
        # --- 评估 L2 ---
        # 这里的 Query 应该是 L2 Query，但 JSON 结构里可能没有显式存储 Query 只有 Path
        # 我们暂时用 "L2 Query" 占位，或者如果数据里有 query 字段则使用
        l2_paths = normalize_paths_structure(pred_paths_dict.get("L2", []))
        for path in l2_paths:
            s = evaluate_single_path(path, gt_set, l1_query, primary_disc, "L2", gen_query="[隐含的L2查询]")
            for k, v in s.items():
                item_scores[f"L2_{k}"].append(v)
                
        # --- 评估 L3 ---
        l3_paths = normalize_paths_structure(pred_paths_dict.get("L3", []))
        for path in l3_paths:
            s = evaluate_single_path(path, gt_set, l1_query, primary_disc, "L3", gen_query="[隐含的L3查询]")
            for k, v in s.items():
                item_scores[f"L3_{k}"].append(v)

        # 计算该 Item 的平均分
        avg_scores = {k: np.mean(v) if v else 0.0 for k, v in item_scores.items()}
        results.append({
            "id": item_id,
            "scores": avg_scores
        })

    # 4. 汇总输出
    print("\n=== Evaluation Summary ===")
    final_metrics = defaultdict(list)
    for r in results:
        for k, v in r["scores"].items():
            final_metrics[k].append(v)
            
    for metric, vals in final_metrics.items():
        print(f"{metric}: {np.mean(vals):.4f}")

    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nDetailed results saved to {args.output}")

if __name__ == "__main__":
    main()
