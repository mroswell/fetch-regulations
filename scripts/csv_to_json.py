import os
import pandas as pd
import json

# ── Settings ──────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKET_ID = os.environ.get("DOCKET_ID", "CDC-2026-0199")
CSV_PATH = os.path.join(REPO_ROOT, "data", "csv", f"comments_{DOCKET_ID}.csv")
JSON_PATH = os.path.join(REPO_ROOT, "data", "json", f"comments_{DOCKET_ID}.json")

API_URL_PREFIX = "https://api.regulations.gov/v4/comments/"
HUMAN_URL_PREFIX = "https://www.regulations.gov/comment/"
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Reading:  {CSV_PATH}")
    df = pd.read_csv(CSV_PATH)

    # Replace NaN with empty string
    df = df.fillna("")

    # Convert url from API format to human-readable format
    df["url"] = df["url"].str.replace(API_URL_PREFIX, HUMAN_URL_PREFIX, regex=False)

    # Ensure output directory exists
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)

    # Write JSON
    records = df.to_dict(orient="records")
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)

    print(f"Written:  {JSON_PATH}")
    print(f"Records:  {len(records)}")
