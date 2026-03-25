---
---

const renameCategory = {
  "deceptive_reviews": "Deceptive Reviews Detection",
  "llamagc_detect": "Llama-generated Content Detection",
  "gptgc_detect": "GPT-generated Content Detection",
  "persuasive_pairs": "Persuasive Argument Prediction",
  "dreaddit": "Mental Stress Detection",
  "headline_binary": "News Headline Engagement",
  "retweet": "Retweets",
  "citations": "Paper Citations",
};
/**************************************************
 * 1) Define your multi-level categories object.
 *    EXACTLY match the Task values in your CSVs.
 *    Now tasks use underscores, not slashes.
 **************************************************/
const categories = {
  All: null,  // Means no filtering in theory, but we skip in UI
  deceptive_reviews: {
    "main": "Deceptive Reviews Detection",
  },
  llamagc_detect: {
    "main": "Llama-generated Content Detection",
  },
  gptgc_detect: {
    "main": "GPT-generated Content Detection",
  },
  persuasive_pairs: {
    "main": "Persuasive Argument Prediction",
  },
  dreaddit: {
    "main": "Mental Stress Detection",
  },
  headline_binary: {
    "main": "News Headline Engagement",
  },
  retweet: {
    "main": "Retweets",
  },
  citations: {
    "main": [
      "journal_same_same_journal_health",
      "journal_same_same_journal_nips",
      "journal_same_same_journal_radiology",
    ],
    "cross": [
      "journal_cross_cross_journal_health_nips",
      "journal_cross_cross_journal_health_radiology",
      "journal_cross_cross_journal_nips_health",
      "journal_cross_cross_journal_nips_radiology",
      "journal_cross_cross_journal_radiology_health",
      "journal_cross_cross_journal_radiology_nips",
    ]
  },
};

/**************************************************
 * 2) CSV file paths.
 *    Adjust for your GitHub Pages structure.
 **************************************************/
const csvFiles_acc = [
  "{{ '/assets/data/GPT_combined_results_real.csv' | relative_url }}",
  "{{ '/assets/data/Llama_combined_results_real.csv' | relative_url }}",
  "{{ '/assets/data/Qwen_combined_results_real.csv' | relative_url }}",
  "{{ '/assets/data/DeepSeek_combined_results_real.csv' | relative_url }}"
];

const csvFiles_npc = [
  "{{ '/assets/data/GPT_combined_NPC_results.csv' | relative_url }}",
  "{{ '/assets/data/Llama_combined_NPC_results.csv' | relative_url }}",
  "{{ '/assets/data/Qwen_combined_NPC_results.csv' | relative_url }}",
  "{{ '/assets/data/DeepSeek_combined_NPC_results.csv' | relative_url }}"
];

//------------------------------------------------------------
// (OPTIONAL) 3) Pretty names for tasks / methods / models
//------------------------------------------------------------
// If you only want to rename certain tasks or methods, define them here.
// The aggregator will keep the original keys to filter, but show these.

const renameTask = {
  "deceptive_reviews": "Deceptive Reviews Detection",
  "llamagc_detect": "Llama-generated Content Detection",
  "gptgc_detect": "GPT-generated Content Detection",
  "persuasive_pairs": "Persuasive Argument Prediction",
  "dreaddit": "Mental Stress Detection",
  "headline_binary": "News Headline Engagement",
  "retweet": "Retweets",
  "journal_same_same_journal_health": "Health Journal",
  "journal_same_same_journal_nips": "NeurIPS Journal",
  "journal_same_same_journal_radiology": "Radiology Journal",
  "journal_cross_cross_journal_health_nips": "Cross Journal Health & NeurIPS",
  "journal_cross_cross_journal_health_radiology": "Cross Journal Health & Radiology",
  "journal_cross_cross_journal_nips_health": "Cross Journal NeurIPS & Health",
  "journal_cross_cross_journal_nips_radiology": "Cross Journal NeurIPS & Radiology",
  "journal_cross_cross_journal_radiology_health": "Cross Journal Radiology & Health",
  "journal_cross_cross_journal_radiology_nips": "Cross Journal Radiology & NeurIPS",
};

const renameMethod = {
  "Zero-shot Inference": "Zero-shot Inference",
  "Few-shot Inference": "Few-shot Inference",
  "Zero-shot Generation": "Zero-shot Generation",
  "\\paperonly": "Literature-Only",
  "\\ioprompt": "IO Prompting",
  "\\iorefine": "Iterative Refinement",
  "\\hypogenic": "HypoGeniC",
  "\\litplusdata": "Literature + Data",
};

const renameModel = {
  "GPT": "GPT-4o-mini",
  "Llama": "Llama-3.1-70B-Instruct",
  "Qwen": "Qwen-2.5-72B-Instruct",
  "DeepSeek": "DeepSeek-R1-Distill-Llama-70B-local"
};