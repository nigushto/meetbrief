import os
import json

import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

NAME_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "name_map.json"
)


def load_name_map():
    """
    Loads the name -> Slack handle mapping from config/name_map.json.

    Returns:
        dict  - e.g. {"Ananya": "@ananya", "Marcus": "@marcus"}
                Empty dict if file not found or unreadable.
    """
    if not os.path.exists(NAME_MAP_PATH):
        return {}
    try:
        with open(NAME_MAP_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (json.JSONDecodeError, OSError):
        return {}


def save_name_map(name_map):
    """
    Saves the name map dict back to config/name_map.json.
    Preserves the _readme comment line.
    """
    os.makedirs(os.path.dirname(NAME_MAP_PATH), exist_ok=True)
    payload = {
        "_readme": "Map first names from transcripts to Slack @handles. Remove this _readme line before sharing."
    }
    payload.update(name_map)
    with open(NAME_MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def resolve_owner(owner_name, name_map):
    """
    Resolves an owner first name to a Slack @mention or bold fallback.

    Returns:
        str  - e.g. "@ananya" if found, "*Ananya*" if not found, "_unassigned_" if empty
    """
    if not owner_name:
        return "_unassigned_"
    mention = name_map.get(owner_name)
    if mention:
        return mention
    return f"*{owner_name}*"


def get_unmapped_owners(pipeline_result, name_map):
    """
    Returns a list of owner names in the pipeline result that are not
    in the name map. Used to surface a warning in the UI.
    """
    unmapped = set()
    for item in pipeline_result.get("confident", []):
        if item["label"] == "action" and item["owner"]:
            if item["owner"] not in name_map:
                unmapped.add(item["owner"])
    return sorted(unmapped)


def format_slack_message(pipeline_result, meeting_title=None, name_map=None,
                         preview=False):
    """
    Formats pipeline output into a Slack Block Kit message.

    @mentions owners of action items when found in name_map.
    Falls back to *bold name* when not found.

    Args:
        pipeline_result (dict)       - output from run_pipeline()
        meeting_title   (str|None)   - human-readable meeting name
        name_map        (dict|None)  - name -> handle mapping.
                                       Loads from config/name_map.json if None.
        preview         (bool)       - if True, also returns a plain-text
                                       preview string for dry-run inspection

    Returns:
        dict  - {"blocks": [...]}  always present
              - {"blocks": [...], "preview_text": "..."}  when preview=True
    """

    if name_map is None:
        name_map = load_name_map()

    confident = pipeline_result["confident"]
    flagged   = pipeline_result["flagged"]
    stats     = pipeline_result["stats"]
    tid       = pipeline_result["transcript_id"]
    title     = meeting_title or tid.replace("_", " ").title()

    decisions = [i for i in confident if i["label"] == "decision"]
    actions   = [i for i in confident if i["label"] == "action"]
    questions = [i for i in confident if i["label"] == "question"]

    blocks       = []
    preview_lines = []

    # --- Header ---
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"📋 MeetBrief — {title}", "emoji": True}
    })
    preview_lines.append(f"{'=' * 52}")
    preview_lines.append(f"  📋 MeetBrief — {title}")
    preview_lines.append(f"{'=' * 52}")

    # --- Stats ---
    summary_text = (
        f"*{stats['total_items']} items extracted* · "
        f"{stats['confident_count']} auto-published · "
        f"{stats['flagged_count']} flagged for review · "
        f"avg confidence {stats['avg_confidence']:.0%}"
    )
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": summary_text}})
    preview_lines.append(f"  {stats['total_items']} items · "
                         f"{stats['confident_count']} published · "
                         f"{stats['flagged_count']} flagged")

    blocks.append({"type": "divider"})
    preview_lines.append(f"  {'-' * 46}")

    # --- Decisions ---
    if decisions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*✅ Decisions ({len(decisions)})*"}
        })
        preview_lines.append(f"  ✅ Decisions ({len(decisions)})")
        decision_lines = []
        for item in decisions:
            owner_str = f"  _{item['owner']}_" if item["owner"] else ""
            decision_lines.append(f"• {item['text']}{owner_str}")
            preview_lines.append(f"    • {item['text']}"
                                  + (f"  [{item['owner']}]" if item["owner"] else ""))
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(decision_lines)}
        })

    # --- Actions (with @mentions) ---
    if actions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📌 Action Items ({len(actions)})*"}
        })
        preview_lines.append(f"\n  📌 Action Items ({len(actions)})")
        action_lines = []
        for item in actions:
            mention = resolve_owner(item["owner"], name_map)
            date    = f"  · due {item['due_date']}" if item["due_date"] else ""
            action_lines.append(f"• {mention} — {item['text']}{date}")

            # Preview: show whether mention was resolved or fell back
            resolved = item["owner"] in name_map if item["owner"] else False
            tag      = "(mention)" if resolved else "(name not in map — bold fallback)"
            preview_lines.append(f"    • {mention} — {item['text']}{date}  {tag}")

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(action_lines)}
        })

    # --- Questions ---
    if questions:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*❓ Open Questions ({len(questions)})*"}
        })
        preview_lines.append(f"\n  ❓ Open Questions ({len(questions)})")
        question_lines = [f"• {item['text']}" for item in questions]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(question_lines)}
        })
        for item in questions:
            preview_lines.append(f"    • {item['text']}")

    # --- Flagged notice ---
    if flagged:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"⚠️ *{len(flagged)} item(s) flagged for review* — "
                    f"low confidence, not included above. "
                    f"Review in MeetBrief before publishing."
                )
            }
        })
        preview_lines.append(f"\n  ⚠️  {len(flagged)} item(s) flagged — not shown here")

    result = {"blocks": blocks}
    if preview:
        result["preview_text"] = "\n".join(preview_lines)
    return result


def send_to_slack(pipeline_result, meeting_title=None, webhook_url=None,
                  name_map=None):
    """
    Formats and sends pipeline output to Slack via incoming webhook.

    Args:
        pipeline_result (dict)      - output from run_pipeline()
        meeting_title   (str|None)  - human-readable meeting name
        webhook_url     (str|None)  - override URL (uses .env default)
        name_map        (dict|None) - name -> handle mapping (loads from file if None)

    Returns:
        dict with keys: success (bool), status (int), message (str)
    """
    url = webhook_url or SLACK_WEBHOOK_URL

    if not url:
        return {
            "success": False, "status": 0,
            "message": "No SLACK_WEBHOOK_URL found. Add it to your .env file."
        }

    if name_map is None:
        name_map = load_name_map()

    payload = format_slack_message(pipeline_result, meeting_title,
                                   name_map=name_map)

    try:
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 200 and response.text == "ok":
            return {"success": True, "status": 200,
                    "message": "Message posted to Slack successfully."}
        else:
            return {"success": False, "status": response.status_code,
                    "message": f"Slack returned: {response.text}"}

    except requests.exceptions.Timeout:
        return {"success": False, "status": 0,
                "message": "Request timed out — check your internet connection."}
    except requests.exceptions.RequestException as e:
        return {"success": False, "status": 0,
                "message": f"Request failed: {str(e)}"}


def preview_slack_message(pipeline_result, meeting_title=None, name_map=None):
    """
    Prints a dry-run preview of the Slack message — no API call.
    Shows whether each owner resolved to a @mention or bold fallback.
    """
    if name_map is None:
        name_map = load_name_map()
    result = format_slack_message(pipeline_result, meeting_title,
                                  name_map=name_map, preview=True)
    print("\n=== Slack message dry-run preview ===")
    print(result["preview_text"])
    unmapped = get_unmapped_owners(pipeline_result, name_map)
    if unmapped:
        print(f"\n  ⚠️  Unmapped owners (bold fallback): {', '.join(unmapped)}")
        print("  Add them to config/name_map.json to enable @mentions.")
    print()


if __name__ == "__main__":
    fake_result = {
        "transcript_id": "transcript_1",
        "confident": [
            {"label": "decision",
             "text": "Q3 scope is onboarding and Slack — AI summary to Q4",
             "owner": "", "due_date": "", "confidence": 0.92, "confidence_reason": ""},
            {"label": "action",
             "text": "Fix dashboard performance — composite indexes",
             "owner": "Ananya", "due_date": "2026-06-11", "confidence": 0.95,
             "confidence_reason": ""},
            {"label": "action",
             "text": "Update roadmap doc and share with team",
             "owner": "Leila", "due_date": "2026-06-05", "confidence": 0.98,
             "confidence_reason": ""},
            {"label": "action",
             "text": "Contact Hartwell with staging environment access",
             "owner": "Zara", "due_date": "2026-06-01", "confidence": 0.88,
             "confidence_reason": ""},
        ],
        "flagged": [
            {"label": "decision",
             "text": "Backend engineer hiring moving forward this week",
             "owner": "Priya", "due_date": "", "confidence": 0.62,
             "confidence_reason": "Owner ambiguous"}
        ],
        "all_items": [],
        "stats": {
            "total_items": 5, "confident_count": 4, "flagged_count": 1,
            "avg_confidence": 0.87, "label_counts": {"decision": 1, "action": 3}
        }
    }

    print("Dry-run preview (Zara is intentionally not in the name map):")
    preview_slack_message(fake_result, meeting_title="Product Strategy All-Hands")