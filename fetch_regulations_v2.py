import os
import requests
import pandas as pd
from tqdm import tqdm
import time

# ── Settings ──────────────────────────────────────────────────────────────────
DOCKET_ID   = "CDC-2026-0199"
VERSION     = "v2"
SAVE_EVERY  = 100   # save progress every N comments
SLEEP_SECS  = 8     # seconds between detail requests (~450/hour)
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL            = "https://api.regulations.gov/v4"
REGULATIONS_API_KEY = os.environ.get("REGULATIONS_API_KEY", "DEMO_KEY")
HEADERS             = {"Accept": "application/json", "X-Api-Key": REGULATIONS_API_KEY}
OUTPUT_CSV          = f"detailed_comments_{DOCKET_ID}_{VERSION}.csv"

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
    print(f"  Gave up on {comment_id} after {max_retries} retries")
    return {}, {}

def extract_attachment_urls(response_json):
    included = response_json.get("included", [])
    urls = []
    for inc in included:
        if inc.get("type") == "attachments":
            file_formats = inc.get("attributes", {}).get("fileFormats", [])
            for ff in file_formats:
                url = ff.get("fileUrl")
                if url:
                    urls.append(url)
    return ", ".join(urls) if urls else None

def save_progress(records, output_csv):
    df = pd.DataFrame(records)
    df.to_csv(output_csv, index=False)
    print(f"  💾 Progress saved: {len(records)} records to {output_csv}")

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Docket:     {DOCKET_ID}")
    print(f"Version:    {VERSION}")
    print(f"Output:     {OUTPUT_CSV}")
    print(f"Pace:       {SLEEP_SECS}s between requests (~{3600//SLEEP_SECS}/hour)")
    print(f"Auto-save:  every {SAVE_EVERY} comments")
    print(f"{'='*60}\n")

    # ── Find resume point from existing output CSV ─────────────────────────────
    if os.path.exists(OUTPUT_CSV):
        existing_df   = pd.read_csv(OUTPUT_CSV)
        filled_rows   = existing_df[existing_df["Comment"].notna() & (existing_df["Comment"] != "")]
        if not filled_rows.empty:
            start_from_id = filled_rows["Comment ID"].iloc[-1]
            print(f"Resuming after comment ID: {start_from_id}")
            print(f"({len(filled_rows)} records already saved)")
            # Seed the buffer with existing records so saves are cumulative
            detailed_comments = existing_df.to_dict("records")
        else:
            start_from_id     = None
            detailed_comments = []
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
    request_count  = 0
    new_this_run   = 0

    try:
        for c in tqdm(all_comments, desc="Fetching details", unit="comment"):
            comment_id             = c.get("id")
            response_json, resp_headers = get_comment_details(comment_id)
            detail                 = response_json.get("data", {})
            attributes             = detail.get("attributes", {})
            attachment_urls        = extract_attachment_urls(response_json)

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
                "Attachment URLs":      attachment_urls,
                "URL":                  detail.get("links", {}).get("self"),
            })

            request_count += 1
            new_this_run  += 1

            # ── Rate limit tracking ────────────────────────────────────────────
            remaining = int(resp_headers.get("X-RateLimit-Remaining", -1))
            limit     = int(resp_headers.get("X-RateLimit-Limit", -1))

            if request_count % 50 == 0:
                print(f"  [{request_count} requests] Rate limit: {remaining}/{limit} remaining")
            if 0 < remaining < 50:
                print(f"  ⚠️  WARNING: Only {remaining} requests remaining!")

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
        print(f"\n✅ Done! {len(detailed_comments)} total records in {OUTPUT_CSV}")
    else:
        print("\nNo comments to save.")
