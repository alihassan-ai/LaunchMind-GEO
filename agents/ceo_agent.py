"""
CEO Agent — Orchestrator.

Responsibilities:
  1. Decompose the startup idea into tasks for each sub-agent (LLM call #1)
  2. Review the Product agent's spec and decide approve / revise (LLM call #2)
  3. Forward the approved spec to Engineer and Marketing
  4. Review the QA verdict and trigger a revision loop if needed (LLM call #3)
  5. Post the final launch summary to Slack
"""

import json
import os
import re
import requests

from message_bus import send_message, get_messages_for, get_latest_message_for
from utils.llm import call_llm_smart

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#launches")


def _parse_json(text: str) -> dict:
    """Extract and parse JSON from an LLM response, handling markdown fences."""
    text = text.strip()
    # Strip ```json ... ``` fences
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    # Fallback: find first { ... }
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


class CEOAgent:
    def __init__(self):
        self.startup_idea: str = ""
        self.approved_spec: dict = {}
        self.pr_url: str = ""
        self.pr_number: int = 0
        self.issue_url: str = ""
        self.marketing_copy: dict = {}
        self._decisions: list = []

    # ------------------------------------------------------------------
    # Step 1 — Decompose idea and task Product agent
    # ------------------------------------------------------------------
    def decompose_idea(self, idea: str) -> str:
        print("\n[CEO] Step 1: Decomposing startup idea with LLM...")
        self.startup_idea = idea

        system = (
            "You are the CEO of LaunchMind, an AI startup accelerator. "
            "You receive a startup idea and must create specific, actionable tasks "
            "for your specialist agents. Respond ONLY with valid JSON — no extra text."
        )
        user = f"""Startup idea:
{idea}

Create detailed tasks for each agent. Be concrete and specific.

Return exactly this JSON:
{{
  "startup_summary": "2-3 sentence summary of GeoRank",
  "product_task": "What the Product Manager agent must research and produce",
  "engineer_task": "What the Engineer agent must build (landing page focus areas)",
  "marketing_task": "What the Marketing agent must create (channels, tone, goals)"
}}"""

        response = call_llm_smart(system, user)
        tasks = _parse_json(response)

        self._log("Decomposed startup idea via LLM", tasks)
        print(f"  [CEO] Summary: {tasks.get('startup_summary', '')[:120]}...")

        msg_id = send_message(
            from_agent="ceo",
            to_agent="product",
            message_type="task",
            payload={
                "idea": idea,
                "startup_summary": tasks.get("startup_summary", ""),
                "instructions": tasks.get("product_task", ""),
                "engineer_task_context": tasks.get("engineer_task", ""),
                "marketing_task_context": tasks.get("marketing_task", ""),
            },
        )
        return msg_id

    # ------------------------------------------------------------------
    # Step 3 — Review Product spec (LLM call #2 — THE FEEDBACK LOOP)
    # ------------------------------------------------------------------
    def review_product_output(self) -> bool:
        print("\n[CEO] Step 3: Reviewing Product spec with LLM (feedback loop)...")

        product_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "product" and m["message_type"] == "result"
        ]
        if not product_msgs:
            print("  [CEO] ERROR: No product spec received.")
            return True  # Skip revision, continue

        latest = product_msgs[-1]
        spec = latest["payload"].get("product_spec", {})

        system = (
            "You are a strict CEO reviewing a product specification. "
            "Your startup is GeoRank — a Generative Engine Optimization platform for e-commerce. "
            "Reject specs that are too generic or missing GEO-specific detail. "
            "Respond ONLY with valid JSON."
        )
        user = f"""Startup idea:
{self.startup_idea}

Product spec submitted by the Product agent:
{json.dumps(spec, indent=2)}

Evaluate strictly:
1. Is the value proposition specific to GEO / LLM search visibility for e-commerce?
2. Do the personas represent real e-commerce store owners or marketers?
3. Are the features concrete GEO features (not generic SEO)?
4. Are user stories specific enough to guide engineering?

Respond with:
{{
  "approved": true,
  "reasoning": "Why it passes or fails",
  "feedback": "Specific improvements needed (leave empty string if approved)"
}}"""

        response = call_llm_smart(system, user)
        review = _parse_json(response)

        approved = review.get("approved", True)
        reasoning = review.get("reasoning", "")
        feedback = review.get("feedback", "")

        print(f"  [CEO] Verdict: {'APPROVED' if approved else 'NEEDS REVISION'}")
        print(f"  [CEO] Reasoning: {reasoning[:150]}...")

        if approved:
            self.approved_spec = spec
            send_message(
                from_agent="ceo",
                to_agent="product",
                message_type="confirmation",
                payload={"status": "approved", "reasoning": reasoning},
                parent_message_id=latest["message_id"],
            )
        else:
            print(f"  [CEO] Sending revision request: {feedback[:100]}...")
            send_message(
                from_agent="ceo",
                to_agent="product",
                message_type="revision_request",
                payload={"feedback": feedback, "reasoning": reasoning},
                parent_message_id=latest["message_id"],
            )

        self._log(
            f"Reviewed product spec — {'approved' if approved else 'revision requested'}",
            review,
        )
        return approved

    def accept_revised_product(self) -> None:
        """After revision, accept the updated spec unconditionally."""
        product_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "product" and m["message_type"] == "result"
        ]
        if product_msgs:
            self.approved_spec = product_msgs[-1]["payload"].get("product_spec", {})
            print("  [CEO] Accepted revised product spec")

    # ------------------------------------------------------------------
    # Step 4a — Task Engineer
    # ------------------------------------------------------------------
    def task_engineer(self) -> str:
        print("\n[CEO] Step 4a: Tasking Engineer agent...")
        task_msg = get_latest_message_for("product", "task")
        engineer_ctx = ""
        if task_msg:
            engineer_ctx = task_msg["payload"].get("engineer_task_context", "")

        return send_message(
            from_agent="ceo",
            to_agent="engineer",
            message_type="task",
            payload={
                "product_spec": self.approved_spec,
                "instructions": engineer_ctx or (
                    "Build a professional HTML landing page for GeoRank. "
                    "Include: hero section, features, how-it-works, pricing teaser, CTA."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Step 4b — Task Marketing (after engineer result received)
    # ------------------------------------------------------------------
    def task_marketing(self) -> str:
        print("\n[CEO] Step 4b: Tasking Marketing agent...")
        task_msg = get_latest_message_for("product", "task")
        marketing_ctx = ""
        if task_msg:
            marketing_ctx = task_msg["payload"].get("marketing_task_context", "")

        return send_message(
            from_agent="ceo",
            to_agent="marketing",
            message_type="task",
            payload={
                "product_spec": self.approved_spec,
                "pr_url": self.pr_url,
                "instructions": marketing_ctx or (
                    "Create launch copy for GeoRank targeting e-commerce store owners. "
                    "Tone: confident, technical, growth-focused."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Step 5 — Collect Engineer result
    # ------------------------------------------------------------------
    def collect_engineer_result(self) -> bool:
        engineer_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "engineer" and m["message_type"] == "result"
        ]
        if not engineer_msgs:
            print("  [CEO] No engineer result found.")
            return False
        payload = engineer_msgs[-1]["payload"]
        self.pr_url = payload.get("pr_url", "")
        self.pr_number = payload.get("pr_number", 0)
        self.issue_url = payload.get("issue_url", "")
        print(f"  [CEO] Engineer result: PR={self.pr_url}")
        return True

    # ------------------------------------------------------------------
    # Step 6 — Collect Marketing result
    # ------------------------------------------------------------------
    def collect_marketing_result(self) -> bool:
        marketing_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "marketing" and m["message_type"] == "result"
        ]
        if not marketing_msgs:
            print("  [CEO] No marketing result found.")
            return False
        self.marketing_copy = marketing_msgs[-1]["payload"].get("copy", {})
        print("  [CEO] Marketing result collected")
        return True

    # ------------------------------------------------------------------
    # Step 7 — Task QA
    # ------------------------------------------------------------------
    def task_qa(self) -> str:
        print("\n[CEO] Step 7: Tasking QA agent...")
        engineer_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "engineer" and m["message_type"] == "result"
        ]
        engineer_output = engineer_msgs[-1]["payload"] if engineer_msgs else {}

        return send_message(
            from_agent="ceo",
            to_agent="qa",
            message_type="task",
            payload={
                "product_spec": self.approved_spec,
                "engineer_output": engineer_output,
                "marketing_copy": self.marketing_copy,
                "pr_url": self.pr_url,
                "pr_number": self.pr_number,
            },
        )

    # ------------------------------------------------------------------
    # Step 8 — Review QA verdict (LLM call #3 — SECOND FEEDBACK LOOP)
    # ------------------------------------------------------------------
    def review_qa_verdict(self) -> bool:
        print("\n[CEO] Step 8: Reviewing QA verdict with LLM (second feedback loop)...")

        qa_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "qa" and m["message_type"] == "result"
        ]
        if not qa_msgs:
            print("  [CEO] No QA verdict received — assuming pass.")
            return True

        qa_payload = qa_msgs[-1]["payload"]
        verdict = qa_payload.get("verdict", "pass")
        issues = qa_payload.get("issues", [])
        engineer_feedback = qa_payload.get("engineer_feedback", "")
        marketing_feedback = qa_payload.get("marketing_feedback", "")

        print(f"  [CEO] QA Verdict: {verdict.upper()}")
        if issues:
            print(f"  [CEO] Issues: {issues}")

        self._log(f"QA verdict received: {verdict}", qa_payload)

        if verdict == "fail":
            print("  [CEO] Sending revision request to Engineer...")
            send_message(
                from_agent="ceo",
                to_agent="engineer",
                message_type="revision_request",
                payload={
                    "feedback": engineer_feedback,
                    "issues": issues,
                },
                parent_message_id=qa_msgs[-1]["message_id"],
            )
            return False

        return True

    def collect_revised_engineer_result(self) -> None:
        """After engineer revision, update the stored PR URL."""
        engineer_msgs = [
            m for m in get_messages_for("ceo")
            if m["from_agent"] == "engineer" and m["message_type"] == "result"
        ]
        if engineer_msgs:
            payload = engineer_msgs[-1]["payload"]
            self.pr_url = payload.get("pr_url", self.pr_url)
            print(f"  [CEO] Revised engineer result received: PR={self.pr_url}")

    # ------------------------------------------------------------------
    # Step 9 — Post final Slack summary
    # ------------------------------------------------------------------
    def post_final_summary(self) -> None:
        print("\n[CEO] Step 9: Posting final launch summary to Slack...")

        tagline = self.marketing_copy.get("tagline", "GeoRank — Be the LLM's Answer")
        description = self.marketing_copy.get(
            "product_description",
            "GeoRank optimizes your e-commerce store for LLM search visibility.",
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "LaunchMind: Mission Complete!"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{tagline}*\n\n{description}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*GitHub PR:*\n<{self.pr_url}|View Pull Request>",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*GitHub Issue:*\n<{self.issue_url}|View Issue>",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Pipeline status:*\n"
                        ":white_check_mark: CEO  :white_check_mark: Product  "
                        ":white_check_mark: Engineer  :white_check_mark: Marketing  "
                        ":white_check_mark: QA"
                    ),
                },
            },
        ]

        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={
                "channel": SLACK_CHANNEL,
                "blocks": blocks,
                "text": f"LaunchMind launch complete: {tagline}",
            },
        )
        data = resp.json()
        if data.get("ok"):
            print("  [CEO] Final summary posted to Slack successfully!")
        else:
            print(f"  [CEO] Slack error: {data.get('error')}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _log(self, decision: str, context: dict = None) -> None:
        entry = {"decision": decision, "context": context or {}}
        self._decisions.append(entry)
        print(f"  [CEO LOG] {decision}")

    def print_decision_log(self) -> None:
        print("\n=== CEO DECISION LOG ===")
        for i, d in enumerate(self._decisions, 1):
            print(f"  {i}. {d['decision']}")
        print("========================\n")
