import os
import requests
import pandas as pd
from tqdm import tqdm
import time

# ── Settings ──────────────────────────────────────────────────────────────────
DOCKET_ID     = "CDC-2026-0199"
BATCH_NUMBER  = int(os.environ.get("BATCH_NUMBER", 1))  # set via GitHub Actions input
TOTAL_BATCHES = 3                                         # informational only
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL            = "https://api.regulations.gov/v4"
REGULATIONS_API_KEY = os.environ.get("REGULATIONS_API_KEY", "DEMO_KEY")
HEADERS             = {"Accept": "application/json", "X-Api-Key": REGULATIONS_API_KEY}

def batch_csv_name(docket_id, batch_num):
    return f"detailed_comments_{docket_id}_batch{batch_num}.csv"

CURRENT_CSV  = batch_csv_name(DOCKET_ID, BATCH_NUMBER)
PREVIOUS_CSV = batch_csv_name(DOCKET_ID, BATCH_NUMBER - 1) if BATCH_NUMBER > 1 else None

def get_documents(docket_id):
    url    = f"{BASE_URL}/documents"
    params = {"filter[docketId]": docket_id, "page[size]": 250}
    docs   = []
    page   = 1
    while True:
        params["page[number]"] = page
        resp = requests.get(url, headers=HEADERS, params=params)
        data = resp.json()
        docs.extend(data.get("data", []))
        if "next" not in data.get("links", {}):
            break
        page += 1
    return docs

def get_comments_for_document(object_id):
    url      = f"{BASE_URL}/comments"
    comments = []
    page     = 1
    while True:
        print(f"  Fetching comment list for document {object_id}, page {page}")
        params = {
            "filter[commentOnId]": object_id,
            "page[size]":          250,
            "page[number]":        page,
            "sort":                "lastModifiedDate,documentId"
        }
        try:
            resp           = requests.get(url, headers=HEADERS, params=params)
            data           = resp.json()
            comments_batch = data.get("data", [])
            if not comments_batch:
                break
            comments.extend(comments_batch)
            page += 1
            time.sleep(0.2)
        except requests.exceptions.RequestException as e:
            print(f"  Error fetching comments for document {object_id}: {e}")
            break
    return comments

def get_comment_details(comment_id, max_retries=5):
    url = f"{BASE_URL}/comments/{comment_id}"
    for attempt in range(max_retries):
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.json().get("data", {}), resp.headers
        elif resp.status_code == 429:
            wait = 60 * (attempt + 1)
            print(f"  Rate limited on {comment_id}. Waiting {wait}s (attempt {attempt+1}/{max_retries})...")
            time.sleep(wait)
        else:
            print(f"  Failed to fetch {comment_id}: HTTP {resp.status_code}")
            return {}, resp.headers
    print(f"  Gave up on {comment_id} after {max_retries} retries")
    return {}, {}

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Docket:        {DOCKET_ID}")
    print(f"Batch:         {BATCH_NUMBER} of ~{TOTAL_BATCHES}")
    print(f"Output CSV:    {CURRENT_CSV}")
    if PREVIOUS_CSV:
        print(f"Previous CSV:  {PREVIOUS_CSV}")
    print(f"{'='*60}\n")

    # ── Find resume point from previous batch CSV ──────────────────────────────
    if PREVIOUS_CSV and os.path.exists(PREVIOUS_CSV):
        prev_df     = pd.read_csv(PREVIOUS_CSV)
        filled_rows = prev_df[prev_df["Comment"].notna() & (prev_df["Comment"] != "")]
        if not filled_rows.empty:
            start_from_id = filled_rows["Comment ID"].iloc[-1]
            print(f"Last fully-fetched comment ID: {start_from_id}")
            print(f"Resuming after row {filled_rows.index[-1]+1} of {len(prev_df)}")
        else:
            start_from_id = None
            print("No filled rows found in previous CSV. Starting from beginning.")
    else:
        start_from_id = None
        if BATCH_NUMBER > 1:
            print(f"Warning: BATCH_NUMBER is {BATCH_NUMBER} but {PREVIOUS_CSV} not found. Starting from beginning.")
        else:
            print("Batch 1 — starting from the beginning.")

    # ── Fetch all documents in docket ──────────────────────────────────────────
    documents = get_documents(DOCKET_ID)
    print(f"\nFound {len(documents)} documents in docket {DOCKET_ID}")

    # ── Fetch all comment stubs ────────────────────────────────────────────────
    all_comments = []
    for doc in tqdm(documents, desc="Fetching comment lists"):
        object_id = doc["attributes"]["objectId"]
        comments  = get_comments_for_document(object_id)
        print(f"  Document {object_id}: {len(comments)} comments")
        all_comments.extend(comments)
    print(f"\nTotal comments in docket: {len(all_comments)}")

    # ── Skip comments already covered in previous batch ───────────────────────
    if start_from_id:
        ids = [c.get("id") for c in all_comments]
        if start_from_id in ids:
            resume_index = ids.index(start_from_id) + 1
            all_comments = all_comments[resume_index:]
            print(f"Skipping first {resume_index} comments. {len(all_comments)} remaining.")
        else:
            print(f"Warning: resume ID {start_from_id} not found in comment list. Starting from beginning.")

    # ── Fetch details ──────────────────────────────────────────────────────────
    detailed_comments = []
    request_count     = 0

    try:
        for c in tqdm(all_comments, desc=f"Fetching details (batch {BATCH_NUMBER})"):
            comment_id           = c.get("id")
            detail, resp_headers = get_comment_details(comment_id)
            attributes           = detail.get("attributes", {})

            detailed_comments.append({
                "Comment ID":           comment_id,
                "Tracking Number":      attributes.get("trackingNbr"),
                "Title":                attributes.get("title"),
                "Document ID":          attributes.get("documentId"),
                "Docket ID":            attributes.get("docketId"),
                "Comment On ID":        attributes.get("commentOnId"),
                "Document Type":        attributes.get("documentType"),
                "Document Subtype":     attributes.get("subtype"),
                "Agency ID":            attributes.get("agencyId"),
                "Posted Date":          attributes.get("postedDate"),
                "Received Date":        attributes.get("receiveDate"),
                "Postmark Date":        attributes.get("postmarkDate"),
                "Withdrawn":            attributes.get("withdrawn"),
                "Restrict Reason Type": attributes.get("restrictReasonType"),
                "Restrict Reason":      attributes.get("restrictReason"),
                "Reason Withdrawn":     attributes.get("reasonWithdrawn"),
                "First Name":           attributes.get("firstName"),
                "Last Name":            attributes.get("lastName"),
                "City":                 attributes.get("city"),
                "State or Province":    attributes.get("stateProvinceRegion"),
                "Zip":                  attributes.get("zip"),
                "Country":              attributes.get("country"),
                "Organization":         attributes.get("organization"),
                "Gov Agency":           attributes.get("govAgency"),
                "Gov Agency Type":      attributes.get("govAgencyType"),
                "Legacy ID":            attributes.get("legacyId"),
                "Page Count":           attributes.get("pageCount"),
                "Doc Abstract":         attributes.get("docAbstract"),
                "Comment":              attributes.get("comment"),
                "URL":                  detail.get("links", {}).get("self"),
            })

            # ── Rate limit tracking ────────────────────────────────────────────
            request_count += 1
            remaining = int(resp_headers.get("X-RateLimit-Remaining", -1))
            limit     = int(resp_headers.get("X-RateLimit-Limit", -1))

            if request_count % 50 == 0:
                print(f"  [{request_count} requests made] Rate limit: {remaining}/{limit} remaining")
            if 0 < remaining < 50:
                print(f"  ⚠️  WARNING: Only {remaining} requests remaining!")

    except Exception as e:
        print(f"\nException occurred: {e}")
        print("Writing buffered comments to CSV before exiting...")

    # ── Save ───────────────────────────────────────────────────────────────────
    if detailed_comments:
        new_df = pd.DataFrame(detailed_comments)
        new_df.to_csv(CURRENT_CSV, index=False)
        print(f"\nSaved {len(new_df)} records to {CURRENT_CSV}")
    else:
        print("\nNo new comments to save.")
