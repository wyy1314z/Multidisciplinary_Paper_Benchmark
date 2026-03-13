#!/usr/bin/env python3
"""
baseline/demo_showcase.py — 具体实例展示：同一篇论文 → 7 种方法的不同输出。

两种运行模式：
  1) --live   调用 LLM API 实际生成（需要 API Key）
  2) 默认     展示预构建的典型输出示例（无需 API）

用法:
    # 展示预构建示例（无需 API）
    python -m baseline.demo_showcase

    # 实际调用 API 生成
    python -m baseline.demo_showcase --live --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import json
import textwrap

# ═══════════════════════════════════════════════════════════════════════════
#  Demo 论文（paper_1.json 第一篇）
# ═══════════════════════════════════════════════════════════════════════════

DEMO_PAPER = {
    "paper_id": "demo_001",
    "title": "Resolving multi-image spatial lipidomic responses to inhaled "
             "toxicants by machine learning",
    "abstract": (
        "Regional responses to inhaled toxicants are essential to understand "
        "the pathogenesis of lung disease under exposure to air pollution. "
        "We evaluate the effect of combined allergen sensitization and ozone "
        "exposure on eliciting spatial differences in lipid distribution in "
        "the mouse lung that may contribute to ozone-induced exacerbations "
        "in asthma. We demonstrate the ability to normalize and segment high "
        "resolution mass spectrometry imaging data by applying established "
        "machine learning algorithms. Interestingly, our segmented regions "
        "overlap with histologically validated lung regions, enabling regional "
        "analysis across biological replicates. Our data reveal differences "
        "in the abundance of spatially distinct lipids, support the potential "
        "role of lipid saturation in healthy lung function, and highlight sex "
        "differences in regional lung lipid distribution following ozone "
        "exposure. Our study provides a framework for future mass spectrometry "
        "imaging experiments capable of relative quantification across "
        "biological replicates and expansion to multiple sample types, "
        "including human tissue."
    ),
    "primary_discipline": "生物学",
    "secondary_disciplines": ["Environmental Science",
                              "Biochemistry, Genetics and Molecular Biology"],
}

# ═══════════════════════════════════════════════════════════════════════════
#  7 种方法的典型输出示例
# ═══════════════════════════════════════════════════════════════════════════

EXAMPLE_OUTPUTS = {

# ── 1. IdeaBench ──────────────────────────────────────────────────────────
"IdeaBench": {
    "method": "IdeaBench-gpt-4o-mini",
    "format": "自由文本段落",
    "llm_calls": 1,
    "output": [
        "Building on the spatial lipidomics framework described, we hypothesize "
        "that integrating single-cell RNA sequencing with mass spectrometry "
        "imaging could reveal cell-type-specific lipid metabolic reprogramming "
        "in ozone-exposed lungs. Specifically, alveolar type II cells may "
        "exhibit distinct phospholipid desaturation patterns compared to "
        "macrophages, and these differences could serve as early biomarkers "
        "for pollution-induced asthma exacerbation. Testing this across "
        "multiple exposure timepoints would clarify the temporal dynamics "
        "of lipid-mediated inflammatory signaling in the lung microenvironment."
    ],
},

# ── 2. VanillaLLM ─────────────────────────────────────────────────────────
"VanillaLLM": {
    "method": "VanillaLLM-gpt-4o-mini",
    "format": "JSON 假设列表",
    "llm_calls": 1,
    "output": [
        "Machine learning-based spatial lipidomics can identify lipid "
        "biomarkers that predict individual susceptibility to ozone-induced "
        "asthma exacerbation before clinical symptoms appear.",
        "Sex-dependent differences in lung lipid saturation levels correlate "
        "with differential inflammatory cytokine profiles following ozone "
        "exposure.",
        "Transfer learning from mouse lung MSI data to human tissue samples "
        "can achieve >80% accuracy in identifying pathological lung regions "
        "without retraining.",
    ],
},

# ── 3. AI-Scientist ───────────────────────────────────────────────────────
"AI-Scientist": {
    "method": "AI-Scientist-gpt-4o-mini",
    "format": "结构化 Idea（含自评分）",
    "llm_calls": 1,
    "output": [
        {
            "Name": "LipidTimeMap",
            "Title": "Temporal Dynamics of Spatial Lipid Remodeling in "
                     "Pollution-Induced Lung Injury",
            "Hypothesis": "Longitudinal MSI at 6h, 24h, 72h, and 7d "
                          "post-ozone exposure will reveal a wave-like "
                          "propagation of lipid desaturation from bronchiolar "
                          "to alveolar regions.",
            "Experiment": "Time-series MALDI-MSI on mouse lung sections at "
                          "4 timepoints, with ML segmentation and spatial "
                          "autocorrelation analysis.",
            "Interestingness": 7,
            "Feasibility": 8,
            "Novelty": 6,
        },
    ],
},

# ── 4. SciMON ─────────────────────────────────────────────────────────────
"SciMON": {
    "method": "SciMON-gpt-4o-mini",
    "format": "Novelty-optimized 假设",
    "llm_calls": 1,
    "output": [
        "Unlike the current study's focus on lipid distribution, we propose "
        "that the spatial organization of lipid-protein complexes (lipid "
        "rafts) in lung epithelium undergoes phase-transition-like "
        "reorganization under ozone stress, and this can be detected by "
        "combining MSI with cryo-electron tomography.",
        "Rather than using ML for segmentation alone, a generative adversarial "
        "network trained on paired healthy/diseased MSI data could synthesize "
        "counterfactual lipid maps showing what a patient's lung would look "
        "like without pollution exposure.",
    ],
},

# ── 5. MOOSE-Chem ─────────────────────────────────────────────────────────
"MOOSE-Chem": {
    "method": "MOOSE-Chem-gpt-4o-mini",
    "format": "灵感驱动两阶段假设",
    "llm_calls": 2,
    "stage1_inspirations": [
        "ML algorithms can segment MSI data into histologically valid regions",
        "Lipid saturation plays a role in healthy lung function",
        "Sex differences exist in regional lipid distribution after ozone",
        "Framework enables cross-replicate quantification",
    ],
    "output": [
        "[Combining inspirations 1+3] The ML segmentation pipeline, when "
        "applied separately to male and female lung samples, will identify "
        "sex-specific lipid microdomains that are invisible in pooled "
        "analysis, revealing distinct inflammatory lipid mediator hotspots.",
        "[Combining inspirations 2+4] Cross-replicate quantification of "
        "lipid saturation indices across a dose-response ozone gradient "
        "will establish a quantitative threshold of lipid desaturation "
        "that predicts transition from reversible to irreversible lung injury.",
    ],
},

# ── 6. SciAgents ──────────────────────────────────────────────────────────
"SciAgents": {
    "method": "SciAgents-gpt-4o-mini",
    "format": "Multi-agent 协作精炼假设",
    "llm_calls": 3,
    "agent_trace": {
        "Ontologist": {
            "concepts": ["spatial lipidomics", "mass spectrometry imaging",
                         "ozone exposure", "lipid saturation",
                         "machine learning segmentation", "asthma exacerbation",
                         "sex differences"],
            "gaps": ["No temporal resolution", "No causal mechanism",
                     "Mouse-to-human translation unclear"],
        },
        "Scientist": "Proposed 3 hypotheses addressing identified gaps",
        "Critic": "Refined for specificity and testability",
    },
    "output": [
        "[Refined] Ozone-induced desaturation of phosphatidylcholine species "
        "(PC 32:0 → PC 32:1) in the bronchiolar region activates the "
        "ferroptosis pathway via lipid peroxidation, and this can be "
        "spatially mapped using the MSI-ML framework combined with "
        "ferroptosis marker (GPX4) immunostaining on serial sections.",
    ],
},

# ── 7. CrossDisc (我们的方法) ─────────────────────────────────────────────
"CrossDisc": {
    "method": "CrossDisc-gpt-4o-mini",
    "format": "多层级结构化知识路径 (L1/L2/L3)",
    "llm_calls": "5+ (概念×2 + 关系 + 查询 + 假设×3)",
    "pipeline_stages": [
        "概念抽取(两轮+grounding)",
        "关系抽取(evidence验证)",
        "查询生成(三级)",
        "假设路径生成(L1/L2/L3)",
        "实体对齐后处理",
    ],
    "extracted_concepts": {
        "主学科(生物学)": [
            "spatial lipidomics", "lipid saturation", "ozone exposure",
            "allergen sensitization", "asthma exacerbation",
            "phospholipid distribution", "alveolar region",
            "bronchiolar region", "sex differences",
        ],
        "辅学科(计算机科学)": [
            "mass spectrometry imaging", "machine learning segmentation",
            "image normalization", "biological replicate quantification",
        ],
    },
    "extracted_relations": [
        {
            "head": "machine learning segmentation",
            "relation": "enables_analysis_of",
            "tail": "spatial lipidomics",
            "evidence": "We demonstrate the ability to normalize and segment "
                        "high resolution mass spectrometry imaging data by "
                        "applying established machine learning algorithms.",
            "evidence_verified": True,
        },
        {
            "head": "ozone exposure",
            "relation": "induces_change_in",
            "tail": "phospholipid distribution",
            "evidence": "Our data reveal differences in the abundance of "
                        "spatially distinct lipids",
            "evidence_verified": True,
        },
        {
            "head": "lipid saturation",
            "relation": "contributes_to",
            "tail": "asthma exacerbation",
            "evidence": "support the potential role of lipid saturation in "
                        "healthy lung function",
            "evidence_verified": True,
        },
    ],
    "output": {
        "L1": [
            {
                "query": "机器学习方法如何帮助揭示吸入性毒物导致的肺部脂质空间分布异常？",
                "path": [
                    {"step": 1, "head": "臭氧暴露", "relation": "诱导改变",
                     "tail": "磷脂分布",
                     "claim": "臭氧暴露导致小鼠肺部磷脂的空间分布发生显著变化"},
                    {"step": 2, "head": "磷脂分布", "relation": "需要分析工具",
                     "tail": "机器学习分割",
                     "claim": "磷脂空间分布的高维数据需要机器学习算法进行有效分割和量化"},
                    {"step": 3, "head": "机器学习分割", "relation": "揭示机制",
                     "tail": "哮喘恶化",
                     "claim": "机器学习驱动的空间脂质组学分析可揭示臭氧诱导哮喘恶化的区域特异性脂质机制"},
                ],
                "summary": "臭氧暴露改变肺部磷脂空间分布，机器学习分割技术使得跨生物学重复的区域定量分析成为可能，从而揭示哮喘恶化的脂质介导机制",
            },
        ],
        "L2": [
            {
                "query": "脂质饱和度在臭氧暴露后的肺部区域差异中扮演什么角色？",
                "path": [
                    {"step": 1, "head": "臭氧暴露", "relation": "降低",
                     "tail": "脂质饱和度",
                     "claim": "臭氧暴露导致肺部特定区域的脂质饱和度显著降低"},
                    {"step": 2, "head": "脂质饱和度", "relation": "影响",
                     "tail": "肺泡区域",
                     "claim": "脂质饱和度的变化在肺泡区域和支气管区域呈现不同模式"},
                    {"step": 3, "head": "肺泡区域", "relation": "介导",
                     "tail": "过敏原致敏",
                     "claim": "肺泡区域脂质饱和度的降低可能增强过敏原致敏反应，加剧哮喘症状"},
                ],
                "summary": "臭氧暴露降低肺部脂质饱和度，该变化在肺泡区域尤为显著，可能通过增强过敏原致敏反应介导哮喘恶化",
            },
        ],
        "L3": [
            {
                "query": "性别差异如何影响臭氧暴露后的肺部脂质空间重塑？",
                "path": [
                    {"step": 1, "head": "性别差异", "relation": "调控",
                     "tail": "磷脂分布",
                     "claim": "雌雄小鼠在臭氧暴露后表现出不同的肺部磷脂空间分布模式"},
                    {"step": 2, "head": "磷脂分布", "relation": "决定",
                     "tail": "脂质饱和度",
                     "claim": "性别特异性的磷脂分布差异导致不同区域脂质饱和度的差异性响应"},
                    {"step": 3, "head": "脂质饱和度", "relation": "预测",
                     "tail": "哮喘恶化",
                     "claim": "性别依赖的区域脂质饱和度模式可作为臭氧诱导哮喘恶化易感性的生物标志物"},
                ],
                "summary": "雌雄小鼠对臭氧暴露的脂质空间响应存在显著差异，性别特异性的区域脂质饱和度模式可预测哮喘恶化风险",
            },
        ],
    },
},
}

def _wrap(text, width=88, indent="    "):
    """Wrap text with indent."""
    lines = textwrap.wrap(text, width=width - len(indent))
    return "\n".join(indent + l for l in lines)


def display_input():
    """展示输入论文。"""
    p = DEMO_PAPER
    print("=" * 90)
    print("  INPUT (同一篇论文，所有方法共用)")
    print("=" * 90)
    print(f"  Title:      {p['title']}")
    print(f"  Primary:    {p['primary_discipline']}")
    print(f"  Secondary:  {', '.join(p['secondary_disciplines'])}")
    print(f"  Abstract:")
    print(_wrap(p["abstract"]))
    print()


def display_baseline(name, data):
    """展示单个 baseline 的输出。"""
    print("-" * 90)
    print(f"  [{name}]  format={data['format']}  |  LLM calls={data['llm_calls']}")
    print("-" * 90)

    if name == "CrossDisc":
        _display_crossdisc(data)
        return

    if name == "AI-Scientist":
        for idea in data["output"]:
            print(f"    Name: {idea['Name']}")
            print(f"    Title: {idea['Title']}")
            print(f"    Hypothesis:")
            print(_wrap(idea["Hypothesis"], indent="      "))
            print(f"    Experiment:")
            print(_wrap(idea["Experiment"], indent="      "))
            print(f"    Self-scores: Interestingness={idea['Interestingness']}"
                  f"  Feasibility={idea['Feasibility']}"
                  f"  Novelty={idea['Novelty']}")
        print()
        return

    if name == "MOOSE-Chem":
        print("    Stage 1 — Extracted Inspirations:")
        for i, ins in enumerate(data["stage1_inspirations"]):
            print(f"      [{i}] {ins}")
        print("    Stage 2 — Combined Hypotheses:")
        for h in data["output"]:
            print(_wrap(h, indent="      "))
        print()
        return

    if name == "SciAgents":
        trace = data["agent_trace"]
        print(f"    Ontologist → concepts: {trace['Ontologist']['concepts'][:4]}...")
        print(f"    Ontologist → gaps: {trace['Ontologist']['gaps']}")
        print(f"    Scientist → {trace['Scientist']}")
        print(f"    Critic → {trace['Critic']}")
        print("    Final refined hypothesis:")
        for h in data["output"]:
            print(_wrap(h, indent="      "))
        print()
        return

    # IdeaBench / VanillaLLM / SciMON: 自由文本列表
    for i, h in enumerate(data["output"], 1):
        print(f"    Hypothesis {i}:")
        print(_wrap(h, indent="      "))
    print()


def _display_crossdisc(data):
    """展示 CrossDisc 的完整管线输出。"""
    print()
    print("    ┌─ Pipeline Stages: " + " → ".join(data["pipeline_stages"]))
    print("    │")

    # 概念
    print("    ├─ Extracted Concepts (两轮抽取 + grounding 过滤):")
    for disc, concepts in data["extracted_concepts"].items():
        print(f"    │    {disc}: {concepts}")

    # 关系
    print("    │")
    print("    ├─ Extracted Relations (evidence 原文验证):")
    for rel in data["extracted_relations"]:
        verified = "✓" if rel["evidence_verified"] else "✗"
        print(f"    │    {rel['head']} --[{rel['relation']}]--> {rel['tail']}")
        print(f"    │      evidence[{verified}]: \"{rel['evidence'][:70]}...\"")

    # 假设路径
    print("    │")
    print("    └─ Hypothesis Paths (结构化三元组链):")
    for level in ("L1", "L2", "L3"):
        paths = data["output"].get(level, [])
        for p in paths:
            print(f"         ── {level} ──")
            print(f"         Query: {p['query']}")
            for step in p["path"]:
                print(f"           Step {step['step']}: "
                      f"{step['head']} --[{step['relation']}]--> {step['tail']}")
                print(f"             claim: {step['claim']}")
            print(f"         Summary: {p['summary'][:80]}...")
            print()


def display_comparison_table():
    """展示方法对比总结表。"""
    print("=" * 90)
    print("  COMPARISON SUMMARY — 同一输入，不同输出的关键差异")
    print("=" * 90)
    print()
    header = (f"{'Method':<16}{'Output Form':<18}{'LLM Calls':<11}"
              f"{'Structured':<12}{'Evidence':<10}{'Multi-Level':<12}{'Concepts':<10}")
    print(header)
    print("-" * len(header))
    rows = [
        ("IdeaBench",    "free paragraph",  "N",   "—", "—", "—", "—"),
        ("VanillaLLM",   "sentence list",   "1",   "—", "—", "—", "—"),
        ("AI-Scientist", "idea+self-score", "1",   "—", "—", "—", "—"),
        ("SciMON",       "novelty-focused", "1",   "—", "—", "—", "—"),
        ("MOOSE-Chem",   "inspiration→hyp", "2",   "—", "—", "—", "partial"),
        ("SciAgents",    "agent-refined",   "3",   "—", "—", "—", "partial"),
        ("CrossDisc",    "KG triple chain", "5+",  "✓", "✓", "✓ L1/L2/L3", "✓ full"),
    ]
    for name, form, calls, struct, evid, multi, conc in rows:
        print(f"{name:<16}{form:<18}{calls:<11}{struct:<12}{evid:<10}{multi:<12}{conc:<10}")

    print()
    print("  Key Differentiators of CrossDisc:")
    print("  ┌──────────────────────────────────────────────────────────────────────┐")
    print("  │ 1. Structured: head→relation→tail 三元组链，可直接构建知识图谱      │")
    print("  │ 2. Evidence-grounded: 每条关系附带原文精确引用，可验证               │")
    print("  │ 3. Multi-level: L1(宏观)→L2(中观)→L3(微观) 层级递进假设             │")
    print("  │ 4. Concept-aligned: 假设实体严格对齐到已抽取概念表                  │")
    print("  │ 5. Cross-disciplinary: 显式建模主学科↔辅学科的知识桥接              │")
    print("  │ 6. Reproducible: 完整管线可自动化，适合大规模 GT 构建               │")
    print("  └──────────────────────────────────────────────────────────────────────┘")
    print()


def run_live_demo(model: str):
    """实际调用 API 生成。"""
    from baseline.common import PaperInput
    from baseline.run_comparison import build_adapters

    paper = PaperInput(**DEMO_PAPER)
    all_names = ["ideabench", "vanilla", "ai_scientist", "scimon",
                 "moose_chem", "sciagents", "crossdisc"]
    adapters = build_adapters(all_names, model)

    display_input()

    for adapter in adapters:
        print(f"\n  Running {adapter.name}...")
        output = adapter.generate(paper, num_hypotheses=3)
        print(f"  Done in {output.elapsed_seconds:.1f}s")
        print("-" * 90)
        print(f"  [{adapter.name}]")
        print("-" * 90)
        if output.structured_paths:
            print(json.dumps(output.to_dict(), ensure_ascii=False, indent=2))
        else:
            for i, h in enumerate(output.free_text_hypotheses, 1):
                print(f"    Hypothesis {i}:")
                print(_wrap(h, indent="      "))
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Actually call LLM API (requires API key)")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    if args.live:
        run_live_demo(args.model)
        return

    # 展示预构建示例
    display_input()

    order = ["IdeaBench", "VanillaLLM", "AI-Scientist", "SciMON",
             "MOOSE-Chem", "SciAgents", "CrossDisc"]
    for name in order:
        display_baseline(name, EXAMPLE_OUTPUTS[name])

    display_comparison_table()


if __name__ == "__main__":
    main()
