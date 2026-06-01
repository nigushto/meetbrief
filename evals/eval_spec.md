# MeetBrief Eval Spec v1.0

## What this document is
This spec defines what counts as a correct extraction for MeetBrief's 
classifier and extractor agents. It is the ground truth for all eval 
scoring. Any change to these definitions requires a version bump and 
a re-label of the ground truth CSV.

## Correct decision — definition
A **decision** is any statement where a course of action was explicitly 
agreed upon or a choice between options was resolved. The key test: 
*did the group or an authority figure commit to something being true 
going forward?* A decision must be extractable as a declarative 
statement ("We will do X" or "X is the plan"). Discussion that leads 
toward a decision but does not resolve it is labelled noise. A 
decision does not require an owner or a due date — those are optional 
attributes. Predictions, observations, and open questions are never 
decisions even if stated confidently.

## Correct action item — definition
An **action item** is any task assigned (explicitly or implicitly) to 
an identifiable person, with an implied or stated expectation of 
completion. The key test: *is there a human who would be accountable 
if this didn't get done?* The owner must be inferable from the 
transcript — do not hallucinate an owner who was not mentioned. Due 
dates should be extracted when stated; inferred dates (e.g. "this 
week" → nearest Friday) are acceptable but must be flagged with 
inferred: true in the output. An action that duplicates a decision 
(same event, same owner) should be labelled action only.

## Scoring — what counts as a match
A predicted item is a **true positive** if: (1) the label matches the 
ground truth label, AND (2) the extracted text captures the same 
commitment — same actor, same task, same scope. Exact wording is not 
required. Partial matches (correct label, wrong owner) count as true 
positives for label scoring but false positives for field-level 
scoring. A predicted item with no corresponding ground truth entry is 
a **false positive**. A ground truth item with no corresponding 
prediction is a **false negative**.
