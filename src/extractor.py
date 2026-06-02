import anthropic
import os
import sys

from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic()

EXTRACTOR_VERSION = "v1"

# --- JSON schema enforced via tool_use ---
# This guarantees the API always returns valid structured output.
# No JSON parsing errors. No missing fields. No markdown fences.
EXTRACTION_TOOL = {
    "name": "extract_structured_item",
    "description": "Extract structured fields from a classified meeting item",
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Clean plain-English summary of the item. Improve on the classifier text if it can be clearer — do not quote verbatim from the transcript."
            },
            "owner": {
                "type": "string",
                "description": "First name of the person responsible. Must be directly traceable to someone named in the transcript. Empty string if genuinely unknown — never guess."
            },
            "due_date": {
                "type": "string",
                "description": "ISO date string YYYY-MM-DD if a deadline was stated or can be reliably inferred. Empty string if absent or ambiguous."
            },
            "confidence": {
                "type": "number",
                "description": "Score from 0.0 to 1.0 reflecting how certain you are this item was correctly classified and all fields are accurate. 0.9+ = very clear. 0.7-0.9 = reasonably clear. 0.5-0.7 = somewhat ambiguous. Below 0.5 = significant uncertainty."
            },
            "confidence_reason": {
                "type": "string",
                "description": "One sentence explaining why you assigned this confidence score. Be specific — name the source of uncertainty if confidence is below 0.8."
            }
        },
        "required": ["text", "owner", "due_date", "confidence", "confidence_reason"]
    }
}

EXTRACTOR_PROMPT_BASE = """You are reviewing a single item extracted from a meeting transcript.

Your job is to:
1. Verify the classification makes sense given the item text
2. Identify the owner — the specific person responsible (for actions) or who made the call (for decisions)
3. Extract the due date if one was stated or clearly implied
4. Assign a confidence score reflecting how certain you are about this item and its fields
5. Write one sentence explaining your confidence score

## Confidence scoring guide

0.9 — 1.0 : Item is unambiguous. Owner explicitly named. Date explicitly stated.
             Example: "Ananya to fix dashboard performance by June 11th"

0.7 — 0.9 : Item is clear but one field is inferred rather than explicit.
             Example: Owner implied by context, or date inferred from "this week"

0.5 — 0.7 : Item is somewhat ambiguous. Multiple interpretations possible.
             Example: Group discussion that may or may not have resolved to a decision

0.0 — 0.5 : Significant uncertainty. Classification may be wrong, or key fields
             cannot be determined. Recommend human review.

## Important: resolving relative dates
When converting relative date references ("this week", "next Friday", "end of
month", "today", "tomorrow") to ISO dates, use the meeting date provided below
as your anchor. If no meeting date is provided, leave due_date blank.
Examples given meeting date 2026-06-01 (Monday):
  "today"        → 2026-06-01
  "tomorrow"     → 2026-06-02
  "this week"    → 2026-06-05  (end of week = Friday)
  "next Monday"  → 2026-06-08
  "next Friday"  → 2026-06-06  (the coming Friday, not two weeks out)
  "end of month" → 2026-06-30
  "in two weeks" → 2026-06-15
"""


def extract_item(classified_item, meeting_date=None):
    """
    Enriches a single classified item with structured fields and confidence score.

    Takes one dict from the classifier output and returns an enriched dict
    with verified owner, due_date, confidence score, and confidence_reason.

    Uses the Anthropic tools parameter to enforce JSON schema — this guarantees
    valid structured output on every call with no parsing errors.

    Args:
        classified_item (dict) - one item from classify_transcript() output
                                 must have: label, text, owner, due_date, transcript_id

    Returns:
        dict with all original fields plus:
            confidence       (float) - 0.0 to 1.0
            confidence_reason (str)  - one sentence explaining the score
    """

    # Build prompt via concatenation — avoids .format() conflicts with special chars
    date_line = f"Meeting date: {meeting_date}" if meeting_date else "Meeting date: not provided"
    label     = classified_item["label"]
    text      = classified_item["text"]
    owner     = classified_item["owner"] or "not identified"
    due_date  = classified_item["due_date"] or "not stated"

    prompt = (
        EXTRACTOR_PROMPT_BASE
        + "\n## Meeting context\n"
        + date_line + "\n"
        + "\n## Item to review\n"
        + "\nThe item has been classified as a " + label + ".\n"
        + "\nText  : " + text + "\n"
        + "Owner (from classifier, may be incomplete): " + owner + "\n"
        + "Date  (from classifier, may be incomplete): " + due_date + "\n"
        + "\nCall extract_structured_item with your assessment."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        temperature=0,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    # --- Extract tool_use block from response ---
    tool_result = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_structured_item":
            tool_result = block.input
            break

    if tool_result is None:
        # Fallback: model didn't call the tool — return item with low confidence
        print(f"  Warning: extractor did not call tool for item: {classified_item['text'][:50]}")
        return {
            **classified_item,
            "confidence":        0.0,
            "confidence_reason": "Extractor did not return structured output — needs manual review."
        }

    # --- Validate confidence is in range ---
    confidence = float(tool_result.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    # --- Return enriched item ---
    return {
        "transcript_id":    classified_item["transcript_id"],
        "label":            classified_item["label"],
        "text":             tool_result.get("text", classified_item["text"]).strip(),
        "owner":            tool_result.get("owner", "").strip(),
        "due_date":         tool_result.get("due_date", "").strip(),
        "confidence":       round(confidence, 2),
        "confidence_reason": tool_result.get("confidence_reason", "").strip()
    }


def extract_items(classified_items, verbose=True, meeting_date=None):
    """
    Enriches a list of classified items by running each through the extractor.

    Args:
        classified_items (list[dict]) - full output from classify_transcript()
        verbose          (bool)       - if True, prints progress per item

    Returns:
        list[dict] - enriched items with confidence scores added
    """

    enriched = []
    total = len(classified_items)

    for i, item in enumerate(classified_items):
        if verbose:
            print(f"  Extracting item {i+1}/{total}: [{item['label']:10s}] {item['text'][:55]}...")

        result = extract_item(item, meeting_date=meeting_date)
        enriched.append(result)

    return enriched


def print_extraction_report(enriched_items):
    """
    Prints a readable summary of extractor output.
    Shows label, confidence, owner, due_date, and confidence_reason per item.
    """
    print(f"\n{'=' * 60}")
    print(f"Extractor report — {len(enriched_items)} items")
    print(f"{'=' * 60}")

    for item in enriched_items:
        conf = item["confidence"]

        # Visual confidence indicator
        if conf >= 0.9:
            indicator = "●●●"
        elif conf >= 0.7:
            indicator = "●●○"
        elif conf >= 0.5:
            indicator = "●○○"
        else:
            indicator = "○○○"

        flag = "  ⚑ FLAGGED" if conf < 0.7 else ""

        print(f"\n  [{item['label']:10s}] {indicator} {conf:.2f}{flag}")
        print(f"  Text  : {item['text'][:70]}")
        print(f"  Owner : {item['owner'] or '(none)'}")
        print(f"  Date  : {item['due_date'] or '(none)'}")
        print(f"  Why   : {item['confidence_reason']}")

    flagged = sum(1 for i in enriched_items if i["confidence"] < 0.7)
    avg_conf = sum(i["confidence"] for i in enriched_items) / len(enriched_items) if enriched_items else 0

    print(f"\n{'=' * 60}")
    print(f"  Total items   : {len(enriched_items)}")
    print(f"  Flagged (<0.7): {flagged}")
    print(f"  Avg confidence: {avg_conf:.2f}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":

    sys.path.insert(0, os.path.dirname(__file__))
    from classifier import classify_transcript, load_transcript

    print("=" * 60)
    print(f"MeetBrief Extractor — {EXTRACTOR_VERSION}")
    print("Step 1: Classify transcript_1")
    print("=" * 60)

    transcript_text = load_transcript("transcript_1.txt")
    classified = classify_transcript(transcript_text, "transcript_1")

    print(f"\nClassifier returned {len(classified)} items.")
    print("\nStep 2: Extracting structured fields + confidence scores...")
    print("(One API call per item — this takes ~30 seconds)\n")

    enriched = extract_items(classified, verbose=True)
    print_extraction_report(enriched)

    print("Extractor v1 working. Ready to wire into pipeline.py")