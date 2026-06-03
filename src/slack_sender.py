import os
import json

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")


def format_slack_message(pipeline_result, meeting_title=None):
    """
    Formats pipeline output into a clean Slack message using mrkdwn.

    Slack message structure:
      Header   : meeting title + stats summary
      Decisions: bullet list of confident decisions
      Actions  : bullet list of confident actions with owner + date
      Questions: bullet list of open questions
      Flagged  : count of items held for review (not shown in detail)

    Args:
        pipeline_result (dict) - output from run_pipeline()
        meeting_title   (str)  - optional human-readable meeting name
                                 defaults to transcript_id

    Returns:
        dict - Slack blocks payload ready to POST
    """

    confident = pipeline_result["confident"]
    flagged   = pipeline_result["flagged"]
    stats     = pipeline_result["stats"]
    tid       = pipeline_result["transcript_id"]
    title     = meeting_title or tid.replace("_", " ").title()

    # Split confident items by label
    decisions = [i for i in confident if i["label"] == "decision"]
    actions   = [i for i in confident if i["label"] == "action"]
    questions = [i for i in confident if i["label"] == "question"]

    blocks = []

    # --- Header block ---
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📋 MeetBrief — {title}",
            "emoji": True
        }
    })

    # --- Stats summary ---
    label_counts = stats.get("label_counts", {})
    summary_text = (
        f"*{stats['total_items']} items extracted* · "
        f"{stats['confident_count']} auto-published · "
        f"{stats['flagged_count']} flagged for review · "
        f"avg confidence {stats['avg_confidence']:.0%}"
    )
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": summary_text}
    })

    blocks.append({"type": "divider"})

    # --- Decisions ---
    if decisions:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*✅ Decisions ({len(decisions)})*"
            }
        })
        decision_lines = []
        for item in decisions:
            owner = f"  _{item['owner']}_" if item["owner"] else ""
            decision_lines.append(f"• {item['text']}{owner}")

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(decision_lines)
            }
        })

    # --- Actions ---
    if actions:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📌 Action Items ({len(actions)})*"
            }
        })
        action_lines = []
        for item in actions:
            owner = f"*{item['owner']}*" if item["owner"] else "_unassigned_"
            date  = f"  · due {item['due_date']}" if item["due_date"] else ""
            action_lines.append(f"• {owner} — {item['text']}{date}")

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(action_lines)
            }
        })

    # --- Open questions ---
    if questions:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*❓ Open Questions ({len(questions)})*"
            }
        })
        question_lines = [f"• {item['text']}" for item in questions]
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(question_lines)
            }
        })

    # --- Flagged items notice ---
    if flagged:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⚑ *{len(flagged)} item(s) flagged for review* — "
                    f"low confidence, not included above. "
                    f"Review in MeetBrief before publishing."
                )
            }
        })

    return {"blocks": blocks}


def send_to_slack(pipeline_result, meeting_title=None, webhook_url=None):
    """
    Formats and sends pipeline output to Slack via incoming webhook.

    Args:
        pipeline_result (dict)      - output from run_pipeline()
        meeting_title   (str|None)  - human-readable meeting name
        webhook_url     (str|None)  - override webhook URL (uses .env default)

    Returns:
        dict with keys:
            success  (bool)   - True if Slack accepted the message
            status   (int)    - HTTP status code
            message  (str)    - description of outcome
    """

    url = webhook_url or SLACK_WEBHOOK_URL

    if not url:
        return {
            "success": False,
            "status":  0,
            "message": "No SLACK_WEBHOOK_URL found. Add it to your .env file."
        }

    payload = format_slack_message(pipeline_result, meeting_title)

    try:
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200 and response.text == "ok":
            return {
                "success": True,
                "status":  200,
                "message": "Message posted to Slack successfully."
            }
        else:
            return {
                "success": False,
                "status":  response.status_code,
                "message": f"Slack returned: {response.text}"
            }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "status":  0,
            "message": "Request timed out — check your internet connection."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "status":  0,
            "message": f"Request failed: {str(e)}"
        }


def preview_slack_message(pipeline_result, meeting_title=None):
    """
    Prints a readable preview of what will be posted to Slack.
    Call this before send_to_slack() to verify the output looks right.
    No API call made.
    """
    payload = format_slack_message(pipeline_result, meeting_title)

    print("\n=== Slack message preview ===")
    for block in payload["blocks"]:
        if block["type"] == "header":
            print(f"\n{'=' * 50}")
            print(f"  {block['text']['text']}")
            print(f"{'=' * 50}")
        elif block["type"] == "divider":
            print(f"  {'-' * 44}")
        elif block["type"] == "section":
            text = block["text"]["text"]
            # Clean up mrkdwn markers for readability in terminal
            text = text.replace("*", "").replace("_", "")
            for line in text.split("\n"):
                print(f"  {line}")
    print()


if __name__ == "__main__":

    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from pipeline import run_pipeline

    # --- Step 1: Build a fake pipeline result for preview (no API call) ---
    fake_result = {
        "transcript_id": "transcript_1",
        "confident": [
            {"label": "decision", "text": "Q3 scope is onboarding and Slack integration — AI summary to Q4",
             "owner": "", "due_date": "", "confidence": 0.92, "confidence_reason": ""},
            {"label": "action",   "text": "Ananya to fix dashboard performance",
             "owner": "Ananya", "due_date": "2026-06-11", "confidence": 0.95, "confidence_reason": ""},
            {"label": "action",   "text": "Leila to update roadmap doc and share with team",
             "owner": "Leila", "due_date": "2026-06-05", "confidence": 0.98, "confidence_reason": ""},
            {"label": "action",   "text": "Dan to contact Hartwell with staging environment access",
             "owner": "Dan", "due_date": "2026-06-01", "confidence": 0.88, "confidence_reason": ""},
        ],
        "flagged": [
            {"label": "decision", "text": "Backend engineer hiring moving forward this week",
             "owner": "Priya", "due_date": "", "confidence": 0.62, "confidence_reason": "Owner ambiguous"}
        ],
        "all_items": [],
        "stats": {
            "total_items": 5,
            "confident_count": 4,
            "flagged_count": 1,
            "avg_confidence": 0.87,
            "label_counts": {"decision": 1, "action": 3}
        }
    }

    print("Step 1: Previewing Slack message (no API call)...")
    preview_slack_message(fake_result, meeting_title="Product Strategy All-Hands")

    send_now = input("Step 2: Send this to Slack? (y/n): ").strip().lower()
    if send_now == "y":
        print("Sending to Slack...")
        result = send_to_slack(fake_result, meeting_title="Product Strategy All-Hands")
        if result["success"]:
            print(f"✓ {result['message']}")
        else:
            print(f"✗ Failed: {result['message']}")
    else:
        print("\nSkipped. Run with real pipeline data:")
        print("  py -c \"import sys; sys.path.insert(0,'src'); "
              "from pipeline import run_pipeline; "
              "from slack_sender import send_to_slack, preview_slack_message; "
              "r = run_pipeline('transcript_1.txt', meeting_date='2026-06-01'); "
              "preview_slack_message(r, 'Product All-Hands')\"")