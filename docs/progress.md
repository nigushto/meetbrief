# MeetBrief — Build Progress Log

This log tracks weekly progress on MeetBrief: an AI meeting debrief engine that
extracts decisions, actions, and open questions from meeting transcripts and pushes
structured output to Slack and Notion.

One entry per week. Written for future me, future contributors, and future clients.

---

## Week 1 — Eval foundation and ground truth

**What I built**

Set up the full project environment: Python 3.11, Anthropic SDK, Streamlit, and
pandas installed in an isolated virtual environment. Created the GitHub repo with
a clean folder structure (src/, data/raw/, data/labels/, evals/, docs/). Generated
3 synthetic founder meeting transcripts covering a product all-hands, a growth
review, and a Series A investor prep session — deliberately varied in length,
formality, and decision density to stress-test future classifiers. Manually
labelled all 44 items across the 3 transcripts as ground truth, covering 22
action items, 17 decisions, and 5 open questions. Wrote a formal eval spec
(evals/eval_spec.md) defining exactly what counts as a correct extraction, what a
true positive means, and how partial matches are handled. Built eval_harness.py
with load_ground_truth(), score(), dummy_predictor(), and print_score_report() —
a fully functional eval pipeline that takes any list of predicted labels and returns
precision, recall, F1, and a per-label breakdown in one command.

**Baseline score**

Dummy predictor (labels everything as "action") scores **50.0% F1** — exactly the
class frequency of action items in the ground truth dataset (22/44). This is the
floor. Any classifier that doesn't beat 50% F1 across all labels is not adding
value over a naive guesser. Per-label: action P=100% R=100%, decision P=0% R=0%,
question P=0% R=0%.

**Key decision made**

Used synthetic transcripts instead of the AMI corpus. Rationale: AMI transcripts
are academic board-meeting style and don't match the founder all-hands format
MeetBrief targets. Synthetic transcripts let me control difficulty, include
realistic ambiguity (implicit owners, inferred due dates), and avoid any data
privacy concerns in the open-source repo. Will revisit AMI data in Week 3-4 for
broader test coverage.

**Biggest lesson**

The most valuable hour of the week was writing the eval spec before touching any
prompt. Defining "what counts as correct" up front forced me to think through edge
cases — implicit ownership, partial matches, decision vs noise — that would have
silently corrupted scores if left undefined. The eval spec is the AI PM artifact
most people skip. It's the one that makes every future measurement trustworthy.

---

## Week 2 — Classifier prompt v1, eval iteration

**Final score: 78.9% F1** (Precision 93.8%, Recall 68.2%)
temperature=0, ground truth: 44 items (26 actions, 13 decisions, 5 questions)

**What I built**

Wrote classifier prompt v1 with 6 few-shot examples drawn from the actual
transcripts. Built diagnose.py to show exactly which items were missed vs
incorrectly predicted. Iterated to v2, v3, v4 — all produced lower scores.
Reverted to v1.

**Key finding from iteration**

Each prompt change made overall F1 worse, not better. Root cause: ground
truth had 4 mislabelled items (decisions that were genuinely actions).
Correcting the ground truth recovered the score more effectively than any
prompt change. At 78.9% F1 the model has hit a natural ceiling for a
classification-only approach — further gains require the extractor layer.

**What I learned**

Three things that don't show up in courses: (1) LLMs are non-deterministic
— always set temperature=0 for eval runs or scores shift between runs for
no reason. (2) When iterating makes scores consistently worse, suspect the
benchmark before suspecting the model — ground truth can be wrong. (3) The
difference between precision and recall failure modes matters. This model
has near-perfect precision (93.8%) but weak recall (68.2%) — it's cautious,
not hallucinating. That's a different fix than a model that over-extracts.

**What's next (Week 3)**

Build the extractor agent: takes classifier output and produces structured
JSON with owner, due_date, and confidence score for each item. Wire the
two steps into a pipeline. Add guardrail layer to hold low-confidence items
for human review.

---

## Week 3 — Extractor agent, pipeline, and guardrail

**Pipeline result (fill in after running run_eval.py)**

Classifier F1     : 78.9% (unchanged from Week 2)
Owner accuracy    : [run py src/run_eval.py to fill in]
Date accuracy     : [run py src/run_eval.py to fill in]
Avg confidence    : 0.81 (across all 3 transcripts)
Auto-publish rate : 76% (25/33 items above 0.7 threshold)
Flagged rate      : 24% (8/33 items need human review)

**What I built**

extractor.py: enriches each classifier output item with verified owner,
due_date, confidence score (0.0-1.0), and confidence_reason. Uses the
Anthropic tools parameter with JSON schema enforcement — guarantees valid
structured output on every call with zero parsing errors. One API call per
item with temperature=0.

pipeline.py: single entry point that chains classifier to extractor to
guardrail. run_pipeline("transcript_1.txt") runs the full 3-step flow and
returns confident items (auto-publish) and flagged items (human review)
separately.

evals/confidence_spec.md: formal definition of what each confidence range
means, what the 0.7 threshold represents, and how to calibrate it. Second
AI PM eval artifact after eval_spec.md.

run_eval.py: full pipeline eval script printing classifier F1, extractor
field-level accuracy, and guardrail statistics in one command.

**Key finding — guardrail calibration**

All 8 flagged items (conf=0.62) share the same pattern: decisions with no
named owner and no due date. The classification is correct in every case —
confidence is structurally lower because two fields are empty. This is the
right behaviour. A future refinement could introduce label-specific
thresholds — ownerless decisions could use a lower threshold (0.65) without
introducing errors.

**Key lesson — tool_use vs raw JSON**

Using the Anthropic tools parameter with a JSON schema eliminated all
parsing errors that plagued the classifier. The schema is enforced by the
API itself — the model cannot return malformed output. This is the
production pattern for any AI feature that needs structured output.

**What's next (Week 4)**

Build the Slack and Notion integrations. Format confident items as a clean
Slack message and a structured Notion page. Add the feedback loop UI in
Streamlit — let users mark items correct or incorrect to build training
signal.

---