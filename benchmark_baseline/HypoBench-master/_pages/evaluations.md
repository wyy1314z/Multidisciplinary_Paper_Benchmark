---
layout: page
permalink: /evaluations/
title: Evaluation Methods
---

HypoBench focuses on evaluating hypothesis generation capabilities through multiple dimensions:

### Explanatory Power

The primary focus of our evaluation is on the explanatory power of generated hypotheses:

#### Utility-driven Evaluation
We evaluate how well the generated hypotheses help language models make accurate predictions:

- **Classification Tasks**: Hypotheses are used to guide models in making predictions on test examples.
- **Data Splits**: We test on both in-distribution (IND) datasets and out-of-distribution (OOD) datasets to assess generalization.
- **Metric**: Classification accuracy and F1 scores.

#### Ground Truth Hypothesis Discovery Rate (HDR)
For synthetic datasets where we know the true underlying hypotheses:

- We measure how well generated hypotheses recover the ground-truth hypotheses.
- This includes both feature discovery (identifying relevant factors) and relationship correctness (understanding how these factors relate to outcomes).

### Interestingness

We provide preliminary metrics for hypothesis "interestingness" - spliting into three dimensions: Novelty, Plausibility, and Clarity, (for real datasets only).

- We use LLM-based qualitative assessments.
- This helps capture aspects beyond pure explanatory power.

## Key Capabilities Benchmarked

HypoBench evaluates three core capabilities necessary for effective hypothesis generation:

1. **Inductive reasoning**: Proposing possible theories for given observations
2. **Abstraction and communication**: Expressing hypotheses in clear, understandable language
3. **Synthesis**: Integrating new observations with existing knowledge

For more details on our evaluation methodology, please refer to our <a href="https://arxiv.org/abs/2504.11524" target="_blank">paper</a>.
For evaluation code, please visit our <a href="https://github.com/ChicagoHAI/HypoBench-code" target="_blank">GitHub repository</a>.