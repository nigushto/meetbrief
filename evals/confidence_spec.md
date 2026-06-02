# MeetBrief Confidence Spec v1.0

## What this document is

This spec defines what the confidence score means in MeetBrief's extractor
output, what threshold triggers human review, and how confidence calibration
is measured. Any change to the threshold or rubric requires a version bump.

Related: evals/eval_spec.md (defines label correctness)

---

## What confidence measures

Confidence is a 0.0–1.0 score assigned by the extractor reflecting how
certain it is that:

1. The item was correctly classified (right label)
2. The extracted text accurately summarises the commitment
3. The owner field is correct and traceable to someone named in the transcript
4. The due_date field is correct — stated or reliably inferable

Confidence is NOT a measure of importance. A low-confidence item may be
highly important — it just needs human verification before publishing.

---

## Scoring rubric

### 0.9 — 1.0 : High confidence — auto-publish

All fields are unambiguous and directly traceable to the transcript.
Owner explicitly named. Date explicitly stated or reliably inferred
from a specific reference ("June 11th", "next Wednesday").

Example:
  "Ananya to fix dashboard performance by June 11th"
  Owner=Ananya (named), Date=2026-06-11 (explicit) → conf=0.95

### 0.7 — 0.9 : Moderate confidence — auto-publish with monitoring

Item is clear but one field is inferred rather than explicit.
Acceptable for auto-publishing but worth spot-checking periodically.

Common reasons for this range:
  - Owner implied by context rather than explicitly assigned
  - Date inferred from relative reference ("this week", "EOD Thursday")
  - Decision made through convergence rather than explicit declaration

Example:
  "Q3 scope narrowed to onboarding and Slack — AI summary to Q4"
  Owner=(none), Date=(none), decision clear but no named decision-maker
  → conf=0.72

### 0.5 — 0.7 : Low confidence — FLAG for human review

Item is ambiguous in at least one significant way. Do not auto-publish.
Show to the user in the Streamlit UI with the confidence_reason displayed.

Common reasons for this range:
  - Owner inferred but not confirmed ("Priya named as participant, not
    explicitly as decision-maker")
  - Relative date cannot be resolved without knowing meeting date
    ("this week" when meeting date is unknown)
  - Classification may be wrong — item could be decision OR action
  - Item is a paraphrase of a longer discussion, not a clear commitment

Example:
  "Company to extend offer to backend engineer candidate"
  Owner=Priya (inferred), Date=(none, "this week" unresolvable)
  → conf=0.62  ⚑ FLAGGED

### 0.0 — 0.5 : Very low confidence — FLAG and warn

Significant uncertainty about the item itself. The classification may
be wrong, the text may be a hallucination, or key fields are missing
with no basis for inference. Always requires human review.

---

## Guardrail threshold

**Current threshold: 0.7**

Items with confidence >= 0.7 are auto-published to Slack and Notion.
Items with confidence <  0.7 are held for human review in the UI.

### Rationale for 0.7

In testing on 3 synthetic transcripts (44 ground truth items):
  - Items scoring >= 0.7 had near-zero field errors (owner/date wrong)
  - Items scoring <  0.7 had at least one field that needed correction
  - The 0.7 threshold correctly flagged ambiguous items without
    over-flagging clearly correct ones

### How to change the threshold

If you find auto-published items frequently contain errors:
  → Raise threshold to 0.75 or 0.8

If you find too many items are being held for review unnecessarily:
  → Lower threshold to 0.65

Change the CONFIDENCE_THRESHOLD constant in src/pipeline.py.
Document the reason and re-run the full eval before shipping.

---

## Calibration — is the model honest about its uncertainty?

A well-calibrated confidence score means: items scored 0.9 should be
correct ~90% of the time. Items scored 0.6 should be correct ~60% of
the time.

### How to measure calibration (Week 4 task)

1. Collect 50+ items with known ground truth labels and fields
2. Group items into confidence buckets: [0.5-0.6], [0.6-0.7], [0.7-0.8],
   [0.8-0.9], [0.9-1.0]
3. For each bucket, measure actual accuracy (owner correct + date correct)
4. Plot predicted confidence vs actual accuracy
5. A well-calibrated model produces a near-diagonal line

Current status: calibration not yet formally measured. Based on manual
inspection of transcript_1 output (10 items), the model appears
appropriately cautious — the one flagged item (conf=0.62) was genuinely
ambiguous on owner attribution.

---

## What confidence does NOT cover

- Latency quality (whether the pipeline ran fast enough)
- Slack/Notion formatting quality
- Whether the item is important enough to include

These are evaluated separately. See docs/progress.md for overall
pipeline quality notes per week.

---

## Version history

v1.0 — Week 3. Initial threshold 0.7. Rubric based on transcript_1
       extractor output inspection. Calibration not yet formally measured.

### Week 3 calibration observation

All 8 flagged items (conf=0.62) share the same pattern: decisions with
no named owner and no due date. The classification is correct in every
case — confidence is reduced structurally because two fields are empty,
not because the item is ambiguous.

Implication: the 0.7 threshold correctly separates "fields are complete
and verified" from "fields are empty". This is the right behaviour for
v1. A future refinement could introduce label-specific thresholds —
decisions without owners are expected to have lower confidence, so a
lower threshold (e.g. 0.65) for ownerless decisions may reduce
unnecessary human review without introducing errors.

v1.1 — Week 4. Meeting date context added to extractor prompt.
Explicit dates and clear relative references resolve correctly.
Vague references ("this week", "next Friday") remain inconsistent.
Full calendar context (day of week) planned for Week 8.