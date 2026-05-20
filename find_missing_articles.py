import os
import sys
import re
import time
import requests
import urllib.parse

# Configuration
BANGLAPEDIA_API = "https://en.banglapedia.org/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
OUTPUT_FILE = "missing_banglapedia_articles.md"

# Custom headers to comply with Wikimedia/MediaWiki API user agent policy
HEADERS = {
    "User-Agent": "BanglapediaWikiCrossReferencer/1.1 (https://en.banglapedia.org/; contact: yahya.gemini@example.com)"
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

def clean_and_format_title(title):
    """
    Cleans and formats a Banglapedia page title for English Wikipedia.
    - Strips trailing disambiguation digits adjacent to names (e.g. Shahed1 -> Shahed).
    - If title contains a comma, reverses the parts to restore natural name order
      (e.g., "Alim, Qazi Abdul" -> "Qazi Abdul Alim" or "Ahmad, Ashabuddin" -> "Ashabuddin Ahmad").
    """
    # Remove any trailing disambiguation digits at the end of words (e.g., "Shahed1" -> "Shahed")
    title_cleaned = re.sub(r'([a-zA-Z]+)\d+\b', r'\1', title)
    
    # Handle human names and inverted terms formatted with a comma
    if "," in title_cleaned:
        parts = [p.strip() for p in title_cleaned.split(",", 1)]
        if len(parts) == 2:
            formatted = f"{parts[1]} {parts[0]}"
            return " ".join(formatted.split())
            
    return " ".join(title_cleaned.split())

def check_wikipedia_existence(formatted_titles, formatted_to_originals):
    """
    Queries English Wikipedia in batches of 50 to check article existence.
    Maps results back to the original Banglapedia titles.
    """
    missing_pairs = [] # List of tuples: (original_title, formatted_title)
    existing_count = 0
    batch_size = 50
    total = len(formatted_titles)
    
    print(f"Checking existence of {total} formatted terms on Wikipedia in batches of {batch_size}...")
    start_time = time.time()
    
    for i in range(0, total, batch_size):
        batch = formatted_titles[i:i+batch_size]
        
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
        
        # Map Wikipedia's returned titles (resolved redirects & normalized titles) back to the batch elements
        resolved_to_formatted = {t: t for t in batch}
        
        # Track casing normalization
        if "normalized" in query_data:
            for norm in query_data["normalized"]:
                from_t = norm["from"]
                to_t = norm["to"]
                if from_t in resolved_to_formatted:
                    resolved_to_formatted[to_t] = resolved_to_formatted[from_t]
                    
        # Track resolved redirects
        if "redirects" in query_data:
            for redir in query_data["redirects"]:
                from_t = redir["from"]
                to_t = redir["to"]
                if from_t in resolved_to_formatted:
                    resolved_to_formatted[to_t] = resolved_to_formatted[from_t]
                    
        # Find which formatted titles exist
        existing_formatted = set()
        for page_id, page_info in pages.items():
            title = page_info.get("title")
            is_missing = "missing" in page_info or int(page_id) < 0
            
            fmt_t = resolved_to_formatted.get(title)
            if fmt_t and not is_missing:
                existing_formatted.add(fmt_t)
                
        # Update missing and existing tallies using original Banglapedia titles
        for fmt_t in batch:
            orig_titles = formatted_to_originals[fmt_t]
            if fmt_t not in existing_formatted:
                for orig in orig_titles:
                    missing_pairs.append((orig, fmt_t))
            else:
                existing_count += len(orig_titles)
                
        # Progress reporting
        processed = min(i + batch_size, total)
        percent = (processed / total) * 100
        sys.stdout.write(f"\rProgress: {processed}/{total} checked ({percent:.1f}%) | Missing original articles: {len(missing_pairs)}")
        sys.stdout.flush()
        
        time.sleep(0.15) # Polite delay to avoid Wikipedia rate limits
        
    duration = time.time() - start_time
    print(f"\n\nWikipedia verification complete. Checked {total} formatted titles in {duration:.2f} seconds.")
    return missing_pairs, existing_count

def generate_markdown_report(total_count, missing_pairs, existing_count):
    """
    Generates a beautifully formatted Markdown report of the missing articles.
    """
    missing_count = len(missing_pairs)
    missing_percent = (missing_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"Generating report: {OUTPUT_FILE}...")
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("# Banglapedia Articles Missing from English Wikipedia\n\n")
        f.write("This report lists articles present on the English Banglapedia which do not have a corresponding page on English Wikipedia. Inverted human names (e.g. `Alim, Qazi Abdul`) and terms have been corrected to their natural order (e.g. `Qazi Abdul Alim`) and disambiguation numbers stripped before cross-referencing Wikipedia.\n\n")
        
        # Summary statistics card
        f.write("## Overview Statistics\n\n")
        f.write("| Metric | Value |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| **Total Banglapedia Articles** | {total_count:,} |\n")
        f.write(f"| **Found on English Wikipedia** | {existing_count:,} |\n")
        f.write(f"| **Missing from English Wikipedia** | {missing_count:,} |\n")
        f.write(f"| **Coverage Gap (%)** | {missing_percent:.2f}% |\n\n")
        
        f.write("## List of Missing Articles\n\n")
        f.write("Below is the complete list of missing articles. Each entry links to the original Banglapedia page, lists the corrected name/title searched, and provides a quick link to search Wikipedia.\n\n")
        
        f.write("| # | Banglapedia Article | Corrected Name / Title | Wikipedia Search |\n")
        f.write("| :---: | :--- | :--- | :--- |\n")
        
        # Sort by the corrected title for cleaner reading
        sorted_pairs = sorted(missing_pairs, key=lambda x: x[1].lower())
        
        for idx, (orig_title, fmt_title) in enumerate(sorted_pairs, 1):
            banglapedia_url = f"https://en.banglapedia.org/index.php?title={urllib.parse.quote(orig_title)}"
            wikipedia_search_url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(fmt_title)}"
            
            f.write(f"| {idx} | [{orig_title}]({banglapedia_url}) | {fmt_title} | [Search Wikipedia]({wikipedia_search_url}) |\n")
            
    print(f"Successfully generated {OUTPUT_FILE}!")

def main():
    print("=" * 60)
    print("Banglapedia vs English Wikipedia Cross-Referencer (Name-Corrected)")
    print("=" * 60)
    
    # 1. Fetch all titles from Banglapedia
    banglapedia_titles = fetch_banglapedia_titles()
    if not banglapedia_titles:
        print("Error: No articles fetched from Banglapedia. Exiting.")
        sys.exit(1)
        
    # 2. Format names and build mapping dict
    formatted_to_originals = {}
    for title in banglapedia_titles:
        fmt_t = clean_and_format_title(title)
        formatted_to_originals.setdefault(fmt_t, []).append(title)
        
    formatted_titles = sorted(list(formatted_to_originals.keys()))
    
    # 3. Check each formatted title on English Wikipedia
    missing_pairs, existing_count = check_wikipedia_existence(formatted_titles, formatted_to_originals)
    
    # 4. Write markdown report
    generate_markdown_report(len(banglapedia_titles), missing_pairs, existing_count)
    
    print("\nAll tasks completed successfully!")
    print("=" * 60)

if __name__ == "__main__":
    main()
