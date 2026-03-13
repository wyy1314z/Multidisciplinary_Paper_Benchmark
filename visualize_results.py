
import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

def visualize(json_path, output_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Prepare data for DataFrame
    rows = []
    for item in data:
        scores = item.get("scores", {})
        if not scores:
            continue
            
        for level in ["L1", "L2", "L3"]:
            inn = scores.get(f"{level}_innovation")
            con = scores.get(f"{level}_consistency")
            
            if inn is not None and con is not None:
                rows.append({
                    "Level": level,
                    "Innovation": inn,
                    "Consistency": con
                })

    df = pd.DataFrame(rows)
    
    if df.empty:
        print("No valid data found to plot.")
        return

    # Set style
    sns.set_theme(style="whitegrid")
    
    plt.figure(figsize=(10, 6))
    
    # Create scatter plot with different markers/colors for levels
    # Use alpha to handle overlapping points
    sns.scatterplot(
        data=df, 
        x="Consistency", 
        y="Innovation", 
        hue="Level", 
        style="Level", 
        s=100, 
        alpha=0.8,
        palette="deep"
    )

    # Add title and labels
    plt.title("Innovation vs Consistency across Hypothesis Levels (L1/L2/L3)", fontsize=16)
    plt.xlabel("Path Consistency (Factuality)", fontsize=12)
    plt.ylabel("Innovation Score (Subjective)", fontsize=12)
    
    # Set axis limits for better view (0-1 for consistency, 0-10 for innovation)
    plt.xlim(-0.05, 1.05)
    plt.ylim(0, 10.5)
    
    # Add annotations for mean points (centroids)
    means = df.groupby("Level")[["Consistency", "Innovation"]].mean()
    for level, row in means.iterrows():
        plt.plot(row["Consistency"], row["Innovation"], marker='X', markersize=15, markeredgecolor='black', color='black')
        plt.text(
            row["Consistency"] + 0.02, 
            row["Innovation"] + 0.2, 
            f"{level} Mean", 
            fontsize=10, 
            fontweight='bold'
        )

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    print(f"Plot saved to {output_path}")

if __name__ == "__main__":
    visualize("outputs/eval_results_v7.json", "outputs/innovation_vs_consistency.png")
