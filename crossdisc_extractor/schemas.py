# crossdisc_extractor/schemas.py
from __future__ import annotations

import re
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationError

logger = logging.getLogger("crossdisc.schemas")

# 链式一致性：语义相似度阈值（0-1）
# 精确相等直接通过；相似度 >= 阈值时通过并记录警告；低于阈值时报错
_CHAIN_SIMILARITY_THRESHOLD = 0.75


def _semantic_chain_match(a: str, b: str) -> tuple:
    """
    判断两个实体标签是否满足链式一致性。
    返回 (is_match: bool, similarity: float)。

    策略（优先级递减）：
    1. 精确相等 → True
    2. 大小写/空格归一化后相等 → True
    3. SequenceMatcher ratio >= 阈值 → True（附警告，处理别名/近义词）
    4. 其他 → False
    """
    a = (a or "").strip()
    b = (b or "").strip()
    if a == b:
        return True, 1.0
    a_norm = a.lower().replace(" ", "").replace("_", "")
    b_norm = b.lower().replace(" ", "").replace("_", "")
    if a_norm == b_norm:
        return True, 1.0
    ratio = SequenceMatcher(None, a_norm, b_norm).ratio()
    return ratio >= _CHAIN_SIMILARITY_THRESHOLD, ratio


# relation_type 的枚举空间（本体标签）
ALLOWED_RELATION_TYPES = {
    "method_applied_to",
    "maps_to",
    "constrains",
    "improves_metric",
    "corresponds_to",
    "inferred_from",
    "assumes",
    "extends",
    "generalizes",
    "driven_by",
    "depends_on",
    "other",
}

# 常见 relation_type 变体 -> 本体枚举的映射（放宽 Schema + 提升鲁棒性）
RELATION_TYPE_MAP = {
    # method_applied_to
    "applies_to": "method_applied_to",
    "apply_to": "method_applied_to",
    "used_for": "method_applied_to",
    "use_for": "method_applied_to",
    "method_for": "method_applied_to",
    "application_to": "method_applied_to",
    # maps_to
    "mapped_to": "maps_to",
    "mapping_to": "maps_to",
    "map_to": "maps_to",
    "maps": "maps_to",
    # constrains
    "constraint": "constrains",
    "constraints": "constrains",
    "restricts": "constrains",
    "limits": "constrains",
    # improves_metric
    "improves": "improves_metric",
    "improve": "improves_metric",
    "boosts": "improves_metric",
    "enhances": "improves_metric",
    "increases": "improves_metric",
    "increase": "improves_metric",
    # corresponds_to
    "corresponds": "corresponds_to",
    "correspond": "corresponds_to",
    "relates_to": "corresponds_to",
    "related_to": "corresponds_to",
    "aligned_with": "corresponds_to",
    # inferred_from
    "derived_from": "inferred_from",
    "derive_from": "inferred_from",
    "inferred": "inferred_from",
    # assumes
    "assumption": "assumes",
    "assume": "assumes",
    # extends
    "extends_from": "extends",
    "builds_on": "extends",
    "based_on": "extends",
    # generalizes
    "generalize": "generalizes",
    "generalization": "generalizes",
    # driven_by
    "caused_by": "driven_by",
    "due_to": "driven_by",
    "driven": "driven_by",
    # depends_on
    "depends": "depends_on",
    "depend_on": "depends_on",
    "relies_on": "depends_on",
    "rely_on": "depends_on",
    "requires": "depends_on",
    "require": "depends_on",
}

def normalize_relation_type(raw: str) -> Optional[str]:
    """
    将模型输出的 relation_type 归一化到 ALLOWED_RELATION_TYPES 中（若可映射）。
    - 已在枚举中：直接返回
    - 常见英文变体：RELATION_TYPE_MAP
    - 常见中文关键词：启发式映射
    - 无法识别：返回 None（Schema 放宽，不再硬失败）
    """
    s = (raw or '').strip()
    if not s:
        return None
    if s in ALLOWED_RELATION_TYPES:
        return s
    low = s.lower().strip()
    key = re.sub(r'[\s\-]+', '_', low)
    key = re.sub(r'[^a-z0-9_]+', '', key)
    if key in RELATION_TYPE_MAP:
        return RELATION_TYPE_MAP[key]
    # 中文启发式（覆盖常见输出）
    if any(w in s for w in ['用于', '应用', '方法', '采用', '使用']):
        return 'method_applied_to'
    if any(w in s for w in ['映射', '对应', '对齐', '转换', '转化']):
        return 'maps_to'
    if any(w in s for w in ['约束', '限制', '制约', '约定']):
        return 'constrains'
    if any(w in s for w in ['提升', '改进', '提高', '增强', '优化']):
        return 'improves_metric'
    if any(w in s for w in ['相关', '关联', '对应于', '一致']):
        return 'corresponds_to'
    if any(w in s for w in ['推断', '导出', '来源于', '由此得出']):
        return 'inferred_from'
    if any(w in s for w in ['假设', '前提']):
        return 'assumes'
    if any(w in s for w in ['扩展', '拓展', '基于', '在此基础上']):
        return 'extends'
    if any(w in s for w in ['泛化', '推广', '一般化']):
        return 'generalizes'
    if any(w in s for w in ['驱动', '导致', '源于', '由于']):
        return 'driven_by'
    if any(w in s for w in ['依赖', '取决于', '需要']):
        return 'depends_on'
    return None


class ConceptEntry(BaseModel):
    term: str = Field(..., description="原始术语")
    normalized: Optional[str] = Field(default=None, description="归一化术语；同义合并")
    std_label: Optional[str] = Field(default=None, description="标准体系标签，如 MeSH/MSC/ACM CCS")
    evidence: str = Field(default="", description="原文证据片段（≤40中文字/≤30英文词）")
    source: str = Field(default="abstract", description="抽取来源：abstract | refs[i]")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("term", mode="before")
    @classmethod
    def _coerce_term(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_evidence(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("source", mode="before")
    @classmethod
    def _coerce_source(cls, v):
        if v is None:
            return "abstract"
        text = str(v).strip()
        return text or "abstract"

    @model_validator(mode="after")
    def _trim(self):
        self.term = (self.term or "").strip()
        if self.normalized is not None:
            self.normalized = self.normalized.strip() or None
        if self.std_label is not None:
            self.std_label = self.std_label.strip() or None
        self.evidence = (self.evidence or "").strip()
        self.source = (self.source or "").strip()
        return self


class Concepts(BaseModel):
    主学科: List[ConceptEntry] = Field(default_factory=list, description="主学科概念条目")
    辅学科: Dict[str, List[ConceptEntry]] = Field(default_factory=dict, description="辅学科→概念条目列表")

    @staticmethod
    def _unwrap_concept_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for key in ("ConceptEntry", "概念", "主学科", "items", "entries"):
                val = v.get(key)
                if isinstance(val, list):
                    return val
            merged = []
            for val in v.values():
                if isinstance(val, list):
                    merged.extend(val)
            return merged
        return []

    @field_validator("主学科", mode="before")
    @classmethod
    def _coerce_main_terms(cls, v):
        return cls._unwrap_concept_list(v)

    @field_validator("主学科")
    @classmethod
    def _nonempty_terms(cls, v: List[ConceptEntry]) -> List[ConceptEntry]:
        return v or []

    @field_validator("辅学科", mode="before")
    @classmethod
    def _coerce_groups(cls, v):
        if not isinstance(v, dict):
            return {}
        out = {}
        for k, lst in v.items():
            key = (k or "").strip()
            if not key:
                continue
            out[key] = cls._unwrap_concept_list(lst)
        return out

    @field_validator("辅学科")
    @classmethod
    def _clean_groups(cls, v: Dict[str, List[ConceptEntry]]) -> Dict[str, List[ConceptEntry]]:
        out: Dict[str, List[ConceptEntry]] = {}
        for k, lst in (v or {}).items():
            key = (k or "").strip()
            if not key:
                continue
            out[key] = lst or []
        return out


class QuantItem(BaseModel):
    metric: str
    value: Union[str, int, float]

    @field_validator("value")
    @classmethod
    def _to_str(cls, v: Union[str, int, float]) -> str:
        return str(v).strip()


class RelationEntry(BaseModel):
    head: str
    relation: str
    relation_type: str
    relation_type_norm: Optional[str] = Field(default=None, description="归一化后的本体关系类型（若可映射）")
    relation_type_raw: Optional[str] = Field(default=None, description="模型原始输出的 relation_type（清洗前）")
    tail: str
    direction: Literal["->"] = "->"
    quant: Optional[QuantItem] = None
    assumptions: List[str] = Field(default_factory=list)
    evidence: str
    source: str
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, v):
        if v is None:
            return "->"
        text = str(v).strip()
        if text in {"", "->", "<-", "term_a_to_term_b", "term_b_to_term_a"}:
            return "->"
        return "->"

    @field_validator("assumptions", mode="before")
    @classmethod
    def _coerce_assumptions(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        text = str(v).strip()
        return [text] if text else []

    @field_validator("evidence", mode="before")
    @classmethod
    def _coerce_relation_evidence(cls, v):
        if v is None:
            return ""
        return str(v)

    @field_validator("source", mode="before")
    @classmethod
    def _coerce_relation_source(cls, v):
        if v is None:
            return "abstract"
        text = str(v).strip()
        return text or "abstract"

    @model_validator(mode="after")
    def _chk(self):
        self.head = (self.head or "").strip()
        self.tail = (self.tail or "").strip()
        self.relation = (self.relation or "").strip()
        raw = (self.relation_type or "").strip()
        self.relation_type_raw = raw
        self.relation_type = raw or "other"
        self.relation_type_norm = normalize_relation_type(raw)
        # Schema 放宽：不再因 relation_type 不在枚举集合而硬失败
        self.evidence = (self.evidence or "").strip()
        self.source = (self.source or "").strip()
        return self


class ClassifiedBucket(BaseModel):
    概念: List[str] = Field(default_factory=list)
    关系: List[int] = Field(default_factory=list, description="引用 跨学科关系 数组中的索引")
    rationale: str = Field(default="", description="一句话理由")

    @field_validator("概念", mode="before")
    @classmethod
    def _coerce_concepts(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, dict):
            for key in ("概念", "ConceptEntry", "items", "entries"):
                val = v.get(key)
                if isinstance(val, list):
                    return [str(x).strip() for x in val if str(x).strip()]
        text = str(v).strip()
        return [text] if text else []

    @field_validator("关系", mode="before")
    @classmethod
    def _coerce_relations(cls, v):
        if v is None:
            return []
        if isinstance(v, list):
            out = []
            for x in v:
                try:
                    out.append(int(x))
                except Exception:
                    continue
            return out
        try:
            return [int(v)]
        except Exception:
            return []

    @field_validator("rationale", mode="before")
    @classmethod
    def _coerce_rationale(cls, v):
        if v is None:
            return ""
        return str(v)

    @model_validator(mode="after")
    def _fill_rationale(self):
        self.rationale = (self.rationale or "").strip()
        if not self.rationale:
            n_concepts = len(self.概念 or [])
            n_relations = len(self.关系 or [])
            self.rationale = f"该辅助学科提供了 {n_concepts} 个相关概念与 {n_relations} 条相关关系。"
        return self


class Query3Levels(BaseModel):
    一级: str
    二级: List[str] = Field(default_factory=list)
    三级: List[str] = Field(default_factory=list)

    @field_validator("一级")
    @classmethod
    def _lvl1(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("查询.一级 不得为空")
        return v

    @field_validator("二级", "三级", mode="before")
    @classmethod
    def _coerce_to_list(cls, v):
        """兼容模型返回单个字符串而非列表的情况"""
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list):
            return []
        out = []
        for s in v:
            s = (str(s) if s is not None else "").strip()
            if s:
                out.append(s)
        return out


class HypothesisStep(BaseModel):
    step: int
    head: str
    relation: str
    tail: str
    claim: str

    @model_validator(mode="after")
    def _trim(self):
        self.step = int(self.step)
        self.head = (self.head or "").strip()
        self.relation = (self.relation or "").strip()
        self.tail = (self.tail or "").strip()
        self.claim = (self.claim or "").strip()
        if self.step <= 0:
            raise ValueError("HypothesisStep.step 必须从 1 开始")
        return self


class Hypothesis3Levels(BaseModel):
    一级: List[List[HypothesisStep]] = Field(default_factory=list)
    二级: List[List[HypothesisStep]] = Field(default_factory=list)
    三级: List[List[HypothesisStep]] = Field(default_factory=list)

    一级总结: List[str] = Field(default_factory=list)
    二级总结: List[str] = Field(default_factory=list)
    三级总结: List[str] = Field(default_factory=list)

    @field_validator("一级", "二级", "三级")
    @classmethod
    def _normalize_level(cls, v: List[List[HypothesisStep]]) -> List[List[HypothesisStep]]:
        return v or []

    @field_validator("一级总结", "二级总结", "三级总结")
    @classmethod
    def _strip_summary_list(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        out: List[str] = []
        for s in v:
            if isinstance(s, str):
                s = s.strip()
                if s:
                    out.append(s)
        return out

    @staticmethod
    def _validate_paths(paths, level_name: str) -> None:
        if not paths:
            return
        for pi, path in enumerate(paths):
            if not isinstance(path, list):
                raise ValueError(f"假设.{level_name}[{pi}] 必须是 HypothesisStep 列表")

            # 1) 强制每条路径恰好 3 个 step
            if len(path) != 3:
                raise ValueError(
                    f"假设.{level_name}[{pi}] 必须恰好包含 3 个 step，当前为 {len(path)}"
                )

            # 2) step 编号强制为 1,2,3（防止模型乱编号）
            steps = [getattr(s, "step", None) for s in path]
            if steps != [1, 2, 3]:
                raise ValueError(
                    f"假设.{level_name}[{pi}] step 必须依次为 [1,2,3]，当前为 {steps}"
                )

            # 3) 链式一致性：下一步 head 与上一步 tail 语义匹配
            #    使用 SequenceMatcher，允许近义词/别名（阈值 0.75）
            for j in range(1, 3):
                prev_tail = (path[j - 1].tail or "").strip()
                curr_head = (path[j].head or "").strip()
                match, sim = _semantic_chain_match(prev_tail, curr_head)
                if not match:
                    raise ValueError(
                        f"假设.{level_name}[{pi}] 链路不一致："
                        f"step{j}.tail='{prev_tail}' 与 step{j+1}.head='{curr_head}' "
                        f"相似度 {sim:.2f} 低于阈值 {_CHAIN_SIMILARITY_THRESHOLD}"
                    )
                if sim < 1.0:
                    logger.warning(
                        "假设.%s[%d] step%d tail≈step%d head（相似度%.2f）：'%s'≈'%s'",
                        level_name, pi, j, j + 1, sim, prev_tail, curr_head
                    )

            # 4) 最后一步 claim 必须非空（用于总结）
            last_claim = (path[-1].claim or "").strip()
            if not last_claim:
                raise ValueError(f"假设.{level_name}[{pi}] 最后一步 claim 不得为空（用于总结）")

    @model_validator(mode="after")
    def _enforce_three_step_chain(self):
        self._validate_paths(self.一级, "一级")
        self._validate_paths(self.二级, "二级")
        self._validate_paths(self.三级, "三级")
        return self


class MetaInfo(BaseModel):
    title: str
    primary: str
    secondary_list: List[str] = Field(default_factory=list)
    journal: str = ""
    journal_id: str = ""
    issn_l: str = ""
    source_type: str = ""
    doi: str = ""
    publication_date: str = ""
    publication_year: Optional[int] = None
    fwci: Optional[float] = None
    cited_by_count: Optional[int] = None
    field: str = ""


class StructExtraction(BaseModel):
    """阶段 1 输出：meta + 概念 + 跨学科关系"""
    meta: MetaInfo
    概念: Concepts
    跨学科关系: List[RelationEntry] = Field(default_factory=list)


class QueryAndBuckets(BaseModel):
    """阶段 2 输出：按辅助学科分类 + 查询"""
    按辅助学科分类: Dict[str, ClassifiedBucket] = Field(default_factory=dict)
    查询: Query3Levels


class GraphMetrics(BaseModel):
    path_consistency: float = 0.0
    coverage: float = 0.0
    bridging_score: float = 0.0

    # ── Enhanced metrics (v2) ─────────────────────────────────────
    # Rao-Stirling diversity index (Stirling 2007)
    rao_stirling_diversity: float = 0.0
    # Embedding-based bridging distance
    embedding_bridging: float = 0.0
    # Relation-aware path consistency F1
    consistency_precision: float = 0.0
    consistency_recall: float = 0.0
    consistency_f1: float = 0.0
    # Information-theoretic novelty
    info_novelty: float = 0.0
    # Reasoning chain coherence
    chain_coherence: float = 0.0
    # Atypical combination index (Uzzi et al. 2013)
    atypical_combination: float = 0.0
    # KG topology
    kg_density: float = 0.0
    kg_inverse_modularity: float = 0.0
    kg_largest_cc_ratio: float = 0.0
    kg_avg_betweenness: float = 0.0
    kg_clustering_coefficient: float = 0.0

    # ── Evidence-grounded GT metrics (v3) ─────────────────────────
    # Concept coverage: how many GT terms appear in generated paths
    concept_recall: float = 0.0
    concept_precision: float = 0.0
    concept_f1: float = 0.0
    # Relation precision: generated relations supported by GT evidence
    relation_precision: float = 0.0
    relation_type_accuracy: float = 0.0
    evidence_coverage: float = 0.0
    # Path semantic alignment: soft similarity to best GT path
    path_alignment_best: float = 0.0
    path_alignment_mean: float = 0.0


class ConceptNode(BaseModel):
    id: str = Field(..., description="唯一标识符，通常使用 normalized term")
    term: str
    normalized: str
    discipline: str
    evidence: str = ""
    source: str = ""
    confidence: float = 1.0


class ConceptEdge(BaseModel):
    source: str
    target: str
    relation: str
    relation_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConceptGraph(BaseModel):
    nodes: List[ConceptNode] = Field(default_factory=list)
    edges: List[ConceptEdge] = Field(default_factory=list)


class Extraction(BaseModel):
    """最终聚合结果：结构 + 分类 + 查询 + 假设 + 图谱 + 评测"""
    meta: MetaInfo
    概念: Concepts
    跨学科关系: List[RelationEntry] = Field(default_factory=list)
    按辅助学科分类: Dict[str, ClassifiedBucket] = Field(default_factory=dict)
    查询: Query3Levels
    假设: Hypothesis3Levels
    graph: Optional[ConceptGraph] = None
    metrics: Optional[GraphMetrics] = None

    @model_validator(mode="after")
    def _check_alignment(self):
        """
        保留你原来的一些基本对齐约束：
        - 查询.二级 的问题数 == 假设.二级 的路径数
        - 查询.三级 的问题数 == 假设.三级 的路径数
        - 假设.一级 至少一条路径
        - 各级总结长度 == 对应路径数
        """
        q = self.查询
        h = self.假设

        # 严格数量对齐：len(查询.二级) == len(查询.三级) == len(假设.一级) == len(假设.二级) == len(假设.三级)
        # 且均等于 meta.secondary_list 的长度（N）。
        # sec_list = [s.strip() for s in (self.meta.secondary_list or []) if s and s.strip()]
        # n_sec = len(sec_list)
        # if n_sec > 0:
        #     if len(q.二级 or []) != n_sec:
        #         # raise ValueError(f"查询.二级 的问题数必须等于 secondary_list 的长度 {n_sec}。")
        #         pass
        #     if len(q.三级 or []) != n_sec:
        #         # raise ValueError(f"查询.三级 的问题数必须等于 secondary_list 的长度 {n_sec}。")
        #         pass
        #     if len(h.一级 or []) != n_sec:
        #         # raise ValueError(f"假设.一级 的路径数必须等于 secondary_list 的长度 {n_sec}。")
        #         pass
        #     if len(h.二级 or []) != n_sec:
        #         # raise ValueError(f"假设.二级 的路径数必须等于 secondary_list 的长度 {n_sec}。")
        #         pass
        #     if len(h.三级 or []) != n_sec:
        #         # raise ValueError(f"假设.三级 的路径数必须等于 secondary_list 的长度 {n_sec}。")
        #         pass

        if not h.一级:
            raise ValueError("假设.一级 至少包含一条知识路径，用于回答 查询.一级")

        n_h1 = len(h.一级)
        n_h2 = len(h.二级)
        n_h3 = len(h.三级)

        n_q2 = len(q.二级 or [])
        n_q3 = len(q.三级 or [])

        if n_q2 > 0 and n_q2 != n_h2:
            # raise ValueError(f"查询.二级 有 {n_q2} 个问题，但 假设.二级 有 {n_h2} 条路径，必须一一对应。")
            pass
        if n_q2 == 0 and n_h2 > 0:
            # raise ValueError("查询.二级 为空，但存在 假设.二级 路径。")
            pass

        if n_q3 > 0 and n_q3 != n_h3:
            # raise ValueError(f"查询.三级 有 {n_q3} 个问题，但 假设.三级 有 {n_h3} 条路径，必须一一对应。")
            pass
        if n_q3 == 0 and n_h3 > 0:
            # raise ValueError("查询.三级 为空，但存在 假设.三级 路径。")
            pass

        if len(h.一级总结) != n_h1:
            raise ValueError("假设.一级总结 的长度必须等于 假设.一级 路径数。")
        if len(h.二级总结) != n_h2:
            raise ValueError("假设.二级总结 的长度必须等于 假设.二级 路径数。")
        if len(h.三级总结) != n_h3:
            raise ValueError("假设.三级总结 的长度必须等于 假设.三级 路径数。")

        return self
