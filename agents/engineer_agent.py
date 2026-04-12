"""
Engineer Agent — Builder.

Reads the product spec, generates an HTML landing page with an LLM,
then takes real actions on GitHub:
  1. Creates a GitHub Issue titled "Initial landing page"
  2. Creates a new branch (agent/landing-page-<timestamp>)
  3. Commits index.html to that branch
  4. Opens a Pull Request
  5. Reports back to CEO

Supports one revision cycle: if the CEO sends a revision_request,
it rewrites the HTML and pushes a new commit to the same branch.
"""

import base64
import json
import os
import re
import time

import requests

from message_bus import send_message, get_latest_message_for, get_messages_for
from utils.llm import call_llm

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # e.g. "username/launchmind-geo"
AUTHOR_NAME = "EngineerAgent"
AUTHOR_EMAIL = "agent@launchmind.ai"

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


class EngineerAgent:
    def __init__(self):
        self._branch: str = ""
        self._file_sha: str = ""
        self._pr_number: int = 0
        self._pr_url: str = ""

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def run(self) -> None:
        print("\n[ENGINEER] Starting build pipeline...")

        task_msg = get_latest_message_for("engineer", "task")
        if not task_msg:
            print("  [ENGINEER] No task found!")
            return

        spec = task_msg["payload"].get("product_spec", {})
        html = self._generate_html(spec)

        base_sha = self._get_default_branch_sha()
        self._branch = f"agent/landing-page-{int(time.time())}"
        self._create_branch(base_sha)
        self._file_sha = self._commit_file(html, "Add GeoRank landing page via EngineerAgent")
        issue_url = self._create_issue(spec)
        pr_url, pr_number = self._open_pr(spec)
        self._pr_url = pr_url
        self._pr_number = pr_number

        send_message(
            from_agent="engineer",
            to_agent="ceo",
            message_type="result",
            payload={
                "pr_url": pr_url,
                "pr_number": pr_number,
                "issue_url": issue_url,
                "branch": self._branch,
                "html_snippet": html[:600] + "...",
            },
            parent_message_id=task_msg["message_id"],
        )
        print(f"  [ENGINEER] Done. PR: {pr_url}")

    def revise(self) -> None:
        print("\n[ENGINEER] Revising landing page based on QA feedback...")

        revision_msgs = [
            m for m in get_messages_for("engineer")
            if m["message_type"] == "revision_request"
        ]
        if not revision_msgs:
            print("  [ENGINEER] No revision request found.")
            return

        revision = revision_msgs[-1]
        feedback = revision["payload"].get("feedback", "")
        issues = revision["payload"].get("issues", [])
        print(f"  [ENGINEER] Feedback: {feedback[:120]}...")

        # Get the original spec
        task_msg = get_latest_message_for("engineer", "task")
        spec = task_msg["payload"].get("product_spec", {}) if task_msg else {}

        revised_html = self._generate_html(spec, revision_feedback=feedback, issues=issues)
        self._file_sha = self._commit_file(
            revised_html,
            "Revise landing page addressing QA feedback (EngineerAgent)",
        )

        send_message(
            from_agent="engineer",
            to_agent="ceo",
            message_type="result",
            payload={
                "pr_url": self._pr_url,
                "pr_number": self._pr_number,
                "branch": self._branch,
                "html_snippet": revised_html[:600] + "...",
                "revision": True,
            },
            parent_message_id=revision["message_id"],
        )
        print(f"  [ENGINEER] Revision committed to branch {self._branch}")

    # ------------------------------------------------------------------
    # LLM — Generate HTML
    # ------------------------------------------------------------------
    def _generate_html(
        self, spec: dict, revision_feedback: str = "", issues: list = None
    ) -> str:
        vp = spec.get("value_proposition", "")
        features = spec.get("features", [])
        personas = spec.get("personas", [])

        feature_list = "\n".join(
            f"- {f.get('name', '')}: {f.get('description', '')}"
            for f in features[:5]
        )
        persona_names = ", ".join(p.get("name", "") for p in personas[:3])

        revision_note = ""
        if revision_feedback:
            revision_note = f"""
REVISION REQUEST — address ALL of these issues:
{revision_feedback}
Issues list: {issues or []}
"""

        system = (
            "You are a senior frontend engineer. Write clean, complete, production-quality "
            "HTML with embedded CSS. Return ONLY the HTML — no explanation, no markdown fences."
        )
        user = f"""Build a complete single-page HTML landing page for GeoRank.

Value proposition: {vp}

Key features:
{feature_list}

Target users: {persona_names}

{revision_note}

Requirements:
1. DOCTYPE html, proper <head> with title, meta charset, viewport, embedded <style>
2. Hero section: bold headline using the value proposition, subheadline, CTA button "Start Free Trial"
3. Features section: display all 5 features as cards (3-column grid)
4. How It Works section: 3 numbered steps
5. Social proof: 2 testimonials from the personas with name, role, quote
6. Pricing teaser: "Starting at $49/month" with a CTA
7. Footer with company name GeoRank and copyright 2025
8. Color scheme: dark navy (#0D1B2A) background, electric blue (#00A8FF) accent, white text
9. Modern, professional look — no external libraries needed

Output: only the HTML file content, starting with <!DOCTYPE html>"""

        html = call_llm(system, user, max_tokens=4096)

        # Strip any accidental markdown fences
        html = re.sub(r"^```[a-z]*\n?", "", html.strip())
        html = re.sub(r"\n?```$", "", html.strip())

        print(f"  [ENGINEER] HTML generated ({len(html)} chars)")
        return html

    # ------------------------------------------------------------------
    # GitHub API helpers
    # ------------------------------------------------------------------
    def _get_default_branch_sha(self) -> str:
        url = f"{GH_API}/repos/{GITHUB_REPO}"
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        default_branch = resp.json()["default_branch"]

        ref_url = f"{GH_API}/repos/{GITHUB_REPO}/git/refs/heads/{default_branch}"
        resp = requests.get(ref_url, headers=HEADERS)
        resp.raise_for_status()
        sha = resp.json()["object"]["sha"]
        print(f"  [ENGINEER] Base SHA: {sha[:10]}... (branch: {default_branch})")
        return sha

    def _create_branch(self, base_sha: str) -> None:
        url = f"{GH_API}/repos/{GITHUB_REPO}/git/refs"
        resp = requests.post(
            url,
            headers=HEADERS,
            json={"ref": f"refs/heads/{self._branch}", "sha": base_sha},
        )
        if resp.status_code == 422:
            print(f"  [ENGINEER] Branch {self._branch} already exists — reusing")
        else:
            resp.raise_for_status()
            print(f"  [ENGINEER] Branch created: {self._branch}")

    def _commit_file(self, html: str, commit_message: str) -> str:
        """Create or update index.html on the agent branch. Returns the new file SHA."""
        url = f"{GH_API}/repos/{GITHUB_REPO}/contents/index.html"
        content_b64 = base64.b64encode(html.encode("utf-8")).decode("utf-8")

        payload = {
            "message": commit_message,
            "content": content_b64,
            "branch": self._branch,
            "committer": {"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
            "author": {"name": AUTHOR_NAME, "email": AUTHOR_EMAIL},
        }
        # If file already exists on this branch, we need its SHA to update
        if self._file_sha:
            payload["sha"] = self._file_sha

        resp = requests.put(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        file_sha = resp.json()["content"]["sha"]
        print(f"  [ENGINEER] File committed (sha: {file_sha[:10]}...)")
        return file_sha

    def _create_issue(self, spec: dict) -> str:
        system = (
            "You write concise GitHub issue descriptions. "
            "Return only the issue body text — no JSON, no fences."
        )
        vp = spec.get("value_proposition", "GeoRank landing page")
        features = spec.get("features", [])
        feature_names = ", ".join(f.get("name", "") for f in features[:5])

        user = (
            f"Write a GitHub issue description for: 'Initial landing page for GeoRank'\n"
            f"Value proposition: {vp}\n"
            f"Features to highlight: {feature_names}\n"
            f"Keep it under 150 words. Use markdown."
        )
        body = call_llm(system, user, max_tokens=300)

        url = f"{GH_API}/repos/{GITHUB_REPO}/issues"
        resp = requests.post(
            url,
            headers=HEADERS,
            json={"title": "Initial landing page", "body": body},
        )
        resp.raise_for_status()
        issue_url = resp.json()["html_url"]
        print(f"  [ENGINEER] Issue created: {issue_url}")
        return issue_url

    def _open_pr(self, spec: dict) -> tuple:
        system = (
            "You write concise GitHub pull request titles and descriptions. "
            "Return JSON with keys: title (string), body (string). No markdown fences."
        )
        vp = spec.get("value_proposition", "")
        user = (
            f"Write a PR title and body for a landing page commit.\n"
            f"Product: GeoRank — {vp}\n"
            f"Keep title under 72 chars. Body under 200 words. Use markdown in body."
        )
        raw = call_llm(system, user, max_tokens=400)
        try:
            pr_meta = _parse_json(raw)
            title = pr_meta.get("title", "feat: Add GeoRank landing page")
            body = pr_meta.get("body", "Initial landing page generated by EngineerAgent.")
        except Exception:
            title = "feat: Add GeoRank landing page"
            body = "Initial landing page generated by EngineerAgent."

        url = f"{GH_API}/repos/{GITHUB_REPO}/pulls"
        resp = requests.post(
            url,
            headers=HEADERS,
            json={
                "title": title,
                "body": body,
                "head": self._branch,
                "base": "main",
            },
        )
        if resp.status_code == 422:
            # PR already exists — find it
            search = requests.get(
                f"{GH_API}/repos/{GITHUB_REPO}/pulls",
                headers=HEADERS,
                params={"head": f"{GITHUB_REPO.split('/')[0]}:{self._branch}", "state": "open"},
            )
            prs = search.json()
            if prs:
                pr_url = prs[0]["html_url"]
                pr_number = prs[0]["number"]
                print(f"  [ENGINEER] PR already exists: {pr_url}")
                return pr_url, pr_number
        resp.raise_for_status()
        pr_url = resp.json()["html_url"]
        pr_number = resp.json()["number"]
        print(f"  [ENGINEER] PR opened: {pr_url}")
        return pr_url, pr_number
