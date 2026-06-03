import os
import sys
import csv
import datetime

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))

from pipeline     import run_pipeline
from slack_sender import send_to_slack, preview_slack_message

# --- Page config ---
st.set_page_config(
    page_title="MeetBrief",
    page_icon="📋",
    layout="wide"
)

# --- Session state initialisation ---
# Must be done before any widget renders
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "feedback" not in st.session_state:
    st.session_state.feedback = {}   # key: item index, value: "correct" | "incorrect"
if "slack_sent" not in st.session_state:
    st.session_state.slack_sent = False
if "feedback_saved" not in st.session_state:
    st.session_state.feedback_saved = False


# --- Helper: feedback CSV path ---
FEEDBACK_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "feedback.csv")


def save_feedback_to_csv(pipeline_result, feedback_dict):
    """Appends feedback rows to data/feedback.csv."""
    timestamp = datetime.datetime.now().isoformat()

    file_exists = os.path.exists(FEEDBACK_CSV)
    is_empty    = not file_exists or os.path.getsize(FEEDBACK_CSV) == 0

    with open(FEEDBACK_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "transcript_id", "label", "text", "owner",
            "due_date", "confidence", "feedback", "timestamp"
        ])

        if is_empty:
            writer.writeheader()

        for idx, decision in feedback_dict.items():
            item = pipeline_result["flagged"][idx]
            writer.writerow({
                "transcript_id": item.get("transcript_id", ""),
                "label":         item.get("label", ""),
                "text":          item.get("text", ""),
                "owner":         item.get("owner", ""),
                "due_date":      item.get("due_date", ""),
                "confidence":    item.get("confidence", ""),
                "feedback":      decision,
                "timestamp":     timestamp,
            })


def label_icon(label):
    icons = {"decision": "✅", "action": "📌", "question": "❓"}
    return icons.get(label, "•")


# ================================================================
# HEADER
# ================================================================
st.title("📋 MeetBrief")
st.caption("Paste a meeting transcript → extract decisions, actions and questions → send to Slack")
st.divider()


# ================================================================
# SECTION 1 — INPUT
# ================================================================
st.subheader("1. Paste your transcript")

col_input, col_config = st.columns([3, 1])

with col_input:
    transcript_text = st.text_area(
        label="Transcript",
        placeholder="Paste your meeting transcript here...",
        height=280,
        label_visibility="collapsed"
    )

with col_config:
    meeting_title = st.text_input(
        "Meeting title",
        placeholder="e.g. Product all-hands",
        help="Used in the Slack message header"
    )
    meeting_date = st.date_input(
        "Meeting date",
        value=datetime.date.today(),
        help="Helps resolve relative dates like 'this week' and 'next Friday'"
    )
    run_button = st.button(
        "Run pipeline",
        type="primary",
        use_container_width=True,
        disabled=not transcript_text.strip()
    )


# ================================================================
# PIPELINE EXECUTION
# ================================================================
if run_button and transcript_text.strip():
    # Reset state for new run
    st.session_state.feedback      = {}
    st.session_state.slack_sent    = False
    st.session_state.feedback_saved = False

    # Write transcript to a temp file — pipeline expects a file path
    tmp_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "raw", "_temp_transcript.txt"
    )
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    meeting_date_str = meeting_date.isoformat()

    with st.spinner("Running pipeline — classifying, extracting, applying guardrail..."):
        result = run_pipeline(
            "_temp_transcript.txt",
            transcript_id=meeting_title or "meeting",
            verbose=False,
            meeting_date=meeting_date_str
        )

    st.session_state.pipeline_result = result
    st.rerun()


# ================================================================
# SECTION 2 — RESULTS
# ================================================================
if st.session_state.pipeline_result:
    result    = st.session_state.pipeline_result
    confident = result["confident"]
    flagged   = result["flagged"]
    stats     = result["stats"]

    st.divider()
    st.subheader("2. Extracted items")

    # --- Stats row ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total items",   stats["total_items"])
    m2.metric("Auto-publish",  stats["confident_count"])
    m3.metric("Flagged",       stats["flagged_count"])
    m4.metric("Avg confidence", f"{stats['avg_confidence']:.0%}")

    st.caption("Auto-publish items are ready to send to Slack. Flagged items need your review first.")

    # --- Confident items ---
    if confident:
        decisions = [i for i in confident if i["label"] == "decision"]
        actions   = [i for i in confident if i["label"] == "action"]
        questions = [i for i in confident if i["label"] == "question"]

        if decisions:
            with st.expander(f"✅ Decisions ({len(decisions)})", expanded=True):
                for item in decisions:
                    st.markdown(f"**{item['text']}**")
                    st.caption(f"confidence {item['confidence']:.0%}")
                    st.divider()

        if actions:
            with st.expander(f"📌 Action items ({len(actions)})", expanded=True):
                for item in actions:
                    owner = f" · owner: **{item['owner']}**" if item["owner"] else ""
                    date  = f" · due: `{item['due_date']}`"  if item["due_date"] else ""
                    st.markdown(f"{item['text']}{owner}{date}")
                    st.caption(f"confidence {item['confidence']:.0%}")
                    st.divider()

        if questions:
            with st.expander(f"❓ Open questions ({len(questions)})", expanded=True):
                for item in questions:
                    st.markdown(f"{item['text']}")
                    st.caption(f"confidence {item['confidence']:.0%}")
                    st.divider()
    else:
        st.info("No high-confidence items found. Check flagged items below.")

    # ================================================================
    # SECTION 3 — FLAGGED ITEMS
    # ================================================================
    if flagged:
        st.divider()
        st.subheader("3. Review flagged items")
        st.warning(
            f"{len(flagged)} item(s) have low confidence and were not auto-published. "
            "Review each one and mark it correct or incorrect.",
            icon="⚠️"
        )

        for idx, item in enumerate(flagged):
            with st.container(border=True):
                col_info, col_btns = st.columns([4, 1])

                with col_info:
                    st.markdown(
                        f"{label_icon(item['label'])} **{item['text']}**"
                    )
                    owner = f"Owner: {item['owner']} · " if item["owner"] else ""
                    date  = f"Due: {item['due_date']} · " if item["due_date"] else ""
                    st.caption(
                        f"{owner}{date}confidence: {item['confidence']:.0%} · "
                        f"_{item['confidence_reason']}_"
                    )

                with col_btns:
                    current = st.session_state.feedback.get(idx)

                    if current == "correct":
                        st.success("Confirmed", icon="✅")
                    elif current == "incorrect":
                        st.error("Rejected", icon="❌")
                    else:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✓", key=f"confirm_{idx}",
                                         help="Mark as correct",
                                         use_container_width=True):
                                st.session_state.feedback[idx] = "correct"
                                st.rerun()
                        with c2:
                            if st.button("✗", key=f"reject_{idx}",
                                         help="Mark as incorrect",
                                         use_container_width=True):
                                st.session_state.feedback[idx] = "incorrect"
                                st.rerun()

        # Save feedback button
        reviewed = len(st.session_state.feedback)
        if reviewed > 0:
            st.caption(f"{reviewed} of {len(flagged)} items reviewed.")
            if st.button(
                "Save feedback",
                disabled=st.session_state.feedback_saved,
                use_container_width=False
            ):
                save_feedback_to_csv(result, st.session_state.feedback)
                st.session_state.feedback_saved = True
                st.rerun()

            if st.session_state.feedback_saved:
                st.success(
                    f"Feedback saved to data/feedback.csv — "
                    f"{reviewed} item(s) recorded.",
                    icon="✅"
                )

    # ================================================================
    # SECTION 4 — SEND TO SLACK
    # ================================================================
    st.divider()
    st.subheader("4. Send to Slack")

    title_for_slack = meeting_title or result["transcript_id"]

    if st.session_state.slack_sent:
        st.success("Sent to Slack successfully.", icon="✅")
    else:
        if st.button(
            "Send to Slack",
            type="primary",
            use_container_width=False
        ):
            with st.spinner("Posting to Slack..."):
                slack_result = send_to_slack(result, meeting_title=title_for_slack)

            if slack_result["success"]:
                st.session_state.slack_sent = True
                st.rerun()
            else:
                st.error(
                    f"Failed to send: {slack_result['message']}",
                    icon="❌"
                )

        st.caption(
            "Only auto-published items are sent. "
            "Flagged items are excluded unless you confirm them above first."
        )