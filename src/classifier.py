import anthropic
import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

client = anthropic.Anthropic()

PROMPT_VERSION = "v1"


CLASSIFIER_PROMPT = """You are an expert meeting analyst. Your job is to read a
meeting transcript and extract every meaningful decision, action item, and open
question. You must also identify noise — anything that is discussion, context, or
filler that does not produce a commitment.

## Label definitions

DECISION — A course of action was explicitly agreed upon or a choice between
options was resolved. The group or an authority figure committed to something
being true going forward. Extractable as "We will do X" or "X is the plan".
Discussion that leads toward a decision but does not resolve it is NOISE.

ACTION — A task assigned (explicitly or implicitly) to an identifiable person,
with an implied or stated expectation of completion. The owner must be named or
clearly inferable from context. Do not hallucinate an owner who was not mentioned.

QUESTION — An open question that was raised but not resolved in the meeting.
Questions that were asked and answered are NOISE.

NOISE — Anything that is discussion, context, background, or filler that does not
produce a commitment or remain unresolved. When in doubt, label as NOISE.

## Rules

1. Extract every decision, action and question — do not miss items.
2. For each item write a clean plain-English summary, not a verbatim quote.
3. If an action has a named owner, include their name in the text.
4. If an action has an explicit due date or deadline, include it in the text.
5. Do not extract the same event as both a decision and an action — prefer action.
6. Return ONLY valid JSON. No preamble, no explanation, no markdown fences.

## Few-shot examples

These examples are drawn from real meeting transcripts. Study them carefully
before processing the transcript below.

### Example 1 — explicit decision with no owner

Transcript segment:
  Priya: OK, we're aligned. Q3 is onboarding flow and Slack integration.
  AI summary moves to Q4.

Correct output:
  {{"label": "decision", "text": "Q3 scope is onboarding and Slack integration
  only — AI summary feature moves to Q4"}}

Why: A clear group commitment was made. No individual owner. Not an action
because no person is tasked with executing it.

### Example 2 — action with explicit owner and date

Transcript segment:
  Priya: Ananya owns the dashboard performance fix, target ship date is next
  Wednesday June 11th.
  Ananya: Yeah I can have a fix in staging by end of this week.

Correct output:
  {{"label": "action", "text": "Ananya to fix dashboard performance — composite
  indexes on accounts and events tables, target ship date June 11th",
  "owner": "Ananya", "due_date": "2026-06-11"}}

Why: Specific person, specific task, specific date. Label as action not decision
even though a decision was also made — see rule 5.

### Example 3 — action with implicit owner

Transcript segment:
  Ravi: Fiona, keep the campaign running but I want weekly retention data on
  that LinkedIn cohort starting next Monday, not monthly.
  James: I'll build the retention view today and have it ready by Monday morning.

Correct output:
  {{"label": "action", "text": "James to build weekly retention view for LinkedIn
  cohort, ready by Monday", "owner": "James", "due_date": ""}}

Why: James volunteered and confirmed the task. Owner is explicit in the response
even though the request was directed at Fiona.

### Example 4 — open question not resolved

Transcript segment:
  Sophie: I haven't modelled it yet. I could put something together.
  Ravi: Yes, do that. Come back to me with a recommendation next week.

Correct output for the open question raised earlier in the same meeting:
  {{"label": "question", "text": "What would an annual plan look like and what
  is the revenue impact?", "owner": "", "due_date": ""}}

Why: The question was raised, Sophie is going to model it, but the answer is
still open. Note: Sophie's task to model it would also be extracted as a
separate ACTION item.

### Example 5 — noise that looks like a decision

Transcript segment:
  Marcus: The migration surfaced some performance issues. We're seeing 3-4
  second load times on the dashboard for accounts with more than 500 records.

Correct output: SKIP — do not extract this as a decision or action.

Why: This is a status update and background context. No commitment was made,
no task was assigned, nothing was resolved. Pure noise.

### Example 6 — implicit action (no explicit assignment)

Transcript segment:
  Nadia: Tom, can you hold the Hartwell account until Wednesday?
  Dan: I'll tell them we have a fix in testing.

Correct output:
  {{"label": "action", "text": "Dan to contact Hartwell and offer staging
  environment access to hold the account until Wednesday",
  "owner": "Dan", "due_date": ""}}

Why: Dan confirmed the task himself in his response. The owner is unambiguous
even though he wasn't formally assigned — he committed.

## Your task

Read the transcript below and extract all decisions, actions, and open questions.
Skip all noise. Return a JSON array of objects. Each object must have:
  - "label"    : one of "decision", "action", "question"
  - "text"     : plain-English summary of the item (do not quote verbatim)
  - "owner"    : name of the responsible person, or "" if none
  - "due_date" : ISO date string YYYY-MM-DD if stated or inferable, else ""

Return ONLY the JSON array. No other text.

## Transcript

{transcript}
"""


def classify_transcript(transcript_text, transcript_id="unknown"):
    """
    Classifies a meeting transcript and returns a list of extracted items.

    Calls the Anthropic API with a few-shot classifier prompt and parses
    the structured JSON response into a list of dicts compatible with
    eval_harness.score().

    Args:
        transcript_text  (str)  - full transcript as a plain text string
        transcript_id    (str)  - identifier added to each returned item
                                  (e.g. "transcript_1")

    Returns:
        list[dict]  - each dict has keys:
                        transcript_id, label, text, owner, due_date

    Raises:
        ValueError   - if the API returns malformed JSON
        ValueError   - if any returned label is not in the valid set
    """

    VALID_LABELS = {"decision", "action", "question"}

    # --- 1. Build the prompt ---
    prompt = CLASSIFIER_PROMPT.format(transcript=transcript_text)

    # --- 2. Call the API ---
    print(f"  Calling Claude API for {transcript_id}...")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    raw = response.content[0].text.strip()

    # --- 3. Strip markdown fences if the model added them anyway ---
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    # --- 4. Parse JSON ---
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"API returned invalid JSON for {transcript_id}.\n"
            f"Error: {e}\n"
            f"Raw response:\n{raw[:500]}"
        )

    if not isinstance(items, list):
        raise ValueError(
            f"Expected a JSON array, got {type(items).__name__}.\n"
            f"Raw response:\n{raw[:500]}"
        )

    # --- 5. Validate and normalise each item ---
    normalised = []
    for i, item in enumerate(items):

        # Label must be present and valid
        label = item.get("label", "").strip().lower()
        if label not in VALID_LABELS:
            print(f"  Warning: item {i} has invalid label '{label}' — skipping.")
            continue

        # Text must be present
        text = item.get("text", "").strip()
        if not text:
            print(f"  Warning: item {i} has empty text — skipping.")
            continue

        normalised.append({
            "transcript_id": transcript_id,
            "label":         label,
            "text":          text,
            "owner":         item.get("owner", "").strip(),
            "due_date":      item.get("due_date", "").strip(),
        })

    print(f"  Extracted {len(normalised)} items from {transcript_id}.")
    return normalised


def load_transcript(filename):
    """
    Loads a transcript from data/raw/ by filename.
    Call with e.g. load_transcript('transcript_1.txt')
    """
    path = os.path.join(
        os.path.dirname(__file__), "..", "data", "raw", filename
    )
    if not os.path.exists(path):
        raise FileNotFoundError(f"Transcript not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":

    sys.path.insert(0, os.path.dirname(__file__))
    from eval_harness import load_ground_truth, score, print_score_report

    print("=" * 55)
    print(f"MeetBrief Classifier — prompt {PROMPT_VERSION}")
    print("=" * 55)

    # --- Load ground truth ---
    ground_truth = load_ground_truth()

    # --- Run classifier on transcript_1 only for first test ---
    print("\nStep 1: Running classifier on transcript_1.txt...")
    transcript_text = load_transcript("transcript_1.txt")
    predictions_t1  = classify_transcript(transcript_text, "transcript_1")

    print("\nRaw predictions for transcript_1:")
    for p in predictions_t1:
        owner = f" [{p['owner']}]" if p["owner"] else ""
        print(f"  [{p['label']:10s}]{owner} {p['text'][:70]}")

    print("\nStep 2: Scoring transcript_1 against ground truth...")
    result_t1 = score(predictions_t1, ground_truth, transcript_id="transcript_1")
    print_score_report(result_t1, f"Classifier {PROMPT_VERSION} — transcript_1 only")

    # --- Prompt to run all 3 ---
    run_all = input("\nRun classifier on all 3 transcripts? (y/n): ").strip().lower()
    if run_all == "y":
        all_predictions = list(predictions_t1)

        for tid in ["transcript_2", "transcript_3"]:
            print(f"\nRunning classifier on {tid}.txt...")
            text  = load_transcript(f"{tid}.txt")
            preds = classify_transcript(text, tid)
            all_predictions.extend(preds)

        print("\nStep 3: Scoring all 3 transcripts combined...")
        result_all = score(all_predictions, ground_truth)
        print_score_report(result_all, f"Classifier {PROMPT_VERSION} — all transcripts")

        print("\nPer-transcript breakdown:")
        for tid in ["transcript_1", "transcript_2", "transcript_3"]:
            r = score(all_predictions, ground_truth, transcript_id=tid)
            print(f"  {tid}: F1={r['f1']:.1%}  "
                  f"P={r['precision']:.1%}  R={r['recall']:.1%}  "
                  f"(TP={r['tp']} FP={r['fp']} FN={r['fn']})")