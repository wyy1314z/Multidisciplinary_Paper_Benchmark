# crossdisc_extractor/__init__.py
"""
Cross-disciplinary benchmark extractor (multi-stage LLM pipeline).

Stages:
1) struct: meta + 概念 + 跨学科关系
2) query: 按辅助学科分类 + 查询(三级)
3) hypothesis: 假设(三级知识路径 + 总结)
"""
