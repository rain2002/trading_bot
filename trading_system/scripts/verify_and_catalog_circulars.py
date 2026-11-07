import os
import urllib.request
import hashlib
from pypdf import PdfReader
from io import BytesIO
import pandas as pd
import re

os.makedirs('trading_system/data/circulars', exist_ok=True)

# Read the log of discovered valid press release URLs
with open(r'C:\Users\nitin\.gemini\antigravity\brain\d32f06ef-9034-47d9-8e57-b459acf2e424\.system_generated\tasks\task-2513.log', 'r') as f:
    lines = f.readlines()

urls = []
for l in lines:
    m = re.search(r'FOUND:\s+(https://www\.niftyindices\.com/Press_Release/ind_prs\d+\.pdf)', l)
    if m:
        urls.append(m.group(1))

urls = sorted(list(set(urls)))
print(f"Total discovered URLs from scan: {len(urls)}")

# Download and inspect each one for NIFTY 50 replacements
nifty50_docs = []

for u in urls:
    fn = os.path.basename(u)
    dest = os.path.join('trading_system/data/circulars', fn)
    
    # Download if not present
    if not os.path.exists(dest):
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
                with open(dest, 'wb') as f_out:
                    f_out.write(data)
        except Exception as e:
            print(f"Download failed {fn}: {e}")
            continue
    else:
        with open(dest, 'rb') as f_in:
            data = f_in.read()

    sha = hashlib.sha256(data).hexdigest()

    try:
        reader = PdfReader(BytesIO(data))
        text = "\n".join([p.extract_text() or "" for p in reader.pages])
        
        # Check if it has NIFTY 50 and replacement/exclusion/inclusion
        t_low = text.lower()
        if ("nifty 50" in t_low or "cnx nifty" in t_low) and ("replacement" in t_low or "exclusion" in t_low or "inclusion" in t_low):
            # Check if it has effective date or company names
            m_eff = re.search(r'effective (?:from|on)\s+([A-Za-z0-9, ]+)', text, re.I)
            eff_str = m_eff.group(1).strip() if m_eff else ""
            nifty50_docs.append({
                "filename": fn,
                "url": u,
                "sha256": sha,
                "size": len(data),
                "effective_hint": eff_str[:50]
            })
            print(f"MATCH: {fn} | SHA: {sha[:16]}... | Hint: {eff_str[:40]}")
    except Exception as e:
        print(f"Parse error {fn}: {e}")

print(f"\nFound {len(nifty50_docs)} documents covering NIFTY 50 changes!")
with open("trading_system/data/circulars/verified_docs.json", "w") as f_json:
    import json
    json.dump(nifty50_docs, f_json, indent=2)
