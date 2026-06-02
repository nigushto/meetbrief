import os
import sys
import csv

sys.path.insert(0, os.path.dirname(__file__))

from classifier import classify_transcript, load_transcript
from extractor  import extract_items
from eval_harness import load_ground_truth

# Run ONLY transcript_2 — smallest transcript, 4 dated GT items, cheapest to check
# This is 8-10 API calls max

print("Running classifier + extractor on transcript_2 only...")
print("(~10 API calls — checking date extraction specifically)\n")

gt = load_ground_truth()
gt_t2_dated = {r["text"][:50]: r["due_date"] 
               for r in gt 
               if r["transcript_id"] == "transcript_2" and r["due_date"].strip()}

text    = load_transcript("transcript_2.txt")
classified = classify_transcript(text, "transcript_2")
enriched   = extract_items(classified, verbose=False, meeting_date="2026-06-01")

print(f"{'='*65}")
print(f"Extracted dates from transcript_2 (meeting date: 2026-06-01)")
print(f"{'='*65}")
print(f"{'due_date':12s}  {'text[:55]'}")
print(f"{'-'*65}")
for item in enriched:
    date = item["due_date"] if item["due_date"] else "(empty)"
    print(f"{date:12s}  {item['text'][:55]}")

print(f"\n{'='*65}")
print("Ground truth dated items for transcript_2:")
print(f"{'='*65}")
for text_key, date in gt_t2_dated.items():
    print(f"{date:12s}  {text_key}")

print(f"\n{'='*65}")
print("Date comparison:")
print(f"{'='*65}")
matched = 0
for item in enriched:
    for gt_text, gt_date in gt_t2_dated.items():
        words_item = set(item["text"].lower().split())
        words_gt   = set(gt_text.lower().split())
        overlap    = len(words_item & words_gt) / max(len(words_gt), 1)
        if overlap >= 0.4:
            match = "✓" if item["due_date"].strip() == gt_date.strip() else "✗"
            if item["due_date"].strip() == gt_date.strip():
                matched += 1
            print(f"  {match}  pred={item['due_date'] or '(empty)':12s}  "
                  f"gt={gt_date:12s}  {gt_text[:40]}")
            break

print(f"\nDate matches: {matched}/{len(gt_t2_dated)}")