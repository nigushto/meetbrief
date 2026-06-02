import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from classifier import classify_transcript, load_transcript
from extractor  import extract_items, print_extraction_report

PIPELINE_VERSION  = "v1"
CONFIDENCE_THRESHOLD = 0.7


def run_pipeline(transcript_filename, transcript_id=None, verbose=True):
    """
    Runs the full MeetBrief pipeline on a single transcript file.

    Step 1 — Classifier  : reads transcript, labels each item as
                           decision / action / question
    Step 2 — Extractor   : enriches each item with verified owner,
                           due_date, confidence score, confidence_reason
    Step 3 — Guardrail   : splits output into confident vs flagged items

    Args:
        transcript_filename (str)  - filename inside data/raw/
                                     e.g. "transcript_1.txt"
        transcript_id       (str)  - identifier for scoring and display.
                                     Defaults to filename without extension.
        verbose             (bool) - print progress to terminal

    Returns:
        dict with keys:
            transcript_id  (str)
            confident      (list[dict]) - items with confidence >= threshold
            flagged        (list[dict]) - items with confidence <  threshold
            all_items      (list[dict]) - full enriched list before splitting
            stats          (dict)       - summary counts and averages
    """

    if transcript_id is None:
        transcript_id = transcript_filename.replace(".txt", "")

    if verbose:
        print(f"\n{'=' * 60}")
        print(f"  MeetBrief Pipeline {PIPELINE_VERSION} — {transcript_id}")
        print(f"{'=' * 60}")

    # --- Step 1: Classify ---
    if verbose:
        print(f"\n[1/3] Classifying transcript...")

    transcript_text = load_transcript(transcript_filename)
    classified      = classify_transcript(transcript_text, transcript_id)

    if verbose:
        print(f"      Classifier found {len(classified)} items.")

    # --- Step 2: Extract structured fields ---
    if verbose:
        print(f"\n[2/3] Extracting structured fields + confidence scores...")
        print(f"      ({len(classified)} API calls — ~{len(classified) * 3}s)\n")

    enriched = extract_items(classified, verbose=verbose)

    # --- Step 3: Apply guardrail ---
    if verbose:
        print(f"\n[3/3] Applying confidence guardrail (threshold={CONFIDENCE_THRESHOLD})...")

    confident, flagged = split_by_confidence(enriched, CONFIDENCE_THRESHOLD)

    if verbose:
        print(f"      Confident : {len(confident)} items (auto-publish)")
        print(f"      Flagged   : {len(flagged)} items (needs review)")

    # --- Build stats ---
    avg_confidence = (
        sum(i["confidence"] for i in enriched) / len(enriched)
        if enriched else 0.0
    )

    label_counts = {}
    for item in enriched:
        label_counts[item["label"]] = label_counts.get(item["label"], 0) + 1

    stats = {
        "total_items":     len(enriched),
        "confident_count": len(confident),
        "flagged_count":   len(flagged),
        "avg_confidence":  round(avg_confidence, 2),
        "label_counts":    label_counts,
    }

    return {
        "transcript_id": transcript_id,
        "confident":     confident,
        "flagged":       flagged,
        "all_items":     enriched,
        "stats":         stats,
    }


def split_by_confidence(enriched_items, threshold=CONFIDENCE_THRESHOLD):
    """
    Splits enriched pipeline output into confident and flagged items.

    Confident items (confidence >= threshold) are safe to auto-publish
    to Slack and Notion without human review.

    Flagged items (confidence < threshold) need human review before
    publishing. They will appear in the Streamlit UI with a warning.

    Args:
        enriched_items (list[dict]) - output from extract_items()
        threshold      (float)      - confidence cutoff, default 0.7

    Returns:
        tuple(confident, flagged) — both are lists of dicts
    """

    confident = [i for i in enriched_items if i["confidence"] >= threshold]
    flagged   = [i for i in enriched_items if i["confidence"] <  threshold]

    return confident, flagged


def print_pipeline_report(result):
    """
    Prints a clean summary of the full pipeline result.
    Separates confident items from flagged items clearly.
    """
    stats = result["stats"]

    print(f"\n{'=' * 60}")
    print(f"  Pipeline report — {result['transcript_id']}")
    print(f"{'=' * 60}")
    print(f"  Total items    : {stats['total_items']}")
    print(f"  Avg confidence : {stats['avg_confidence']:.2f}")
    print(f"  Label split    : {stats['label_counts']}")
    print(f"{'=' * 60}")

    if result["confident"]:
        print(f"\n  CONFIDENT ({len(result['confident'])} items — ready to publish)")
        print(f"  {'-' * 54}")
        for item in result["confident"]:
            owner = f"  [{item['owner']}]" if item["owner"] else ""
            date  = f"  due {item['due_date']}" if item["due_date"] else ""
            print(f"  [{item['label']:10s}] {item['confidence']:.2f}{owner}{date}")
            print(f"    {item['text'][:70]}")

    if result["flagged"]:
        print(f"\n  FLAGGED ({len(result['flagged'])} items — needs human review)")
        print(f"  {'-' * 54}")
        for item in result["flagged"]:
            owner = f"  [{item['owner']}]" if item["owner"] else ""
            print(f"  [{item['label']:10s}] {item['confidence']:.2f}{owner}  ⚑")
            print(f"    {item['text'][:70]}")
            print(f"    Why flagged: {item['confidence_reason']}")

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":

    import sys

    transcripts = [
        ("transcript_1.txt", "transcript_1"),
        ("transcript_2.txt", "transcript_2"),
        ("transcript_3.txt", "transcript_3"),
    ]

    # Run transcript_1 first for a quick sanity check
    print("Running pipeline on transcript_1 first...")
    result = run_pipeline("transcript_1.txt", "transcript_1", verbose=True)
    print_pipeline_report(result)

    run_all = input("Run pipeline on all 3 transcripts? (y/n): ").strip().lower()
    if run_all != "y":
        sys.exit(0)

    all_results = [result]

    for filename, tid in transcripts[1:]:
        r = run_pipeline(filename, tid, verbose=True)
        print_pipeline_report(r)
        all_results.append(r)

    # --- Combined summary across all transcripts ---
    print(f"\n{'=' * 60}")
    print("  COMBINED SUMMARY — all 3 transcripts")
    print(f"{'=' * 60}")

    total_items     = sum(r["stats"]["total_items"]     for r in all_results)
    total_confident = sum(r["stats"]["confident_count"] for r in all_results)
    total_flagged   = sum(r["stats"]["flagged_count"]   for r in all_results)
    avg_conf        = sum(r["stats"]["avg_confidence"]  for r in all_results) / len(all_results)

    print(f"  Total items     : {total_items}")
    print(f"  Confident       : {total_confident}  ({round(total_confident/total_items*100)}% auto-publish)")
    print(f"  Flagged         : {total_flagged}   ({round(total_flagged/total_items*100)}% needs review)")
    print(f"  Avg confidence  : {avg_conf:.2f}")
    print(f"{'=' * 60}\n")