# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This project fetches, analyzes, and displays public comments submitted to federal advisory committee dockets on regulations.gov. The initial focus is CDC-2026-0199, a docket related to ACIP (Advisory Committee on Immunization Practices) and/or VRBPAC (Vaccines and Related 
Biological Products Advisory Committee).

The goal is to make federal advisory committee public comments accessible, searchable, and analyzable for researchers, journalists, advocates, and the general public.

## Repository
- GitHub: github.com/mroswell/committeecomments.com
- Domain: committeecomments.com
- Hosting: GitHub Pages served from root of main branch

This repository serves two functions:
1. **Data pipeline** — GitHub Actions workflows that fetch comments from
   regulations.gov and save them as CSV files
2. **Website** — static GitHub Pages site served from the repository root
   at committeecomments.com (not yet built)

## Commands

```bash
# Environment setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Fetch comments from regulations.gov (requires REGULATIONS_API_KEY in .env)
python scripts/fetch_regulations_comments.py

# Run perspective analysis (requires ANTHROPIC_API_KEY in .env) — NOT YET CREATED
python scripts/perspective_analysis.py

# Convert CSV to JSON for website — NOT YET CREATED
python scripts/csv_to_json.py

# Trigger the fetch workflow manually via GitHub Actions
gh workflow run "Fetch Regulations.gov Comments"
```

## Current State
- `scripts/fetch_regulations_comments.py` — exists, working, fetches comments from regulations.gov API
- `scripts/perspective_analysis.py` — **planned, not yet created**
- `scripts/csv_to_json.py` — **planned, not yet created**
- `index.html` — **planned, not yet created**

## Repository Structure
```
committeecomments.com/
├── CLAUDE.md
├── CNAME                              ← committeecomments.com
├── requirements.txt
├── .env                               ← local API keys, never committed
├── .gitignore
├── .github/
│   └── workflows/
│       └── fetch_regulations_comments.yml
├── scripts/
│   └── fetch_regulations_comments.py  ← fetches comments from regulations.gov
└── data/
    ├── csv/
    │   └── comments_CDC-2026-0199.csv ← single source of truth
    └── json/
        └── comments_CDC-2026-0199.json ← generated from CSV for website (planned)
```

## Environment Setup
Create a `.env` file in the project root (never commit this):
```
ANTHROPIC_API_KEY=your_key_here
REGULATIONS_API_KEY=your_key_here
```

Python scripts load these via `python-dotenv`:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Data Fetching
- Uses regulations.gov v4 API
- API key stored as GitHub Actions secret `REGULATIONS_API_KEY`
- Fetches all documents in the docket, then all comment stubs, then detail for each comment
- Uses `include=attachments` to capture attachment URLs
- Paces requests with `time.sleep(4)` to stay under 1,000 requests/hour rate limit
- Saves progress every 20 comments to runner filesystem
- Auto-resumes from last saved comment if run is interrupted
- Commits final CSV to `data/csv/comments_CDC-2026-0199.csv` via GitHub Actions
- `permissions: contents: write` required in workflow YAML for commit step
- `git pull --rebase` before `git push` prevents push rejection if repo
  was updated during the run

## CSV Fields

### Fully Populated (reliable for CDC-2026-0199)
- `Comment_ID` — unique identifier e.g. CDC-2026-0199-0001
- `Withdrawn` — boolean
- `Posted_Date`
- `Agency_ID`
- `Document_Type`
- `Docket_ID`
- `Title`
- `URL` — link to comment on regulations.gov
- `Page_Count`
- `Tracking_Number` — 1 missing value
- `Received_Date` — 1 missing value
- `Comment` — full comment text, contains HTML, render as innerHTML not textContent. 1 missing value.

### Partially Populated (useful for CDC-2026-0199)
- `First_Name` — present for 2354 of 2441 comments
- `Last_Name` — present for 2355 of 2441 comments
- `Attachment_URLs` — present for 222 of 2441 comments, comma-separated URLs
- `Organization` — present for 69 of 2441 comments
- `Reason_Withdrawn` — only 1 value

### Empty for CDC-2026-0199 (keep for future dockets)
Postmark_Date, Restrict_Reason, Country, Document_ID, Zip, Comment_On_ID,
Doc_Abstract, Document_Subtype, State_or_Province, Legacy_ID, City,
Gov_Agency, Gov_Agency_Type, Restrict_Reason_Type

## Website Filter Implications (CDC-2026-0199)
- **Perspective filter** ✅ — added by perspective analysis script
- **Has attachment filter** ✅ — 222 comments have attachments
- **Org vs individual filter** ✅ — 69 comments have an organization
- **State filter** ❌ — State_or_Province is completely empty for this docket
- **Full text search** ✅ — search Comment, Title, First_Name, Last_Name, Organization

## Analysis Fields (added in place to comments_CDC-2026-0199.csv)
- `perspective`: pro-vaccine | nuanced-mostly-pro | uncertain | nuanced-mostly-anti | anti-vaccine
- `vaccines_mentioned`: comma-separated vaccine names found in comment
- `tags`: comma-separated topics found in comment
- `references`: "references" if comment contains citations/links to research, else empty
- `duplicate`: "duplicate" if comment is a near-duplicate of another, else empty

## Perspective Analysis Script
We use the term "perspective" rather than "sentiment" for the classification
field displayed on the website, because commenters — particularly those
describing vaccine injuries — are expressing informed perspectives grounded
in personal experience, not merely emotional sentiment.

The underlying technique is sentiment analysis via the Claude API. The output
field is named `perspective` in the CSV and on the website. Do not rename
`perspective` back to `sentiment` — the choice is intentional and documented here.

The script (`scripts/perspective_analysis.py`):
- Reads `data/csv/comments_CDC-2026-0199.csv`
- Sends each comment to the Claude API (claude-sonnet-4-20250514)
- Uses sentiment analysis techniques to classify each comment
- Adds analysis columns directly to the same CSV (no separate output file)
- Processes in batches and saves progress every 20 records
- Auto-resumes if interrupted (skips rows that already have a perspective value)
- Uses `time.sleep(1)` between API calls
- Reads API key from environment variable `ANTHROPIC_API_KEY`

### Perspective Guidance
- Perspective labels in order from most to least pro-vaccine:
  pro-vaccine | nuanced-mostly-pro | uncertain | nuanced-mostly-anti | anti-vaccine
- Many commenters who experienced vaccine injuries do not consider themselves
  "anti-vaccine" — they may be pro-safety or pro-transparency. Use
  "nuanced-mostly-anti" for these cases rather than "anti-vaccine" unless
  the comment is clearly and broadly anti-vaccine.
- Vaccine injury is treated as a legitimate concern, not misinformation.
- Do not editorialize about the commenter's motives or credibility.

### Tag Guidance
Tags describe what the comment is about, neutrally and descriptively.
Do not use tags that editorialize or dismiss the commenter's perspective.

Tags should include but are not limited to:
- `side_effects`
- `efficacy`
- `mandates`
- `natural_immunity`
- `personal_experience`
- `religious_exemption`
- `philosophical_exemption`
- `scientific_citations`
- `vaccine_injury`
- `transparency`
- `safety_concern`
- `myocarditis`
- `informed_consent`
- `VAERS`
- `long_covid`
- `boosters`
- `children`
- `elderly`
- `medical_exemption`
- `policy_criticism`
- `manufacturer_liability`
- `risk_benefit_analysis`
- `adverse_events`
- `death`
- `disability`

## CSV to JSON Conversion Script
The script (`scripts/csv_to_json.py`):
- Reads `data/csv/comments_CDC-2026-0199.csv`
- Converts to `data/json/comments_CDC-2026-0199.json`
- Replaces NaN with empty string
- Should be run after perspective analysis is complete
- Output JSON is what the website loads at runtime

## Website Goals
The website is the primary deliverable. It should make 2,400+ public comments
accessible and useful for researchers, journalists, advocates, and the general public.

### Core Features
1. **Browse all comments** — paginated list of all comments, default sorted by date
2. **Full text search** — search within comment text, names, organizations
3. **Filter by perspective** — filter to see only pro-vaccine, anti-vaccine, etc.
4. **Filter by organization vs individual** — based on whether Organization field is populated
5. **Filter by has attachment** — based on whether Attachment_URLs field is populated
6. **Filter by tags** — filter by topic tags assigned during perspective analysis
7. **Find duplicates** — view comments flagged as duplicates grouped together
8. **Find similar comments** — view comments grouped by similarity

### Each Comment Card Should Show
- Perspective label (color coded, consistent color per perspective value)
- Name (First_Name + Last_Name if available)
- Organization (if available)
- State_or_Province (if available, empty for this docket)
- Posted_Date
- Comment text (rendered as HTML, not stripped)
- Tags (if any)
- Attachment links (clickable, opening on regulations.gov)
- Link to original comment on regulations.gov
- Duplicate/similar indicator if flagged

### Technical Approach
- Static GitHub Pages site (no server, no database)
- All comment data loaded from `data/json/comments_CDC-2026-0199.json`
- Full text search using Fuse.js (client-side search library)
- Filtering and sorting done entirely in JavaScript
- Pagination to handle 2,400+ comments without performance issues
- Mobile friendly

### Data Pipeline
```
regulations.gov API
       ↓
data/csv/comments_CDC-2026-0199.csv  (fetch script)
       ↓
data/csv/comments_CDC-2026-0199.csv  (perspective analysis adds columns in place)
       ↓
data/json/comments_CDC-2026-0199.json  (csv_to_json.py)
       ↓
index.html  (loads JSON at runtime)
```

## GitHub Pages Setup
- GitHub Pages served from root of main branch
- Add `CNAME` file to repo root containing: `committeecomments.com`
- In repo Settings → Pages → set source to main branch → / (root)
- Set custom domain to `committeecomments.com`

DNS records at registrar:
```
A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
CNAME www  mroswell.github.io
```

## Future Dockets
This site is designed to eventually cover multiple ACIP and VRBPAC dockets.
When adding a new docket:
- Update `DOCKET_ID` in `scripts/fetch_regulations_comments.py`
- Re-run the GitHub Actions workflow to fetch comments
- Run perspective analysis on the new CSV
- Convert to JSON and add to `data/json/`
- Update site navigation to include the new docket

## Technical Notes
- Most agency-configurable fields came back empty for this docket
- regulations.gov API rate limit is 1,000 requests/hour
- GitHub Actions has a 6-hour hard timeout for hosted runners
- Comment text should be rendered as innerHTML not textContent
- Vaccine injury is treated as a legitimate concern, not misinformation
- Fuse.js is recommended for client-side full text search on a static site
- Consider paginating at 50 comments per page for performance
- Do not use tags that editorialize or dismiss commenters' perspectives
- The field is named `perspective` not `sentiment` — this is intentional,
  do not rename it