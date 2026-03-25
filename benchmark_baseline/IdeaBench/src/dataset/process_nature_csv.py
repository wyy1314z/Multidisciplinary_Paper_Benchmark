import pandas as pd
import argparse
import os
import sys
from tqdm import tqdm
import time

# Add current directory to sys.path to allow importing from sibling modules if needed
# But here we are in src/dataset/process_nature_csv.py, and setup_custom_paper is in src/dataset/
# So we can just import it if we run from root with -m or adjust path.
# However, to be safe and avoid import issues with relative paths in different execution contexts,
# I will copy the helper functions or import them if the path is set up correctly.

# Assuming we run this script as: python src/dataset/process_nature_csv.py
# We need to add the directory containing setup_custom_paper.py to path.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from setup_custom_paper import search_paper, get_paper_details
except ImportError:
    # Fallback if import fails (e.g. if dependencies are missing or path issues), define them here or handle error
    print("Could not import setup_custom_paper. Please ensure you are running this from the project root.")
    # For robustness, I'll redefine the search function here to ensure it works standalone 
    # if the other file has dependencies I missed or if pathing is tricky.
    # But reusing is better. Let's try to trust the import first.
    pass

def process_csv(input_csv, output_csv, limit=None):
    print(f"Reading input CSV: {input_csv}")
    try:
        df_input = pd.read_csv(input_csv)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    if 'title' not in df_input.columns:
        print("Error: Input CSV must contain a 'title' column.")
        return

    titles = df_input['title'].tolist()
    if limit:
        titles = titles[:limit]
        print(f"Limiting to first {limit} titles.")
        
    print(f"Found {len(titles)} titles to process.")

    # Check for DOI column
    dois = df_input['doi'].tolist() if 'doi' in df_input.columns else [None] * len(titles)

    found_papers = []
    not_found_titles = []

    for i, title in tqdm(enumerate(titles), total=len(titles), desc="Searching papers"):
        # Basic cleaning of title if needed
        if not isinstance(title, str) or not title.strip():
            continue
            
        paper_data = None
        
        # Try DOI first if available
        doi = dois[i]
        if isinstance(doi, str) and 'doi.org' in doi:
            try:
                # Extract DOI from URL if needed (e.g., https://doi.org/10.1038/...)
                clean_doi = doi.split('doi.org/')[-1].strip()
                paper_data = get_paper_details(f"DOI:{clean_doi}")
            except Exception as e:
                # print(f"DEBUG: DOI lookup failed for {doi}: {e}")
                pass
        
        # Fallback to title search
        if not paper_data:
            paper_data = search_paper(title)
            
            if not paper_data:
                # Retry with shorter title as in setup_custom_paper.py
                short_query = " ".join(title.split()[:5])
                paper_data = search_paper(short_query)

        if paper_data:
            found_papers.append(paper_data)
        else:
            not_found_titles.append(title)
        
        # Be nice to the API
        time.sleep(2)  # Increased delay between requests

    print(f"Successfully found {len(found_papers)} papers.")
    print(f"Failed to find {len(not_found_titles)} papers.")
    
    if not_found_titles:
        print("First 5 not found titles:")
        for t in not_found_titles[:5]:
            print(f"- {t}")

    if found_papers:
        df_output = pd.DataFrame(found_papers)
        df_output['strategy'] = 'nature_2025_custom'
        
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        df_output.to_csv(output_csv, index=False)
        print(f"Saved result to {output_csv}")
    else:
        print("No papers found. Nothing saved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process Nature 2025 CSV to target_papers.csv format")
    parser.add_argument("--input", type=str, required=True, help="Path to input CSV (nature_2025.csv)")
    parser.add_argument("--output", type=str, required=True, help="Path to output CSV")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of papers to process (for testing)")
    
    args = parser.parse_args()
    
    process_csv(args.input, args.output, limit=args.limit)
