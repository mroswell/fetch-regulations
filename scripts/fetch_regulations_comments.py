import os
import requests
import pandas as pd
from tqdm import tqdm
import time

# ── Settings ──────────────────────────────────────────────────────────────────
DOCKET_ID   = "CDC-2026-0199"
SAVE_EVERY  = 20   # save progress every N comments
SLEEP_SECS  = 4     # seconds between detail requests
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL            = "https://api.regulations.gov/v4"
REGULATIONS_API_KEY = os.environ.get("REGULATIONS_API_KEY", "DEMO_KEY")
HEADERS             = {"Accept": "application/json", "X-Api-Key": REGULATIONS_API_KEY}

# Output to data/csv/ relative to the repo root (parent of scripts/)
REPO_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_CSV = os.path.join(REPO_ROOT, "data", "csv", f"comments_{DOCKET_ID}.csv")

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
    url    = f"{BASE_URL}/comments/{comment_id}"
    params = {"include": "attachments"}
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params)
            if resp.status_code == 200:
                return resp.json(), resp.headers
            elif resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  Rate limited on {comment_id}. Waiting {wait}s (attempt {attempt+1}/{max_retries})...")
                time.sleep(wait)
            else:
                print(f"  Failed to fetch {comment_id}: HTTP {resp.status_code}")
                return {}, resp.headers
        except requests.exceptions.RequestException as e:
            print(f"  Request error on {comment_id}: {e}")
            return {}, {}
    print(f"  Gave up on {comment_id} after {max_retries} retries")
    return {}, {}

def extract_attachment_urls(response_json):
    if not response_json:
        return None
    included = response_json.get("included", [])
    if not included:
        return None
    urls = []
    for inc in included:
        if not isinstance(inc, dict):
            continue
        if inc.get("type") == "attachments":
            file_formats = inc.get("attributes", {}).get("fileFormats", [])
            if not file_formats:
                continue
            for ff in file_formats:
                if not isinstance(ff, dict):
                    continue
                url = ff.get("fileUrl")
                if url:
                    urls.append(url)
    return ", ".join(urls) if urls else None

def save_progress(records, output_csv):
    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"  Progress saved: {len(records)} records to {output_csv}")

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Docket:     {DOCKET_ID}")
    print(f"Output:     {OUTPUT_CSV}")
    print(f"Pace:       {SLEEP_SECS}s between requests (~{3600//SLEEP_SECS}/hour)")
    print(f"Auto-save:  every {SAVE_EVERY} comments")
    print(f"{'='*60}\n")

    # ── Find resume point from existing output CSV ─────────────────────────────
    if os.path.exists(OUTPUT_CSV):
        existing_df = pd.read_csv(OUTPUT_CSV)
        filled_rows = existing_df[
            existing_df["comment"].notna() & (existing_df["comment"] != "")
        ]
        if not filled_rows.empty:
            start_from_id     = filled_rows["comment_id"].iloc[-1]
            detailed_comments = existing_df.to_dict("records")
            print(f"Resuming after comment ID: {start_from_id}")
            print(f"({len(filled_rows)} records already saved)")
        else:
            start_from_id     = None
            detailed_comments = []
            print("CSV exists but no filled rows found. Starting from beginning.")
    else:
        start_from_id     = None
        detailed_comments = []
        print("No existing CSV found. Starting from the beginning.")

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

    # ── Skip already-processed comments ───────────────────────────────────────
    if start_from_id:
        ids = [c.get("id") for c in all_comments]
        if start_from_id in ids:
            resume_index = ids.index(start_from_id) + 1
            all_comments = all_comments[resume_index:]
            print(f"Skipping first {resume_index} comments. {len(all_comments)} remaining.")
        else:
            print(f"Warning: resume ID {start_from_id} not found. Starting from beginning.")

    # ── Fetch details ──────────────────────────────────────────────────────────
    request_count = 0
    new_this_run  = 0

    try:
        for c in tqdm(all_comments, desc="Fetching details", unit="comment"):
            comment_id                  = c.get("id")
            response_json, resp_headers = get_comment_details(comment_id)
            detail                      = response_json.get("data", {}) if response_json else {}
            attributes                  = detail.get("attributes", {}) if detail else {}
            attachment_urls             = extract_attachment_urls(response_json)

            detailed_comments.append({
                "comment_id":           comment_id,
                "tracking_number":      attributes.get("trackingNbr"),
                "title":                attributes.get("title"),
                "document_id":          attributes.get("documentId"),
                "docket_id":            attributes.get("docketId"),
                "comment_on_id":        attributes.get("commentOnId"),
                "document_type":        attributes.get("documentType"),
                "document_subtype":     attributes.get("subtype"),
                "agency_id":            attributes.get("agencyId"),
                "posted_date":          attributes.get("postedDate"),
                "received_date":        attributes.get("receiveDate"),
                "postmark_date":        attributes.get("postmarkDate"),
                "withdrawn":            attributes.get("withdrawn"),
                "restrict_reason_type": attributes.get("restrictReasonType"),
                "restrict_reason":      attributes.get("restrictReason"),
                "reason_withdrawn":     attributes.get("reasonWithdrawn"),
                "first_name":           attributes.get("firstName"),
                "last_name":            attributes.get("lastName"),
                "city":                 attributes.get("city"),
                "state_or_province":    attributes.get("stateProvinceRegion"),
                "zip":                  attributes.get("zip"),
                "country":              attributes.get("country"),
                "organization":         attributes.get("organization"),
                "gov_agency":           attributes.get("govAgency"),
                "gov_agency_type":      attributes.get("govAgencyType"),
                "legacy_id":            attributes.get("legacyId"),
                "page_count":           attributes.get("pageCount"),
                "doc_abstract":         attributes.get("docAbstract"),
                "comment":              attributes.get("comment"),
                "attachment_urls":      attachment_urls,
                "url":                  detail.get("links", {}).get("self") if detail else None,
            })

            request_count += 1
            new_this_run  += 1

            # ── Rate limit tracking ────────────────────────────────────────────
            remaining = int(resp_headers.get("X-RateLimit-Remaining", -1))
            limit     = int(resp_headers.get("X-RateLimit-Limit", -1))

            if request_count % 50 == 0:
                print(f"  [{request_count} requests] Rate limit: {remaining}/{limit} remaining")
            if 0 < remaining < 50:
                print(f"  WARNING: Only {remaining} requests remaining!")

            # ── Periodic save ──────────────────────────────────────────────────
            if new_this_run % SAVE_EVERY == 0:
                save_progress(detailed_comments, OUTPUT_CSV)

            time.sleep(SLEEP_SECS)

    except Exception as e:
        print(f"\nException occurred: {e}")
        print("Saving progress before exiting...")

    # ── Final save ─────────────────────────────────────────────────────────────
    if detailed_comments:
        save_progress(detailed_comments, OUTPUT_CSV)
        print(f"\nDone! {len(detailed_comments)} total records in {OUTPUT_CSV}")
    else:
        print("\nNo comments to save.")
