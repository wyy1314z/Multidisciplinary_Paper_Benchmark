import os
import requests
import sys

def check_env_var(var_name):
    val = os.environ.get(var_name)
    if val:
        masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
        print(f"✅ {var_name} is set: {masked}")
        return val
    else:
        print(f"❌ {var_name} is NOT set.")
        return None

def check_openai_connection():
    print("\n--- Testing OpenAI API Connection ---")
    api_key = os.environ.get("OPENAI_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE", "http://api.shubiaobiao.cn/v1")
    
    if not api_key:
        print("⚠️ OPENAI_API_KEY not found in environment. Skipping connection test.")
        return

    print(f"Using API Base: {api_base}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Simple model list or chat completion test
    url = f"{api_base}/models"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Connection successful! Retrieved model list.")
        else:
            print(f"❌ Connection failed. Status Code: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ Connection error: {e}")

def check_s2_connection():
    print("\n--- Testing Semantic Scholar API Connection ---")
    api_key = os.environ.get("S2_API_KEY")
    headers = {'User-Agent': 'Mozilla/5.0'}
    if api_key:
        headers['x-api-key'] = api_key
        print("Using S2_API_KEY.")
    
    url = "https://api.semanticscholar.org/graph/v1/paper/search?query=deep+learning&limit=1"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print("✅ Semantic Scholar API reachable.")
        elif response.status_code == 429:
            print("⚠️ Semantic Scholar API Rate Limit (429).")
        else:
            print(f"❌ Semantic Scholar API error: {response.status_code}")
    except Exception as e:
        print(f"❌ Semantic Scholar connection error: {e}")

if __name__ == "__main__":
    print("Checking Environment Variables...")
    check_env_var("OPENAI_API_KEY")
    check_env_var("OPENAI_API_BASE")
    check_env_var("S2_API_KEY")
    check_env_var("http_proxy")
    check_env_var("https_proxy")
    
    check_s2_connection()
    check_openai_connection()
