import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from classifier import classify_transcript, load_transcript
from eval_harness import load_ground_truth, score


def text_match(pred_text, gt_text, threshold=0.4):
    pred_words = set(pred_text.lower().split())
    gt_words   = set(gt_text.lower().split())
    if not gt_words:
        return False
    overlap = len(pred_words & gt_words) / len(gt_words)
    return overlap >= threshold


def diagnose(transcript_id, predictions, ground_truth):
    gt_for   = [g for g in ground_truth if g["transcript_id"] == transcript_id]
    pred_for = [p for p in predictions  if p["transcript_id"] == transcript_id]

    print(f"\n{'=' * 55}")
    print(f"  {transcript_id}")
    print(f"{'=' * 55}")

    # --- Missed items (in GT, not found by classifier) ---
    print("\nMISSED  (ground truth items the classifier did not find):")
    missed_any = False
    for g in gt_for:
        matched = any(
            p["label"] == g["label"] and text_match(p["text"], g["text"])
            for p in pred_for
        )
        if not matched:
            owner = f"  owner={g['owner']}" if g["owner"] else ""
            print(f"  [{g['label']:10s}] {g['text'][:75]}{owner}")
            missed_any = True
    if not missed_any:
        print("  (none — perfect recall)")

    # --- Extra items (predicted but not in GT) ---
    print("\nEXTRA   (predictions that do not match any ground truth item):")
    extra_any = False
    for p in pred_for:
        matched = any(
            p["label"] == g["label"] and text_match(p["text"], g["text"])
            for g in gt_for
        )
        if not matched:
            owner = f"  owner={p['owner']}" if p["owner"] else ""
            print(f"  [{p['label']:10s}] {p['text'][:75]}{owner}")
            extra_any = True
    if not extra_any:
        print("  (none — perfect precision)")


if __name__ == "__main__":
    print("Loading ground truth...")
    ground_truth = load_ground_truth()

    all_predictions = []

    for tid in ["transcript_1", "transcript_2", "transcript_3"]:
        print(f"\nClassifying {tid}...")
        text  = load_transcript(f"{tid}.txt")
        preds = classify_transcript(text, tid)
        all_predictions.extend(preds)

    print("\n\nDIAGNOSTIC REPORT")
    print("Missed = items in your ground truth the classifier did not find")
    print("Extra  = items the classifier predicted that are not in ground truth")

    for tid in ["transcript_1", "transcript_2", "transcript_3"]:
        diagnose(tid, all_predictions, ground_truth)

    print(f"\n{'=' * 55}")
    print("SUMMARY")
    result = score(all_predictions, ground_truth)
    total_missed = result["fn"]
    total_extra  = result["fp"]
    print(f"  Total missed : {total_missed}  (false negatives — fix by improving recall)")
    print(f"  Total extra  : {total_extra}   (false positives — fix by improving precision)")
    print(f"  Overall F1   : {result['f1']:.1%}")
    print(f"{'=' * 55}\n")