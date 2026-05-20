import os
import sys
import time
import requests
import urllib.parse

# Configuration
BANGLAPEDIA_API = "https://en.banglapedia.org/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
OUTPUT_FILE = "missing_banglapedia_articles.md"

# Custom headers to comply with Wikimedia/MediaWiki API user agent policy
HEADERS = {
    "User-Agent": "BanglapediaWikiCrossReferencer/1.0 (https://en.banglapedia.org/; contact: yahya.gemini@example.com)"
}

def fetch_banglapedia_titles():
    """
    Fetches all article titles in namespace 0 from Banglapedia.
    Filters out redirects to only check actual articles.
    """
    titles = []
    params = {
        "action": "query",
        "list": "allpages",
        "apnamespace": 0,
        "aplimit": 500,
        "apfilterredir": "nonredirects",
        "format": "json"
    }
    
    print("Initializing Banglapedia article fetch...")
    start_time = time.time()
    
    while True:
        try:
            # Using POST for robustness
            response = requests.post(BANGLAPEDIA_API, data=params, headers=HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if "query" in data and "allpages" in data["query"]:
                batch = [page["title"] for page in data["query"]["allpages"]]
                titles.extend(batch)
                print(f"Fetched {len(titles)} articles...")
            
            if "continue" in data:
                params.update(data["continue"])
            else:
                break
                
            time.sleep(0.1) # Be polite to Banglapedia servers
        except Exception as e:
            print(f"Error fetching from Banglapedia: {e}", file=sys.stderr)
            break
            
    duration = time.time() - start_time
    print(f"Finished fetching Banglapedia articles. Total: {len(titles)} articles in {duration:.2f} seconds.\n")
    return titles

def check_wikipedia_existence(titles):
    """
    Queries English Wikipedia in batches of 50 to see which articles do not exist.
    Resolves redirects and normalizations.
    """
    missing_titles = []
    existing_count = 0
    batch_size = 50
    total = len(titles)
    
    print(f"Checking existence of {total} articles on English Wikipedia in batches of {batch_size}...")
    start_time = time.time()
    
    for i in range(0, total, batch_size):
        batch = titles[i:i+batch_size]
        
        params = {
            "action": "query",
            "titles": "|".join(batch),
            "redirects": 1,
            "format": "json"
        }
        
        # Retry logic for robustness
        retries = 3
        data = None
        for retry in range(retries):
            try:
                response = requests.post(WIKIPEDIA_API, data=params, headers=HEADERS, timeout=20)
                response.raise_for_status()
                data = response.json()
                break
            except Exception as e:
                print(f"\n[Warning] Attempt {retry+1} failed for batch starting at index {i}: {e}", file=sys.stderr)
                time.sleep(2)
        
        if not data:
            print(f"\n[Error] Failed to query batch starting at index {i} after {retries} retries. Skipping batch.", file=sys.stderr)
            continue
            
        query_data = data.get("query", {})
        pages = query_data.get("pages", {})
        
        # Map Wikipedia's normalized/redirected titles back to the original titles we queried.
        # This is key since Wikipedia normalizes casing and resolves redirects.
        resolved_to_original = {t: t for t in batch}
        
        # Track normalization mappings
        if "normalized" in query_data:
            for norm in query_data["normalized"]:
                from_t = norm["from"]
                to_t = norm["to"]
                if from_t in resolved_to_original:
                    resolved_to_original[to_t] = resolved_to_original[from_t]
                    
        # Track redirect mappings
        if "redirects" in query_data:
            for redir in query_data["redirects"]:
                from_t = redir["from"]
                to_t = redir["to"]
                if from_t in resolved_to_original:
                    resolved_to_original[to_t] = resolved_to_original[from_t]
                    
        # Determine which original titles exist
        existing_originals = set()
        for page_id, page_info in pages.items():
            title = page_info.get("title")
            is_missing = "missing" in page_info or int(page_id) < 0
            
            orig = resolved_to_original.get(title)
            if orig and not is_missing:
                existing_originals.add(orig)
                
        # Any title in the batch that is not confirmed to exist is missing
        for orig_title in batch:
            if orig_title not in existing_originals:
                missing_titles.append(orig_title)
            else:
                existing_count += 1
                
        # Progress reporting
        processed = min(i + batch_size, total)
        percent = (processed / total) * 100
        sys.stdout.write(f"\rProgress: {processed}/{total} checked ({percent:.1f}%) | Missing found: {len(missing_titles)}")
        sys.stdout.flush()
        
        time.sleep(0.15) # Polite delay to avoid Wikipedia rate limits
        
    duration = time.time() - start_time
    print(f"\n\nWikipedia verification complete. Checked {total} articles in {duration:.2f} seconds.")
    print(f"Exists on Wikipedia: {existing_count} | Missing: {len(missing_titles)}")
    return missing_titles

def generate_markdown_report(total_count, missing_articles):
    """
    Generates a beautifully formatted Markdown report of the missing articles.
    """
    missing_count = len(missing_articles)
    existing_count = total_count - missing_count
    missing_percent = (missing_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"Generating report: {OUTPUT_FILE}...")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Banglapedia Articles Missing from English Wikipedia\n\n")
        f.write("This report lists articles present on the English Banglapedia which do not have a corresponding page on English Wikipedia. This list is extremely useful for identifying gaps in Wikipedia's coverage of Bangladesh-related topics.\n\n")
        
        # Summary statistics card
        f.write("## Overview Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| **Total Banglapedia Articles** | {total_count:,} |\n")
        f.write(f"| **Found on English Wikipedia** | {existing_count:,} |\n")
        f.write(f"| **Missing from English Wikipedia** | {missing_count:,} |\n")
        f.write(f"| **Coverage Gap (%)** | {missing_percent:.2f}% |\n\n")
        
        f.write("## List of Missing Articles\n\n")
        f.write("Below is the complete list of missing articles. Each entry links to the original Banglapedia page and includes a quick link to search English Wikipedia in case the article exists under a very different name.\n\n")
        
        f.write("| # | Banglapedia Article | Wikipedia Search |\n")
        f.write("| :---: | :--- | :--- |\n")
        
        for idx, title in enumerate(sorted(missing_articles), 1):
            banglapedia_url = f"https://en.banglapedia.org/index.php?title={urllib.parse.quote(title)}"
            wikipedia_search_url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(title)}"
            
            f.write(f"| {idx} | [{title}]({banglapedia_url}) | [Search Wikipedia]({wikipedia_search_url}) |\n")
            
    print(f"Successfully generated {OUTPUT_FILE}!")

def main():
    print("=" * 60)
    print("Banglapedia vs English Wikipedia Cross-Referencer")
    print("=" * 60)
    
    # 1. Fetch all titles from Banglapedia
    banglapedia_titles = fetch_banglapedia_titles()
    if not banglapedia_titles:
        print("Error: No articles fetched from Banglapedia. Exiting.")
        sys.exit(1)
        
    # 2. Check each title on English Wikipedia
    missing_articles = check_wikipedia_existence(banglapedia_titles)
    
    # 3. Write markdown report
    generate_markdown_report(len(banglapedia_titles), missing_articles)
    
    print("\nAll tasks completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
