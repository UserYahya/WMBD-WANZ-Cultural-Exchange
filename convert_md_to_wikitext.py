import re

md_file = "missing_banglapedia_articles.md"
wikitext_file = "missing_banglapedia_articles.wikitext"

print(f"Reading {md_file}...")
with open(md_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

total_count = 0
found_count = 0
missing_count = 0
coverage_gap = ""

# Parse summary statistics
for line in lines:
    if "**Total Banglapedia Articles**" in line:
        total_count = line.split("|")[2].strip()
    elif "**Found on English Wikipedia**" in line:
        found_count = line.split("|")[2].strip()
    elif "**Missing from English Wikipedia**" in line:
        missing_count = line.split("|")[2].strip()
    elif "**Coverage Gap (%)**" in line:
        coverage_gap = line.split("|")[2].strip()

print("Generating Wikitext table...")
rows = []
for line in lines:
    line = line.strip()
    # Check if the line is a table row (starts and ends with |)
    if line.startswith("|") and line.endswith("|"):
        parts = [p.strip() for p in line.split("|")]
        # Skip header rows and separators
        if len(parts) >= 5 and parts[1].isdigit():
            idx = parts[1]
            banglapedia_cell = parts[2]
            corrected_title = parts[3]
            
            # Parse markdown link [text](url)
            match = re.match(r'\[(.*?)\]\((.*?)\)', banglapedia_cell)
            if match:
                orig_title = match.group(1)
                url = match.group(2)
                
                # Format into Wikitext external link and wikilink
                wikitext_row = f"|-\n| {idx} || [{url} {orig_title}] || [[{corrected_title}]]"
                rows.append(wikitext_row)

print(f"Writing to {wikitext_file}...")
with open(wikitext_file, "w", encoding="utf-8") as f:
    f.write("= Banglapedia Articles Missing from English Wikipedia =\n\n")
    f.write("This table lists articles present on the English Banglapedia which do not have a corresponding page on English Wikipedia.\n\n")
    
    f.write(f"* '''Total Banglapedia Articles Checked:''' {total_count}\n")
    f.write(f"* '''Found on English Wikipedia:''' {found_count}\n")
    f.write(f"* '''Missing from English Wikipedia:''' {missing_count}\n")
    f.write(f"* '''Coverage Gap:''' {coverage_gap}\n\n")
    
    f.write("{| class=\"wikitable sortable\"\n")
    f.write("! # !! Banglapedia Article !! Corrected Name / Title\n")
    f.write("\n".join(rows))
    f.write("\n|}\n")

print(f"Successfully generated {wikitext_file}!")
