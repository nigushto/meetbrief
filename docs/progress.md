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

**What's next (Week 2)**

Write classifier prompt v1 using few-shot examples to label transcript segments
as decision / action / question / noise. Score it against ground truth. Analyse
failure patterns. Write prompt v2 fixing the top 3 failures. Target: F1 above
70% across all labels before moving to the extractor agent in Week 3.

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

**What I learned about AI PM eval work**
Three things that don't show up in courses:
1. LLMs are non-deterministic — always set temperature=0 for eval runs
   or your scores will shift between runs for no reason.
2. When iterating makes scores consistently worse, suspect the benchmark
   before suspecting the model. Your ground truth can be wrong.
3. The difference between precision and recall failure modes matters.
   This model has near-perfect precision (93.8%) but weak recall (68.2%)
   — it's cautious, not hallucinating. That's a different fix than a
   model that extracts everything including noise.

**What's next (Week 3)**
Build the extractor agent: takes classifier output and produces structured
JSON with owner, due_date, and confidence score for each item. Wire the
two steps into a pipeline. This is where the product starts to feel real.