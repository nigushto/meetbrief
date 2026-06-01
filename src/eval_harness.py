import pandas as pd
import os

VALID_LABELS = {"decision", "action", "question", "noise"}

GROUND_TRUTH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "labels", "ground_truth.csv"
)


def load_ground_truth(path=GROUND_TRUTH_PATH):
    """
    Loads the ground truth CSV and returns a list of labelled items.

    Each item is a dict with keys:
        transcript_id  (str)  - which transcript this came from
        label          (str)  - one of: decision, action, question, noise
        text           (str)  - the extracted content in plain language
        owner          (str)  - person responsible, or empty string if unknown
        due_date       (str)  - ISO date string (YYYY-MM-DD), or empty string
        notes          (str)  - annotation reasoning

    Returns:
        list[dict]  - one dict per labelled item

    Raises:
        FileNotFoundError   - if the CSV path does not exist
        ValueError          - if required columns are missing
        ValueError          - if any label value is outside the valid set
    """

    # --- 1. Check the file exists ---
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Ground truth file not found at: {path}\n"
            f"Expected location: data/labels/ground_truth.csv\n"
            f"Have you downloaded the file from the project setup step?"
        )

    # --- 2. Load into a DataFrame ---
    df = pd.read_csv(path)

    # --- 3. Validate required columns exist ---
    required_columns = {"transcript_id", "label", "text"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(
            f"Ground truth CSV is missing required columns: {missing}\n"
            f"Columns found: {list(df.columns)}\n"
            f"Check your CSV matches the spec in evals/eval_spec.md"
        )

    # --- 4. Validate label values ---
    invalid_labels = set(df["label"].dropna().unique()) - VALID_LABELS
    if invalid_labels:
        raise ValueError(
            f"Invalid label values found: {invalid_labels}\n"
            f"Valid labels are: {VALID_LABELS}\n"
            f"Check your ground_truth.csv for typos."
        )

    # --- 5. Fill optional columns with empty strings if missing or NaN ---
    for col in ["owner", "due_date", "notes"]:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("")

    # --- 6. Strip whitespace from all string columns ---
    string_cols = ["transcript_id", "label", "text", "owner", "due_date", "notes"]
    for col in string_cols:
        df[col] = df[col].str.strip()

    # --- 7. Drop rows where text is empty (malformed rows) ---
    before = len(df)
    df = df[df["text"] != ""]
    dropped = before - len(df)
    if dropped > 0:
        print(f"Warning: dropped {dropped} rows with empty text fields.")

    # --- 8. Convert to list of dicts ---
    items = df[string_cols].to_dict(orient="records")

    return items


def summarise_ground_truth(items):
    """
    Prints a summary of loaded ground truth items.
    Useful for sanity-checking after load.
    """
    print(f"\n--- Ground Truth Summary ---")
    print(f"Total items loaded: {len(items)}")

    label_counts = {}
    for item in items:
        label = item["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    for label, count in sorted(label_counts.items()):
        print(f"  {label:12s}: {count}")

    transcript_counts = {}
    for item in items:
        tid = item["transcript_id"]
        transcript_counts[tid] = transcript_counts.get(tid, 0) + 1

    print(f"\nItems per transcript:")
    for tid, count in sorted(transcript_counts.items()):
        print(f"  {tid:20s}: {count}")

    items_with_owner = sum(1 for i in items if i["owner"])
    items_with_date  = sum(1 for i in items if i["due_date"])
    print(f"\nItems with owner   : {items_with_owner} / {len(items)}")
    print(f"Items with due date: {items_with_date} / {len(items)}")
    print(f"----------------------------\n")


def score(predictions, ground_truth, transcript_id=None, _top_level=True):
    """
    Scores a list of predicted items against ground truth.

    A prediction is a TRUE POSITIVE if:
      - its label matches a ground truth item's label, AND
      - its text is a reasonable match (checked via keyword overlap)

    Args:
        predictions  (list[dict])  - each dict must have 'label' and 'text'
        ground_truth (list[dict])  - loaded via load_ground_truth()
        transcript_id (str|None)   - if set, scores only items for that transcript

    Returns:
        dict with keys:
            precision       (float) - tp / (tp + fp)
            recall          (float) - tp / (tp + fn)
            f1              (float) - harmonic mean of precision and recall
            tp              (int)   - true positives
            fp              (int)   - false positives (predicted but wrong/not in GT)
            fn              (int)   - false negatives (in GT but not predicted)
            per_label       (dict)  - precision/recall broken down by label
    """

    # Filter to a specific transcript if requested
    if transcript_id:
        ground_truth = [i for i in ground_truth if i["transcript_id"] == transcript_id]
        predictions  = [p for p in predictions  if p.get("transcript_id") == transcript_id]

    def text_match(pred_text, gt_text, threshold=0.4):
        """
        Returns True if enough words overlap between prediction and ground truth.
        Not exact matching — we allow paraphrasing, which is realistic.
        Threshold = fraction of GT words that must appear in the prediction.
        """
        pred_words = set(pred_text.lower().split())
        gt_words   = set(gt_text.lower().split())
        if not gt_words:
            return False
        overlap = len(pred_words & gt_words) / len(gt_words)
        return overlap >= threshold

    # Track which GT items have been matched (avoid double-counting)
    gt_matched = [False] * len(ground_truth)
    tp = 0
    fp = 0

    for pred in predictions:
        matched = False
        for i, gt in enumerate(ground_truth):
            if gt_matched[i]:
                continue
            if pred["label"] == gt["label"] and text_match(pred["text"], gt["text"]):
                tp += 1
                gt_matched[i] = True
                matched = True
                break
        if not matched:
            fp += 1

    fn = sum(1 for matched in gt_matched if not matched)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)

    # Per-label breakdown — only computed at the top level to avoid infinite recursion
    per_label = {}
    if _top_level:
        for label in VALID_LABELS:
            gt_for_label   = [i for i in ground_truth if i["label"] == label]
            pred_for_label = [p for p in predictions  if p["label"] == label]
            if gt_for_label or pred_for_label:
                label_result = score(pred_for_label, gt_for_label, _top_level=False)
                per_label[label] = {
                    "precision": label_result["precision"],
                    "recall":    label_result["recall"],
                    "f1":        label_result["f1"],
                    "gt_count":  len(gt_for_label),
                    "pred_count": len(pred_for_label),
                }

    return {
        "precision": round(precision, 3),
        "recall":    round(recall, 3),
        "f1":        round(f1, 3),
        "tp":        tp,
        "fp":        fp,
        "fn":        fn,
        "per_label": per_label,
    }


def print_score_report(result, label=""):
    """
    Prints a readable score report from the output of score().
    """
    header = f"--- Score Report{': ' + label if label else ''} ---"
    print(f"\n{header}")
    print(f"  Precision : {result['precision']:.1%}  "
          f"({result['tp']} correct out of {result['tp'] + result['fp']} predicted)")
    print(f"  Recall    : {result['recall']:.1%}  "
          f"({result['tp']} found out of {result['tp'] + result['fn']} in ground truth)")
    print(f"  F1        : {result['f1']:.1%}")
    print(f"\n  Per-label breakdown:")
    for label_name, stats in sorted(result["per_label"].items()):
        print(f"    {label_name:12s}  "
              f"P={stats['precision']:.1%}  R={stats['recall']:.1%}  "
              f"(GT={stats['gt_count']}  Pred={stats['pred_count']})")
    print(f"{'-' * len(header)}\n")


def dummy_predictor(ground_truth, forced_label="action"):
    """
    A baseline predictor that labels every ground truth item as forced_label.

    Use this to sanity-check the scorer before plugging in a real LLM.
    A good scorer should return:
      - High recall for 'action' (finds all GTs but with wrong labels)
      - Low precision overall (most predictions are wrong label)

    Args:
        ground_truth  (list[dict])  - loaded via load_ground_truth()
        forced_label  (str)         - label to apply to every item (default: 'action')

    Returns:
        list[dict]  - predictions in the same format as ground_truth items
    """
    if forced_label not in VALID_LABELS:
        raise ValueError(f"forced_label must be one of {VALID_LABELS}")

    predictions = []
    for item in ground_truth:
        predictions.append({
            "transcript_id": item["transcript_id"],
            "label":         forced_label,
            "text":          item["text"],   # use GT text so text_match always passes
            "owner":         "",
            "due_date":      "",
        })
    return predictions


# --- Run this file directly to verify everything loads correctly ---
if __name__ == "__main__":
    print("Loading ground truth...")
    ground_truth = load_ground_truth()
    summarise_ground_truth(ground_truth)

    # --- E2: score() sanity check with a perfect predictor ---
    print("=== TEST 1: Perfect predictor (score should be 100%) ===")
    perfect_preds = [
        {"transcript_id": i["transcript_id"], "label": i["label"], "text": i["text"]}
        for i in ground_truth
    ]
    perfect_result = score(perfect_preds, ground_truth)
    print_score_report(perfect_result, "Perfect predictor")

    # --- E3: dummy predictor (labels everything as 'action') ---
    print("=== TEST 2: Dummy predictor (labels everything as 'action') ===")
    dummy_preds  = dummy_predictor(ground_truth, forced_label="action")
    dummy_result = score(dummy_preds, ground_truth)
    print_score_report(dummy_result, "Dummy predictor — all 'action'")

    print("What this tells you:")
    print(f"  - Precision {dummy_result['precision']:.1%}: most 'action' predictions are wrong label")
    print(f"  - Recall for action {dummy_result['per_label'].get('action', {}).get('recall', 0):.1%}: "
          f"finds all real actions")
    print(f"  - Recall for decision/question: 0% — never predicted, never found")
    print("\nYour scorer is working correctly if TEST 1 = 100% and TEST 2 shows this pattern.")
    print("\neval_harness.py fully operational. Ready for Week 2 — real classifier prompt.")