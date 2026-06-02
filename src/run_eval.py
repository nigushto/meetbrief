import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from pipeline     import run_pipeline
from eval_harness import (
    load_ground_truth,
    score,
    score_fields,
    print_full_eval_report,
)

if __name__ == "__main__":

    print("MeetBrief — Full Pipeline Eval")
    print("Running all 3 transcripts through classifier + extractor...")
    print("(This makes ~100 API calls — expect 3–5 minutes)\n")

    # --- 1. Load ground truth ---
    ground_truth = load_ground_truth()

    # --- 2. Run full pipeline on all 3 transcripts ---
    all_enriched = []
    combined_stats = {
        "total_items":     0,
        "confident_count": 0,
        "flagged_count":   0,
        "avg_confidence":  0.0,
    }

    # Meeting dates added — allows extractor to resolve relative date references
    # All 3 synthetic transcripts are from the week of June 1, 2026
    transcript_files = [
        ("transcript_1.txt", "transcript_1", "2026-06-01"),
        ("transcript_2.txt", "transcript_2", "2026-06-01"),
        ("transcript_3.txt", "transcript_3", "2026-06-01"),
    ]

    conf_sum = 0.0
    run_count = 0

    for filename, tid, meeting_date in transcript_files:
        print(f"Running pipeline on {tid}...")
        result = run_pipeline(filename, tid, verbose=False, meeting_date=meeting_date)

        all_enriched.extend(result["all_items"])

        combined_stats["total_items"]     += result["stats"]["total_items"]
        combined_stats["confident_count"] += result["stats"]["confident_count"]
        combined_stats["flagged_count"]   += result["stats"]["flagged_count"]
        conf_sum  += result["stats"]["avg_confidence"]
        run_count += 1

        print(f"  {tid}: {result['stats']['total_items']} items, "
              f"avg conf={result['stats']['avg_confidence']:.2f}, "
              f"flagged={result['stats']['flagged_count']}")

    combined_stats["avg_confidence"] = round(conf_sum / run_count, 2)

    # --- 3. Score labels (classifier quality) ---
    print("\nScoring classifier labels against ground truth...")
    label_result = score(all_enriched, ground_truth)

    # --- 4. Score fields (extractor quality) ---
    print("Scoring extractor field accuracy...")
    field_result = score_fields(all_enriched, ground_truth)

    # --- 5. Print full scorecard ---
    print_full_eval_report(label_result, field_result, combined_stats)

    # --- 6. Per-transcript field accuracy breakdown ---
    print("Per-transcript field accuracy:")
    for filename, tid, meeting_date in transcript_files:
        gt_for   = [g for g in ground_truth    if g["transcript_id"] == tid]
        pred_for = [p for p in all_enriched if p["transcript_id"] == tid]
        fr = score_fields(pred_for, gt_for)
        lr = score(pred_for, ground_truth, transcript_id=tid)
        print(f"  {tid}:")
        print(f"    Label F1       : {lr['f1']:.1%}")
        print(f"    Owner accuracy : {fr['owner_accuracy']:.1%}"
              f"  ({fr['owner_correct']}/{fr['owner_scoreable']})")
        print(f"    Date accuracy  : {fr['date_accuracy']:.1%}"
              f"  ({fr['date_correct']}/{fr['date_scoreable']})")