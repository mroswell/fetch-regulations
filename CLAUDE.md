# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
This project fetches, analyzes, and displays public comments submitted to federal advisory 
committee dockets on regulations.gov. The initial focus is CDC-2026-0199, a docket related 
to ACIP (Advisory Committee on Immunization Practices) and/or VRBPAC (Vaccines and Related 
Biological Products Advisory Committee).

The goal is to make federal advisory committee public comments accessible, searchable, 
and analyzable for researchers, journalists, advocates, and the general public.
A key design goal is to surface patient stories — comments from people who were personally 
injured, or whose family member or friend was injured or died following vaccination.

## Repository
- GitHub: github.com/mroswell/committeecomments.com
- Domain: committeecomments.com
- Hosting: GitHub Pages served from root of main branch

This repository serves two functions:
1. **Data pipeline** — GitHub Actions workflows that fetch comments from
   regulations.gov and save them as CSV files
2. **Website** — static GitHub Pages site served from the repository root
   at committeecomments.com

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
- `scripts/fetch_regulations_comments.py` — exists, working
- `scripts/perspective_analysis.py` — **planned, not yet created**
- `scripts/csv_to_json.py` — **planned, not yet created**
- `index.html` — **planned, not yet created**

## Repository Structure
```
committeecomments.com/
├── CLAUDE.md
├── CNAME                                  ← committeecomments.com
├── index.html                             ← website root
├── requirements.txt
├── .env                                   ← local API keys, never committed
├── .gitignore
├── .github/
│   └── workflows/
│       └── fetch_regulations_comments.yml
├── scripts/
│   ├── fetch_regulations_comments.py   ← fetches comments from regulations.gov
│   ├── perspective_analysis.py            ← adds perspective/tags/etc to CSV
│   └── csv_to_json.py                     ← converts CSV to JSON for website
└── data/
    ├── csv/
    │   └── comments_CDC-2026-0199.csv     ← single source of truth
    └── json/
        └── comments_CDC-2026-0199.json    ← generated from CSV for website
```

## Environment Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this):
```
ANTHROPIC_API_KEY=your_key_here
REGULATIONS_API_KEY=your_key_here
```

Load in Python scripts with:
```python
from dotenv import load_dotenv
load_dotenv()
```

## Data Fetching
- Uses regulations.gov v4 API
- API key stored as GitHub Actions secret `REGULATIONS_API_KEY`
- Fetches all documents in the docket, then all comment stubs, then detail for each comment
- Uses `include=attachments` to capture attachment URLs
- Paces requests with `time.sleep(8)` to stay under 1,000 requests/hour rate limit
- Saves progress every 20 comments to runner filesystem
- Auto-resumes from last saved comment if run is interrupted
- Commits final CSV to `data/csv/comments_CDC-2026-0199.csv` via GitHub Actions
- `permissions: contents: write` required in workflow YAML for commit step
- `git pull --rebase` before `git push` prevents push rejection if repo
  was updated during the run

## CSV Fields
All field names are lowercase with underscores.

### Fully Populated (reliable for CDC-2026-0199)
- `comment_id` — unique identifier e.g. CDC-2026-0199-0001
- `withdrawn` — boolean
- `posted_date`
- `agency_id`
- `document_type`
- `docket_id`
- `title`
- `url` — API URL, convert to human-readable on website by replacing
  `https://api.regulations.gov/v4/comments/` with `https://www.regulations.gov/comment/`
- `page_count`
- `tracking_number` — 1 missing value
- `received_date` — 1 missing value
- `comment` — full comment text, contains HTML, render as innerHTML not textContent. 1 missing value.

### Partially Populated (useful for CDC-2026-0199)
- `first_name` — present for 2354 of 2441 comments
- `last_name` — present for 2355 of 2441 comments
- `attachment_urls` — present for 222 of 2441 comments, comma-separated URLs
- `organization` — present for 69 of 2441 comments
- `reason_withdrawn` — only 1 value

### Empty for CDC-2026-0199 (kept for future dockets)
postmark_date, restrict_reason, country, document_id, zip, comment_on_id,
doc_abstract, document_subtype, state_or_province, legacy_id, city,
gov_agency, gov_agency_type, restrict_reason_type

## Website Filter Implications (CDC-2026-0199)
- **Perspective filter** ✅ — added by perspective analysis script
- **Vaccine injured filter** ✅ — separate flag, independent of perspective
- **Has attachment filter** ✅ — 222 comments have attachments
- **Org vs individual filter** ✅ — 69 comments have an organization
- **State filter** ❌ — state_or_province is completely empty for this docket
- **Full text search** ✅ — search comment, title, first_name, last_name, organization

## Analysis Fields (added in place to comments_CDC-2026-0199.csv)
- `perspective`: pro-vaccine | nuanced-mostly-pro | uncertain | vaccine-hesitant | anti-vaccine
- `vaccine_injured`: "true" if commenter or their family member or friend was injured 
  or died following vaccination, otherwise empty
- `vaccines_mentioned`: comma-separated vaccine names found in comment
- `tags`: comma-separated topics found in comment
- `references`: "references" if comment contains citations/links to research, else empty
- `duplicate`: "duplicate" if comment is a form letter or near-duplicate, else empty

## Perspective Analysis Script (`scripts/perspective_analysis.py`)

### Naming Convention
We use the term "perspective" rather than "sentiment" for the classification
field displayed on the website, because commenters — particularly those
describing vaccine injuries — are expressing informed perspectives grounded
in personal experience, not merely emotional sentiment.

The underlying technique is sentiment analysis via the Claude API. The output
field is named `perspective` in the CSV and on the website. Do not rename
`perspective` back to `sentiment` — the choice is intentional and documented here.

### Script Behavior
- Reads `data/csv/comments_CDC-2026-0199.csv`
- Sends each comment to the Claude API (claude-sonnet-4-20250514)
- Adds analysis columns directly to the same CSV (no separate output file)
- Skips rows that already have a perspective value (auto-resume)
- Saves the entire dataframe back to the CSV every 20 records
- Uses `time.sleep(1)` between API calls
- Reads API key from environment variable `ANTHROPIC_API_KEY`

### Perspective Values (in order)
```
pro-vaccine | nuanced-mostly-pro | uncertain | vaccine-hesitant | anti-vaccine
```

### Perspective Guidance
- `pro-vaccine` — clearly and broadly supportive of vaccines
- `nuanced-mostly-pro` — generally supportive but raises some concerns
- `uncertain` — ambiguous or balanced
- `vaccine-hesitant` — raising safety concerns, calling for more transparency,
  or skeptical of vaccine policy. Many people who experienced vaccine injuries 
  do not consider themselves anti-vaccine — use "vaccine-hesitant" for these 
  cases unless they are clearly and broadly opposed to all vaccines.
- `anti-vaccine` — clearly and broadly opposed to vaccines
- Vaccine injury is a legitimate concern, not misinformation
- Do not editorialize about the commenter's motives or credibility

### vaccine_injured Flag Guidance
- Independent of perspective — someone can be "pro-vaccine" AND vaccine_injured,
  or "anti-vaccine" AND vaccine_injured
- Set to "true" if the commenter describes:
  - A personal experience of injury affecting themselves, OR
  - Injury or death affecting a family member or friend
  following vaccination
- Do NOT set to "true" when a commenter merely acknowledges that rare adverse 
  events exist as part of a broader policy argument, with no personal connection
- This flag exists to surface patient stories on the website

### Tag Guidance
Tags describe what the comment is about, neutrally and descriptively.
Do not use tags that editorialize or dismiss the commenter's perspective.

Available tags:
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

## CSV to JSON Conversion Script (`scripts/csv_to_json.py`)
- Reads `data/csv/comments_CDC-2026-0199.csv`
- Converts `url` field from API format to human-readable format:
  replace `https://api.regulations.gov/v4/comments/` with `https://www.regulations.gov/comment/`
- Replaces NaN with empty string
- Writes to `data/json/comments_CDC-2026-0199.json`
- Run after perspective analysis is complete

## Data Pipeline
```
regulations.gov API
       ↓
data/csv/comments_CDC-2026-0199.csv         (fetch script)
       ↓
data/csv/comments_CDC-2026-0199.csv         (perspective_analysis.py adds columns in place)
       ↓
data/json/comments_CDC-2026-0199.json       (csv_to_json.py)
       ↓
index.html                                  (loads JSON at runtime)
```

## Website Goals
The website is the primary deliverable. It should make 2,400+ public comments
accessible and useful for researchers, journalists, advocates, and the general public.
A key goal is to surface patient stories.

### Core Features
1. **Browse all comments** — paginated list of all comments, default sorted by date
2. **Full text search** — search within comment text, names, organizations
3. **Filter by perspective** — dropdown: pro-vaccine | nuanced-mostly-pro | uncertain | vaccine-hesitant | anti-vaccine
4. **Filter by vaccine injured** — show only comments with vaccine_injured flag
5. **Filter by organization vs individual** — based on whether organization field is populated
6. **Filter by has attachment** — based on whether attachment_urls field is populated
7. **Filter by tags** — filter by topic tags assigned during perspective analysis
8. **Find duplicates** — view comments flagged as duplicates grouped together
9. **Find similar comments** — view comments grouped by similarity

### Each Comment Card Should Show
- Perspective label (color coded, consistent color per perspective value)
- Vaccine injured indicator (if vaccine_injured = "true") — visually distinct,
  to help surface patient stories
- Name (first_name + last_name if available)
- Organization (if available)
- state_or_province (if available, empty for this docket)
- posted_date
- Comment text (rendered as innerHTML, not stripped)
- Tags (if any)
- Attachment links (clickable, opening on regulations.gov)
- Link to original comment on regulations.gov (human-readable URL)
- Duplicate indicator if flagged

### Technical Approach
- Static GitHub Pages site (no server, no database)
- All comment data loaded from `data/json/comments_CDC-2026-0199.json`
- Full text search using Fuse.js (client-side search library)
- Filtering and sorting done entirely in JavaScript
- Pagination to handle 2,400+ comments without performance issues
- Mobile friendly

## GitHub Pages Setup
- GitHub Pages served from root of main branch
- `CNAME` file in repo root contains: `committeecomments.com`
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
- All CSV field names are lowercase with underscores
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
- `vaccine_injured` is a separate boolean flag independent of perspective
- Convert `url` field from API format to human-readable format in csv_to_json.py