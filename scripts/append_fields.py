import os
import json
import time
import pandas as pd
import anthropic
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# ── Settings ──────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(REPO_ROOT, "data", "csv", "comments_CDC-2026-0199.csv")
SAVE_EVERY = 20
SLEEP_SECS = 3
MODEL = "claude-sonnet-4-20250514"
# ──────────────────────────────────────────────────────────────────────────────

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Canonical vaccine names — keys are lowercase for matching
VACCINE_CANONICAL = {
    "pfizer": "Pfizer",
    "pfizer-biontech": "Pfizer-BioNTech",
    "biontech": "BioNTech",
    "comirnaty": "Comirnaty",
    "moderna": "Moderna",
    "spikevax": "Spikevax",
    "novavax": "Novavax",
    "nuvaxovid": "Nuvaxovid",
    "astrazeneca": "AstraZeneca",
    "vaxzevria": "Vaxzevria",
    "j&j": "J&J",
    "johnson & johnson": "J&J",
    "johnson and johnson": "J&J",
    "janssen": "Janssen",
    "mrna": "mRNA",
    "hpv": "HPV",
    "gardasil": "Gardasil",
    "dtap": "DTaP",
    "tdap": "Tdap",
    "mmr": "MMR",
    "bcg": "BCG",
    "flu": "Flu",
    "flu shot": "Flu Shot",
    "influenza": "Influenza",
    "covid": "COVID",
    "covid-19": "COVID-19",
    "rsv": "RSV",
    "hepatitis b": "Hepatitis B",
    "hepatitis a": "Hepatitis A",
    "hep b": "Hepatitis B",
    "hep a": "Hepatitis A",
    "polio": "Polio",
    "ipv": "IPV",
    "rotavirus": "Rotavirus",
    "shingles": "Shingles",
    "shingrix": "Shingrix",
    "pneumococcal": "Pneumococcal",
    "prevnar": "Prevnar",
    "meningococcal": "Meningococcal",
    "varicella": "Varicella",
    "chickenpox": "Chickenpox",
}


def normalize_vaccines(raw_value):
    """Normalize comma-separated vaccine names to canonical forms."""
    if not raw_value or pd.isna(raw_value):
        return ""
    names = [n.strip() for n in str(raw_value).split(",") if n.strip()]
    normalized = []
    seen = set()
    for name in names:
        canonical = VACCINE_CANONICAL.get(name.lower().strip(), name.strip())
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            normalized.append(canonical)
    return ", ".join(normalized)

PERSPECTIVE_VALUES = [
    "pro-vaccine",
    "nuanced-mostly-pro",
    "uncertain",
    "vaccine-hesitant",
    "anti-vaccine"
]

ANALYSIS_COLUMNS = [
    "perspective",
    "vaccine_injured",
    "vaccines_mentioned",
    "tags",
    "references",
    "duplicate"
]


def build_prompt(comment_text):
    return f"""You are analyzing a public comment submitted to a federal advisory committee
docket on regulations.gov related to ACIP (Advisory Committee on Immunization Practices)
and/or VRBPAC (Vaccines and Related Biological Products Advisory Committee).

Analyze the following comment and return a JSON object with exactly these fields:

{{
    "perspective": one of exactly: "pro-vaccine" | "nuanced-mostly-pro" | "uncertain" | "vaccine-hesitant" | "anti-vaccine",
    "vaccine_injured": "true" if the commenter describes a personal experience of injury 
        affecting themselves, OR injury or death affecting a family member or friend, 
        following vaccination — otherwise empty string,
    "vaccines_mentioned": comma-separated vaccine names mentioned (Moderna, Pfizer, 
        Novavax, J&J, AstraZeneca, mRNA, flu shot, etc.) or empty string if none,
    "tags": comma-separated tags from the list below that describe what the comment is about,
    "references": "references" if the comment contains citations, links, or references 
        to studies or research, otherwise empty string,
    "duplicate": "duplicate" if this comment appears to be a form letter or 
        near-identical to what many others might submit, otherwise empty string
}}

Perspective guidance:
- "pro-vaccine" — clearly and broadly supportive of vaccines
- "nuanced-mostly-pro" — generally supportive but raises some concerns
- "uncertain" — ambiguous or balanced
- "vaccine-hesitant" — raising safety concerns, calling for more transparency,
  or skeptical of vaccine policy. Note: many people who experienced vaccine 
  injuries do not consider themselves anti-vaccine — use "vaccine-hesitant" 
  for these cases unless they are clearly and broadly opposed to all vaccines.
- "anti-vaccine" — clearly and broadly opposed to vaccines

vaccine_injured guidance:
- Set to "true" if the commenter describes a personal experience of injury 
  affecting themselves, OR injury or death affecting a family member or friend,
  following vaccination.
- This field is independent of perspective — someone can be "pro-vaccine" AND
  "vaccine_injured", or "anti-vaccine" AND "vaccine_injured".
- Do NOT set to "true" when a commenter merely acknowledges that rare adverse 
  events exist as part of a broader policy argument, with no personal connection.

Important:
- Vaccine injury is a legitimate concern, not misinformation
- Do not editorialize about the commenter's motives or credibility
- Many people who experienced vaccine injuries do not consider themselves anti-vaccine

Tag guidance — use only tags that accurately describe the comment content.
Do not use tags that editorialize or dismiss the commenter's perspective.
Available tags:
side_effects, efficacy, mandates, natural_immunity, personal_experience,
religious_exemption, philosophical_exemption, scientific_citations,
vaccine_injury, transparency, safety_concern, myocarditis, informed_consent,
VAERS, long_covid, boosters, children, elderly, medical_exemption,
policy_criticism, manufacturer_liability, risk_benefit_analysis,
adverse_events, death, disability

Return only valid JSON, no preamble, no explanation, no markdown code blocks.

Comment:
{comment_text}"""


def analyze_comment(comment_text, max_retries=5):
    if not comment_text or pd.isna(comment_text):
        return {col: "" for col in ANALYSIS_COLUMNS}
    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model=MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": build_prompt(comment_text)}]
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw.strip())
            if result.get("perspective") not in PERSPECTIVE_VALUES:
                result["perspective"] = "uncertain"
            return result
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            wait = 30 * (attempt + 1)
            print(f"\n  {type(e).__name__}: waiting {wait}s (attempt {attempt+1}/{max_retries})")
            time.sleep(wait)
        except Exception as e:
            print(f"\n  Error analyzing comment: {e}")
            return {col: "" for col in ANALYSIS_COLUMNS}
    print(f"\n  Gave up after {max_retries} retries")
    return {col: "" for col in ANALYSIS_COLUMNS}


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"Input:      {CSV_PATH}")
    print(f"Model:      {MODEL}")
    print(f"Save every: {SAVE_EVERY} rows")
    print(f"{'='*60}")

    # Verify API key is set
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY is not set!")
        exit(1)
    print(f"API key:    ...{api_key[-4:]}")

    # Quick connectivity test
    print("Testing API connection...")
    try:
        test = client.messages.create(
            model=MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        print(f"API test:   OK ({test.content[0].text.strip()})")
    except Exception as e:
        print(f"API test FAILED: {type(e).__name__}: {e}")
        exit(1)

    print(f"{'='*60}\n")

    df = pd.read_csv(CSV_PATH)

    # Add analysis columns if not present
    for col in ANALYSIS_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Find rows that still need analysis (perspective is empty)
    needs_analysis = df["perspective"].isna() | (df["perspective"] == "")
    todo_indices = df[needs_analysis].index.tolist()

    print(f"Total rows:        {len(df)}")
    print(f"Already analyzed:  {len(df) - len(todo_indices)}")
    print(f"Remaining:         {len(todo_indices)}")

    if not todo_indices:
        print("All rows already analyzed!")
        exit()

    processed = 0

    try:
        for idx in tqdm(todo_indices, desc="Analyzing comments", unit="comment"):
            comment_text = df.at[idx, "comment"]
            result = analyze_comment(comment_text)

            df.at[idx, "perspective"] = result.get("perspective", "")
            df.at[idx, "vaccine_injured"] = result.get("vaccine_injured", "")
            df.at[idx, "vaccines_mentioned"] = normalize_vaccines(
                result.get("vaccines_mentioned", ""))
            df.at[idx, "tags"] = result.get("tags", "")
            df.at[idx, "references"] = result.get("references", "")
            df.at[idx, "duplicate"] = result.get("duplicate", "")

            processed += 1

            if processed % SAVE_EVERY == 0:
                df.to_csv(CSV_PATH, index=False)
                print(f"  💾 Saved progress: {processed} analyzed this run")

            time.sleep(SLEEP_SECS)

    except Exception as e:
        print(f"\nException occurred: {e}")
        print("Saving progress before exiting...")

    # Final save
    df.to_csv(CSV_PATH, index=False)
    print(f"\n✅ Done!")
    print(f"   Analyzed this run: {processed}")
    print(f"   Total analyzed:    {len(df[df['perspective'] != ''])}")
    print(f"   Vaccine injured:   {len(df[df['vaccine_injured'] == 'true'])}")
    print(f"   Saved to:          {CSV_PATH}")
