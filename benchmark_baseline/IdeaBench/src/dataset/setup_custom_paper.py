import argparse
import pandas as pd
import requests
import sys
import os

import time

def make_request_with_retry(url, params=None, headers=None, retries=5, backoff_factor=2):
    """
    Make a request with exponential backoff retry for 429 errors.
    """
    if headers is None:
        headers = {}
    
    # Add User-Agent if not present
    if 'User-Agent' not in headers:
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    
    # Check for S2_API_KEY in environment
    api_key = os.environ.get('S2_API_KEY')
    if api_key:
        headers['x-api-key'] = api_key

    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                sleep_time = (backoff_factor ** attempt) + 5  # Increased base wait time
                print(f"DEBUG: API Error 429 (Too Many Requests). Retrying in {sleep_time} seconds... (Attempt {attempt + 1}/{retries})")
                time.sleep(sleep_time)
            else:
                print(f"DEBUG: API Error {response.status_code}: {response.text}")
                return response # Return error response to be handled by caller
        except Exception as e:
            print(f"DEBUG: Request failed: {e}")
            if attempt < retries - 1:
                sleep_time = (backoff_factor ** attempt) + 5
                print(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                return None
    
    print("Error: Max retries exceeded.")
    return None

def search_paper(query):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {'query': query, 'limit': 1, 'fields': 'paperId,title,abstract,year,venue,citationCount,publicationTypes,externalIds'}
    
    response = make_request_with_retry(url, params=params)
    
    if response and response.status_code == 200:
        data = response.json()
        if data.get('total', 0) > 0:
            return data['data'][0]
        else:
            print(f"DEBUG: API returned 200 but 0 results. Query: {query}")
            
    return None

def get_paper_details(paper_id):
    url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    params = {'fields': 'paperId,title,abstract,year,venue,citationCount,publicationTypes,externalIds'}
    
    response = make_request_with_retry(url, params=params)
    
    if response and response.status_code == 200:
        return response.json()
        
    return None

def main():
    parser = argparse.ArgumentParser(description="Setup custom target paper for IdeaBench")
    parser.add_argument("--title", type=str, help="Paper title")
    parser.add_argument("--paper_id", type=str, help="Semantic Scholar Paper ID")
    parser.add_argument("--output", type=str, required=True, help="Output CSV path")
    args = parser.parse_args()

    paper_data = None
    if args.paper_id:
        print(f"Fetching details for Paper ID: {args.paper_id}")
        paper_data = get_paper_details(args.paper_id)
    elif args.title:
        print(f"Searching for paper: {args.title}")
        paper_data = search_paper(args.title)
    
    if not paper_data:
        print("Error: Paper not found via API search.")
        # Fallback: Try searching with a broader query (just first 5 words) if exact match fails
        if args.title:
            short_query = " ".join(args.title.split()[:5])
            print(f"Retrying with shorter query: {short_query}")
            paper_data = search_paper(short_query)

    if not paper_data:
        print("Error: Paper still not found! Please check the title or ID.")
        sys.exit(1)

    print(f"Found paper: {paper_data.get('title', 'Unknown')} ({paper_data.get('year', 'N/A')})")
    
    if not paper_data.get('abstract'):
        print("Warning: This paper has no abstract in Semantic Scholar. Generation might fail.")

    # Create DataFrame with columns expected by IdeaBench
    df = pd.DataFrame([paper_data])
    df['strategy'] = 'custom'
    
    # Save
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Saved target paper to {args.output}")

if __name__ == "__main__":
    main()
