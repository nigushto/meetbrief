V1 failure
-----------------------------------------------
Pattern 1 — Implicit decisions not extracted
Recall on decisions is 41%. The model is catching explicit decisions ("OK we're aligned, Q3 is X") but missing decisions that are implied through discussion convergence rather than a clear declaration. Transcript_1 had 5 false negatives despite being the simplest transcript — those are almost certainly implicit decisions.
Pattern 2 — Questions buried in long transcripts
Only 2 of 5 questions found. Transcript_3 is 55 minutes of dense content — open questions raised early in the meeting get lost by the time the model reaches the end of its context. The model is likely focusing on the most recent content.
Pattern 3 — Conservative extraction overall
33 predictions against 44 ground truth items — the model is under-extracting by 25%. High precision (93.9%) + low recall (70.5%) is the classic "cautious model" signature. The prompt is too conservative about what counts as worth extracting.