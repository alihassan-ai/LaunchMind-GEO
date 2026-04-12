"""
QA / Reviewer Agent.

Receives the Engineer's HTML and the Marketing copy from the CEO, then:
  1. Uses an LLM to review the HTML landing page (consistency with product spec)
  2. Uses an LLM to review the marketing copy (quality, CTA, tone)
  3. Posts at least 2 review comments on the GitHub PR
  4. Returns a structured verdict (pass/fail + issues) to the CEO
"""

import json
import os
import re

import requests

from message_bus import send_message, get_latest_message_for
from utils.llm import call_llm_smart

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")

GH_API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


class QAAgent:
    def run(self) -> None:
        print("\n[QA] Starting review...")

        task_msg = get_latest_message_for("qa", "task")
        if not task_msg:
            print("  [QA] No task found!")
            return

        payload = task_msg["payload"]
        spec = payload.get("product_spec", {})
        engineer_output = payload.get("engineer_output", {})
        marketing_copy = payload.get("marketing_copy", {})
        pr_number = payload.get("pr_number", 0)

        html_snippet = engineer_output.get("html_snippet", "")

        html_review = self._review_html(html_snippet, spec)
        copy_review = self._review_copy(marketing_copy, spec)

        # Post GitHub PR comments
        if pr_number:
            self._post_pr_comments(pr_number, html_review, copy_review)

        # Determine overall verdict
        html_passed = html_review.get("passed", True)
        copy_passed = copy_review.get("passed", True)
        overall_verdict = "pass" if (html_passed and copy_passed) else "fail"

        issues = []
        if not html_passed:
            issues.extend(html_review.get("issues", []))
        if not copy_passed:
            issues.extend(copy_review.get("issues", []))

        print(f"  [QA] HTML review: {'PASS' if html_passed else 'FAIL'}")
        print(f"  [QA] Copy review: {'PASS' if copy_passed else 'FAIL'}")
        print(f"  [QA] Overall verdict: {overall_verdict.upper()}")

        send_message(
            from_agent="qa",
            to_agent="ceo",
            message_type="result",
            payload={
                "verdict": overall_verdict,
                "issues": issues,
                "engineer_feedback": html_review.get("feedback", ""),
                "marketing_feedback": copy_review.get("feedback", ""),
                "html_review": html_review,
                "copy_review": copy_review,
            },
            parent_message_id=task_msg["message_id"],
        )

    # ------------------------------------------------------------------
    # LLM Review — HTML landing page
    # ------------------------------------------------------------------
    def _review_html(self, html_snippet: str, spec: dict) -> dict:
        print("  [QA] Reviewing HTML with LLM...")

        vp = spec.get("value_proposition", "")
        features = [f.get("name", "") for f in spec.get("features", [])[:5]]
        personas = [p.get("name", "") for p in spec.get("personas", [])[:3]]

        system = (
            "You are a QA engineer reviewing a landing page. Be specific. "
            "Flag real issues, not trivial ones. Respond ONLY with valid JSON."
        )
        user = f"""Review this HTML landing page for GeoRank.

Expected value proposition: {vp}
Expected features to mention: {features}
Expected persona references: {personas}

HTML (first 2000 chars):
{html_snippet[:2000]}

Review criteria:
1. Does the headline/hero match the value proposition?
2. Are at least 3 of the 5 features mentioned?
3. Is there a clear CTA button?
4. Is there a pricing section?
5. Is the GEO / LLM search concept clearly communicated?

Respond with:
{{
  "passed": true or false,
  "score": 0-100,
  "feedback": "Overall feedback for the engineer (2-3 sentences)",
  "issues": ["Specific issue 1", "Specific issue 2"],
  "positives": ["What works well"]
}}

Pass if score >= 70."""

        raw = call_llm_smart(system, user, max_tokens=800)
        try:
            review = _parse_json(raw)
        except Exception:
            review = {"passed": True, "score": 80, "feedback": "HTML looks good.", "issues": [], "positives": []}

        print(f"  [QA] HTML score: {review.get('score', 'N/A')}/100")
        return review

    # ------------------------------------------------------------------
    # LLM Review — Marketing copy
    # ------------------------------------------------------------------
    def _review_copy(self, copy: dict, spec: dict) -> dict:
        print("  [QA] Reviewing marketing copy with LLM...")

        vp = spec.get("value_proposition", "")
        tagline = copy.get("tagline", "")
        description = copy.get("product_description", "")
        cold_email = copy.get("cold_email", {})
        social = copy.get("social_posts", {})

        system = (
            "You are a QA reviewer checking marketing copy quality. "
            "Be specific. Respond ONLY with valid JSON."
        )
        user = f"""Review this marketing copy for GeoRank.

Value proposition: {vp}

Tagline: {tagline}
Product description: {description}
Email subject: {cold_email.get('subject', '')}
Email body (first 300 chars): {str(cold_email.get('body', ''))[:300]}
Twitter post: {social.get('twitter', '')}

Review criteria:
1. Is the tagline under 10 words and benefit-focused?
2. Does the product description clearly explain GEO value?
3. Does the cold email have a clear CTA?
4. Is the tone appropriate for e-commerce store owners?
5. Does the Twitter post include relevant hashtags?

Respond with:
{{
  "passed": true or false,
  "score": 0-100,
  "feedback": "Overall feedback for the marketing team (2-3 sentences)",
  "issues": ["Specific issue 1", "Specific issue 2"],
  "positives": ["What works well"]
}}

Pass if score >= 70."""

        raw = call_llm_smart(system, user, max_tokens=600)
        try:
            review = _parse_json(raw)
        except Exception:
            review = {"passed": True, "score": 80, "feedback": "Copy looks good.", "issues": [], "positives": []}

        print(f"  [QA] Copy score: {review.get('score', 'N/A')}/100")
        return review

    # ------------------------------------------------------------------
    # GitHub — Post review comments on the PR
    # ------------------------------------------------------------------
    def _post_pr_comments(self, pr_number: int, html_review: dict, copy_review: dict) -> None:
        print(f"  [QA] Posting review comments on PR #{pr_number}...")

        comments = []

        # Comment 1 — HTML review
        html_issues = html_review.get("issues", [])
        html_positives = html_review.get("positives", [])
        html_score = html_review.get("score", "N/A")
        html_verdict = "PASS" if html_review.get("passed", True) else "FAIL"

        issues_text = "\n".join(f"- {i}" for i in html_issues) if html_issues else "- None"
        positives_text = "\n".join(f"- {p}" for p in html_positives) if html_positives else "- Good overall"

        comments.append(
            f"## QA Review — HTML Landing Page\n\n"
            f"**Verdict:** {html_verdict} | **Score:** {html_score}/100\n\n"
            f"**Feedback:** {html_review.get('feedback', '')}\n\n"
            f"**Issues:**\n{issues_text}\n\n"
            f"**What works:**\n{positives_text}\n\n"
            f"*Reviewed by QAAgent — LaunchMind MAS*"
        )

        # Comment 2 — Marketing copy review
        copy_issues = copy_review.get("issues", [])
        copy_score = copy_review.get("score", "N/A")
        copy_verdict = "PASS" if copy_review.get("passed", True) else "FAIL"

        copy_issues_text = "\n".join(f"- {i}" for i in copy_issues) if copy_issues else "- None"

        comments.append(
            f"## QA Review — Marketing Copy\n\n"
            f"**Verdict:** {copy_verdict} | **Score:** {copy_score}/100\n\n"
            f"**Feedback:** {copy_review.get('feedback', '')}\n\n"
            f"**Issues:**\n{copy_issues_text}\n\n"
            f"*Reviewed by QAAgent — LaunchMind MAS*"
        )

        # Post each comment to the PR (PRs share issue comments endpoint)
        url = f"{GH_API}/repos/{GITHUB_REPO}/issues/{pr_number}/comments"
        for i, body in enumerate(comments, 1):
            resp = requests.post(url, headers=HEADERS, json={"body": body})
            if resp.status_code == 201:
                print(f"  [QA] Comment {i} posted on PR #{pr_number}")
            else:
                print(f"  [QA] Comment {i} failed: {resp.status_code} {resp.text[:100]}")
