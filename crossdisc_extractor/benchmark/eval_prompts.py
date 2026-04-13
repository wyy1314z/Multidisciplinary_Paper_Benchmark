from __future__ import annotations

# 评估 L1 (浅层) 假设路径的 Prompt
# 重点：创新性、可行性、科学性
PROMPT_EVAL_L1 = """你是一个跨学科研究评估专家。
你的任务是评估模型生成的“浅层跨学科假设路径”（Level 1 Hypothesis）。

【评估依据】
我们基于一级查询（Query L1）所属的学科，从知识图谱中检索到了一组“Ground Truth 参考路径”（由该学科的高质量文献生成）。
你需要对比“模型生成的路径”和“参考路径集合”，对模型生成的路径进行打分。

【输入信息】
1. **查询 (Query L1)**: {query}
2. **查询主学科**: {discipline}
3. **参考路径集合 (Ground Truth)**:
{gt_paths}

4. **模型生成的路径 (Generated)**:
{gen_path}

【评分维度】(0-10分)
1. **创新性 (Innovation)**: 
   - 该路径是否提出了参考路径中未覆盖的新颖联系？
   - 是否在合理范围内跨越了学科边界？
   - (注意：完全照搬参考路径不算创新，得分应较低；但在参考路径基础上的合理外推算创新)
   
2. **可行性 (Feasibility)**:
   - 该路径提出的联系在逻辑上是否成立？
   - 是否存在明显的逻辑断裂或不可能的跳跃？
   
3. **科学性 (Scientificity)**:
   - 涉及的术语和概念使用是否准确？
   - 是否符合科学事实（基于你的常识和参考路径的上下文）？

【输出格式】
请输出一个 JSON 对象，包含以下字段：
{{
    "innovation_score": <float>,
    "feasibility_score": <float>,
    "scientificity_score": <float>,
    "reason": "<简短的评分理由>"
}}
只输出 JSON，不要输出其他内容。
"""

# 评估假设路径的现实可行性 (Feasibility)
# 与 testability 区分：
# - testability 关注“能否被检验/证伪”
# - feasibility 关注“在当前资源和方法条件下能否真正执行”
PROMPT_FEASIBILITY = """你是一位跨学科科研评估专家。请评估以下研究假设路径的现实可行性（Feasibility）。

【假设路径】
{hypothesis_path}

【评分原则】
Feasibility 不等于逻辑是否通顺，也不等于是否可证伪。
它专门评估：在当前可获得的数据、方法、资源和验证条件下，这条假设是否现实可执行。

【评分维度】(每项 0-10 分)
1. **数据可行性 (Data Feasibility)**:
   - 验证该假设所需的数据、样本或文献证据是否现实可获得？
   - 10分: 公开或常规实验/观测数据即可支持
   - 5分: 数据可获得，但需要较高成本收集或整合
   - 0分: 关键数据几乎不可得，或依赖不存在的数据来源

2. **方法可行性 (Method Feasibility)**:
   - 验证该假设所需的方法、模型、实验流程是否已经存在且成熟？
   - 10分: 可直接采用成熟方法实施
   - 5分: 需要组合多种专业方法，但总体可行
   - 0分: 严重依赖尚不成熟或不存在的方法

3. **资源可行性 (Resource Feasibility)**:
   - 所需设备、计算、时间和跨学科协作成本是否合理？
   - 10分: 常规研究团队即可完成
   - 5分: 需要较强资源支持，但现实中可组织
   - 0分: 需要极端昂贵、稀缺或几乎不可获得的资源

4. **验证准备度 (Validation Readiness)**:
   - 是否能够提出一个清晰、现实的最小验证方案？
   - 10分: 可直接形成最小可行验证方案
   - 5分: 需要进一步细化后可验证
   - 0分: 尚无法落到可执行验证步骤

【输出格式】
请输出一个 JSON 对象，包含以下字段：
{{{{
    "data_feasibility": <float>,
    "method_feasibility": <float>,
    "resource_feasibility": <float>,
    "validation_readiness": <float>,
    "minimum_viable_validation": "<一句话说明最小可行验证方案>",
    "reason": "<简短说明主要瓶颈>"
}}}}
只输出 JSON，不要输出其他内容。
"""

# 评估假设路径的可验证性 (Testability)
# 参考: Popper (1959) 可证伪性原则 + Si et al. (2024) Expected Effectiveness
PROMPT_TESTABILITY = """你是一位实验设计专家。请评估以下跨学科研究假设路径的可验证性。

【假设路径】
{hypothesis_path}

【评分维度】(每项 0-10 分)
1. **具体性 (Specificity)**:
   - 假设是否足够具体，可以形成精确的研究问题？
   - 10分: 可直接设计对照实验
   - 5分: 需要进一步细化才能实验
   - 0分: 过于模糊，无法操作化

2. **可测量性 (Measurability)**:
   - 假设中涉及的变量是否可以测量？
   - 现有技术手段能否获取相关数据？

3. **可证伪性 (Falsifiability)**:
   - 是否存在可能的实验结果能否定该假设？
   - 如果任何结果都不能否定它，说明它不是好的科学假设

4. **资源可行性 (Resource Feasibility)**:
   - 验证该假设需要的实验资源是否合理？
   - 10分: 标准实验室即可验证
   - 5分: 需要专业设备但可获取
   - 0分: 需要尚不存在的技术

【输出格式】
请输出一个 JSON 对象，包含以下字段：
{{{{
    "specificity": <float>,
    "measurability": <float>,
    "falsifiability": <float>,
    "resource_feasibility": <float>,
    "suggested_experiment": "<简述一个验证方案>"
}}}}
只输出 JSON，不要输出其他内容。
"""
# 重点：逻辑深度、跨学科融合度
PROMPT_EVAL_DEEP = """你是一个跨学科研究评估专家。
你的任务是评估模型生成的“{level_name}跨学科假设路径”（Level {level} Hypothesis）。
这一层级的路径通常涉及更复杂的机制解释或多步推导。

【输入信息】
1. **上层查询**: {query}
2. **本层查询 (Generated Query)**: {gen_query}
3. **参考路径集合 (Ground Truth)**:
{gt_paths}

4. **模型生成的路径 (Generated)**:
{gen_path}

【评分维度】(0-10分)
1. **创新性 (Innovation)**: 该路径是否揭示了深层的机制联系，而不仅仅是表面关联？
2. **可行性 (Feasibility)**: 推理链条（Step 1 -> Step 2 -> Step 3）是否严密？
3. **科学性 (Scientificity)**: 概念使用是否专业、准确？

【输出格式】
请输出一个 JSON 对象，包含以下字段：
{{
    "innovation_score": <float>,
    "feasibility_score": <float>,
    "scientificity_score": <float>,
    "reason": "<简短的评分理由>"
}}
只输出 JSON，不要输出其他内容。
"""
