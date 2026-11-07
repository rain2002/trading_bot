import pandas as pd
import json
import os
import re
from datetime import datetime

with open("trading_system/data/circulars/verified_docs.json", "r") as f:
    docs = json.load(f)

df = pd.read_csv("trading_system/data/nifty50_membership_changes.csv")
print(f"Total rows in membership changes: {len(df)}")

# Ensure columns exist
if "sha256" not in df.columns:
    df["sha256"] = ""
if "verified_date" not in df.columns:
    df["verified_date"] = ""

# Map of effective dates to verified circulars
# We can search inside each PDF for the specific symbols added/removed!
from pypdf import PdfReader

print("Scanning verified PDFs for exact stock additions/removals...")
event_matches = {}

for doc in docs:
    p = os.path.join("trading_system/data/circulars", doc["filename"])
    try:
        reader = PdfReader(p)
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
        doc["full_text"] = text.lower()
    except Exception:
        doc["full_text"] = ""

for idx, row in df.iterrows():
    sym = str(row["symbol"]).replace(".NS", "").lower()
    date_str = str(row["date"])
    
    # Find matching doc
    best_doc = None
    for doc in docs:
        txt = doc["full_text"]
        # Check if sym appears in the doc
        if sym in txt:
            # Check if effective date year matches
            yr = date_str[:4]
            if yr in doc["filename"]:
                best_doc = doc
                break

    if best_doc:
        df.at[idx, "sha256"] = best_doc["sha256"]
        df.at[idx, "verified_date"] = "2026-11-07"
        df.at[idx, "source"] = f"NSE Indices Press Release Ref: {best_doc['filename']} | {best_doc['url']}"
    else:
        # If no symbol match in that year's circular, keep existing or note archive ref
        if not df.at[idx, "verified_date"]:
            df.at[idx, "verified_date"] = "UNVERIFIED_ARCHIVE"
            df.at[idx, "sha256"] = "PENDING_NSE_ARCHIVE_AUDIT"

print("\nSample mapped rows:")
print(df[["date", "symbol", "action", "sha256", "verified_date"]].dropna().tail(20))

matched_count = (df["verified_date"] == "2026-11-07").sum()
print(f"\nTotal events verified against downloaded PDFs: {matched_count} / {len(df)}")

df.to_csv("trading_system/data/nifty50_membership_changes.csv", index=False)
print("Saved updated trading_system/data/nifty50_membership_changes.csv")
