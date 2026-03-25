---
---

const renameCategory = {
  "admission": "College Admission",
  "admission_adv": "Counterintuitive Admission",
  "election": "Presidential Election",
  "preference": "Personality Prediction",
  "shoe": "Shoe Sales"
};
/**************************************************
 * 1) Define your multi-level categories object.
 *    EXACTLY match the Task values in your CSVs.
 *    Now tasks use underscores, not slashes.
 **************************************************/
const categories = {
  All: null,  // Means no filtering in theory, but we skip in UI
  admission: {
    "level 1": [
      "admission_level_1_base"
    ],
    "level 2": [
      "admission_level_2_depth_2",
      "admission_level_2_distractor_3",
      "admission_level_2_noise_10",
      "admission_level_2_size_5"
    ],
    "level 3": [
      "admission_level_3_depth_3",
      "admission_level_3_distractor_6",
      "admission_level_3_noise_20",
      "admission_level_3_size_10"
    ],
    "level 4": [
      "admission_level_4_depth_4",
      "admission_level_4_distractor_10",
      "admission_level_4_noise_30",
      "admission_level_4_size_15"
    ]
  },
  admission_adv: {
    "level 1": [
      "admission_adv_level_1_base"
    ],
    "level 2": [
      "admission_adv_level_2_depth_2",
      "admission_adv_level_2_distractor_3",
      "admission_adv_level_2_noise_10",
      "admission_adv_level_2_size_5"
    ],
    "level 3": [
      "admission_adv_level_3_depth_3",
      "admission_adv_level_3_distractor_6",
      "admission_adv_level_3_noise_20",
      "admission_adv_level_3_size_10"
    ],
    "level 4": [
      "admission_adv_level_4_depth_4",
      "admission_adv_level_4_distractor_10",
      "admission_adv_level_4_noise_30",
      "admission_adv_level_4_size_15"
    ]
  },
  election: {
    "level 0": [
      "election_level0",
      "election_level0_nosubtlety"
    ],
    "level 1": [
      "election_level1",
      "election_level1_nosubtlety"
    ],
    "level 2": [
      "election_level2",
      "election_level2_nosubtlety"
    ],
    "level 3": [
      "election_level3",
      "election_level3_nosubtlety"
    ],
    "level 4": [
      "election_level4",
      "election_level4_nosubtlety"
    ],
    "level 5": [
      "election_level5",
      "election_level5_nosubtlety"
    ],
    "controlled": [
      "election_controlled_5_0_0",
      "election_controlled_10_0_0",
      "election_controlled_15_0_0",
      "election_controlled_20_0_0",
      "election_controlled_20_0.1_0",
      "election_controlled_20_0.2_0",
      "election_controlled_20_0.3_0",
      "election_controlled_20_0_0.1",
      "election_controlled_20_0_0.2",
      "election_controlled_20_0_0.3",
      "election_controlled_20_0.1_0.1",
      "election_controlled_20_0.2_0.2",
      "election_controlled_20_0.3_0.3"
    ],
    "counterfactual": [
      "election_counterfactual_normal",
      "election_counterfactual_counterfactual"
    ]
  },
  preference: {
    "level 0": [
      "preference_level0",
      "preference_level0_nosubtlety"
    ],
    "level 1": [
      "preference_level1",
      "preference_level1_nosubtlety"
    ],
    "level 2": [
      "preference_level2",
      "preference_level2_nosubtlety"
    ],
    "level 3": [
      "preference_level3",
      "preference_level3_nosubtlety"
    ],
    "level 4": [
      "preference_level4",
      "preference_level4_nosubtlety"
    ],
    "level 5": [
      "preference_level5",
      "preference_level5_nosubtlety"
    ],
    "controlled": [
      "preference_controlled_5_0_0",
      "preference_controlled_10_0_0",
      "preference_controlled_15_0_0",
      "preference_controlled_20_0_0",
      "preference_controlled_20_0.1_0",
      "preference_controlled_20_0.2_0",
      "preference_controlled_20_0.3_0",
      "preference_controlled_20_0_0.1",
      "preference_controlled_20_0_0.2",
      "preference_controlled_20_0_0.3",
      "preference_controlled_20_0.1_0.1",
      "preference_controlled_20_0.2_0.2",
      "preference_controlled_20_0.3_0.3"
    ]
  },
  shoe: {
    "simple": [
      "shoe"
    ],
    "two_level": [
      "shoe_two_level_simple",
      "shoe_two_level_hard"
    ]
  }
};

/**************************************************
 * 2) CSV file paths.
 *    Adjust for your GitHub Pages structure.
 **************************************************/
const csvFiles_acc = [
  "{{ '/assets/data/GPT_combined_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/Llama_combined_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/Qwen_combined_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/DeepSeek_combined_results_synth.csv' | relative_url }}"
];

const csvFiles_hdr = [
  "{{ '/assets/data/GPT_combined_HDR_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/Llama_combined_HDR_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/Qwen_combined_HDR_results_synth.csv' | relative_url }}",
  "{{ '/assets/data/DeepSeek_combined_HDR_results_synth.csv' | relative_url }}"
];

//------------------------------------------------------------
// (OPTIONAL) 3) Pretty names for tasks / methods / models
//------------------------------------------------------------
// If you only want to rename certain tasks or methods, define them here.
// The aggregator will keep the original keys to filter, but show these.

const renameTask = {
  // Admission tasks
  "admission_level_1_base": "College Admission Base (Level 1)",
  "admission_level_2_depth_2": "College Admission Depth 2 (Level 2)",
  "admission_level_2_distractor_3": "College Admission Distractor 3 (Level 2)",
  "admission_level_2_noise_10": "College Admission Noise 10% (Level 2)",
  "admission_level_2_size_5": "College Admission Num. Features: 5 (Level 2)",
  "admission_level_3_depth_3": "College Admission Depth 3 (Level 3)",
  "admission_level_3_distractor_6": "College Admission Distractor 6 (Level 3)",
  "admission_level_3_noise_20": "College Admission Noise 20% (Level 3)",
  "admission_level_3_size_10": "College Admission Num. Features: 10 (Level 3)",
  "admission_level_4_depth_4": "College Admission Depth 4 (Level 4)",
  "admission_level_4_distractor_10": "College Admission Distractor 10 (Level 4)",
  "admission_level_4_noise_30": "College Admission Noise 30% (Level 4)",
  "admission_level_4_size_15": "College Admission Num. Features: 15 (Level 4)",

  // Counterintuitive Admission tasks
  "admission_adv_level_1_base": "Counterintuitive Admission Base (Level 1)",
  "admission_adv_level_2_depth_2": "Counterintuitive Admission Depth 2 (Level 2)",
  "admission_adv_level_2_distractor_3": "Counterintuitive Admission Distractor 3 (Level 2)",
  "admission_adv_level_2_noise_10": "Counterintuitive Admission Noise 10% (Level 2)",
  "admission_adv_level_2_size_5": "Counterintuitive Admission Num. Features: 5 (Level 2)",
  "admission_adv_level_3_depth_3": "Counterintuitive Admission Depth 3 (Level 3)",
  "admission_adv_level_3_distractor_6": "Counterintuitive Admission Distractor 6 (Level 3)",
  "admission_adv_level_3_noise_20": "Counterintuitive Admission Noise 20% (Level 3)",
  "admission_adv_level_3_size_10": "Counterintuitive Admission Num. Features: 10 (Level 3)",
  "admission_adv_level_4_depth_4": "Counterintuitive Admission Depth 4 (Level 4)",
  "admission_adv_level_4_distractor_10": "Counterintuitive Admission Distractor 10 (Level 4)",
  "admission_adv_level_4_noise_30": "Counterintuitive Admission Noise 30% (Level 4)",
  "admission_adv_level_4_size_15": "Counterintuitive Admission Num. Features: 15 (Level 4)",

  // Election tasks
  "election_level0": "Presidential Election Level 0",
  "election_level0_nosubtlety": "Presidential Election Level 0 (No Subtlety)",
  "election_level1": "Presidential Election Level 1",
  "election_level1_nosubtlety": "Presidential Election Level 1 (No Subtlety)",
  "election_level2": "Presidential Election Level 2",
  "election_level2_nosubtlety": "Presidential Election Level 2 (No Subtlety)",
  "election_level3": "Presidential Election Level 3",
  "election_level3_nosubtlety": "Presidential Election Level 3 (No Subtlety)",
  "election_level4": "Presidential Election Level 4",
  "election_level4_nosubtlety": "Presidential Election Level 4 (No Subtlety)",
  "election_level5": "Presidential Election Level 5",
  "election_level5_nosubtlety": "Presidential Election Level 5 (No Subtlety)",
  "election_controlled_5_0_0": "Presidential Election Controlled (Num. Features: 5, Noise: 0%, Dropout: 0%)",
  "election_controlled_10_0_0": "Presidential Election Controlled (Num. Features: 10, Noise: 0%, Dropout: 0%)",
  "election_controlled_15_0_0": "Presidential Election Controlled (Num. Features: 15, Noise: 0%, Dropout: 0%)",
  "election_controlled_20_0_0": "Presidential Election Controlled (Num. Features: 20, Noise: 0%, Dropout: 0%)",
  "election_controlled_20_0.1_0": "Presidential Election Controlled (Num. Features: 20, Noise: 10%, Dropout: 0%)",
  "election_controlled_20_0.2_0": "Presidential Election Controlled (Num. Features: 20, Noise: 20%, Dropout: 0%)",
  "election_controlled_20_0.3_0": "Presidential Election Controlled (Num. Features: 20, Noise: 30%, Dropout: 0%)",
  "election_controlled_20_0_0.1": "Presidential Election Controlled (Num. Features: 20, Noise: 0%, Dropout: 10%)",
  "election_controlled_20_0_0.2": "Presidential Election Controlled (Num. Features: 20, Noise: 0%, Dropout: 20%)",
  "election_controlled_20_0_0.3": "Presidential Election Controlled (Num. Features: 20, Noise: 0%, Dropout: 30%)",
  "election_controlled_20_0.1_0.1": "Presidential Election Controlled (Num. Features: 20, Noise: 10%, Dropout: 10%)",
  "election_controlled_20_0.2_0.2": "Presidential Election Controlled (Num. Features: 20, Noise: 20%, Dropout: 20%)",
  "election_controlled_20_0.3_0.3": "Presidential Election Controlled (Num. Features: 20, Noise: 30%, Dropout: 30%)",
  "election_counterfactual_normal": "Presidential Election Counterfactual (Normal)",
  "election_counterfactual_counterfactual": "Presidential Election Counterfactual",

  // Preference tasks
  "preference_level0": "Personality Prediction Level 0",
  "preference_level0_nosubtlety": "Personality Prediction Level 0 (No Subtlety)",
  "preference_level1": "Personality Prediction Level 1",
  "preference_level1_nosubtlety": "Personality Prediction Level 1 (No Subtlety)",
  "preference_level2": "Personality Prediction Level 2",
  "preference_level2_nosubtlety": "Personality Prediction Level 2 (No Subtlety)",
  "preference_level3": "Personality Prediction Level 3",
  "preference_level3_nosubtlety": "Personality Prediction Level 3 (No Subtlety)",
  "preference_level4": "Personality Prediction Level 4",
  "preference_level4_nosubtlety": "Personality Prediction Level 4 (No Subtlety)",
  "preference_level5": "Personality Prediction Level 5",
  "preference_level5_nosubtlety": "Personality Prediction Level 5 (No Subtlety)",
  "preference_controlled_5_0_0": "Personality Prediction Controlled (Num. Features: 5, Noise: 0%, Dropout: 0%)",
  "preference_controlled_10_0_0": "Personality Prediction Controlled (Num. Features: 10, Noise: 0%, Dropout: 0%)",
  "preference_controlled_15_0_0": "Personality Prediction Controlled (Num. Features: 15, Noise: 0%, Dropout: 0%)",
  "preference_controlled_20_0_0": "Personality Prediction Controlled (Num. Features: 20, Noise: 0%, Dropout: 0%)",
  "preference_controlled_20_0.1_0": "Personality Prediction Controlled (Num. Features: 20, Noise: 10%, Dropout: 0%)",
  "preference_controlled_20_0.2_0": "Personality Prediction Controlled (Num. Features: 20, Noise: 20%, Dropout: 0%)",
  "preference_controlled_20_0.3_0": "Personality Prediction Controlled (Num. Features: 20, Noise: 30%, Dropout: 0%)",
  "preference_controlled_20_0_0.1": "Personality Prediction Controlled (Num. Features: 20, Noise: 0%, Dropout: 10%)",
  "preference_controlled_20_0_0.2": "Personality Prediction Controlled (Num. Features: 20, Noise: 0%, Dropout: 20%)",
  "preference_controlled_20_0_0.3": "Personality Prediction Controlled (Num. Features: 20, Noise: 0%, Dropout: 30%)",
  "preference_controlled_20_0.1_0.1": "Personality Prediction Controlled (Num. Features: 20, Noise: 10%, Dropout: 10%)",
  "preference_controlled_20_0.2_0.2": "Personality Prediction Controlled (Num. Features: 20, Noise: 20%, Dropout: 20%)",
  "preference_controlled_20_0.3_0.3": "Personality Prediction Controlled (Num. Features: 20, Noise: 30%, Dropout: 30%)",

  // Shoe tasks
  "shoe": "Shoe Sales Base",
  "shoe_two_level_simple": "Shoe Sales Two-Level Simple",
  "shoe_two_level_hard": "Shoe Sales Two-Level Hard"
};

const renameMethod = {
  "Zero-shot Inference": "Zero-shot Inference",
  "Few-shot Inference": "Few-shot Inference",
  "Zero-shot Generation": "Zero-shot Generation",
  "\\ioprompt": "IO Prompting",
  "\\iorefine": "Iterative Refinement",
  "\\hypogenic": "HypoGeniC"
};

const renameModel = {
  "GPT": "GPT-4o-mini",
  "Llama": "Llama-3.1-70B-Instruct",
  "Qwen": "Qwen-2.5-72B-Instruct",
  "DeepSeek": "DeepSeek-R1-Distill-Llama-70B-local"
};