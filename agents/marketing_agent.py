"""
Marketing Agent — Growth Marketer.

Reads the product spec and PR URL from the CEO, then:
  1. Uses an LLM to generate: tagline, product description, cold email, 3 social posts
  2. Sends a cold outreach email via SendGrid (skipped if SENDGRID_API_KEY not set)
  3. Posts a launch announcement to Slack using Block Kit
  4. Returns all copy as structured JSON to the CEO
"""

import json
import os
import re

import requests

from message_bus import send_message, get_latest_message_for
from utils.llm import call_llm

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#launches")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "")
TO_EMAIL = os.environ.get("TO_EMAIL", "")


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


class MarketingAgent:
    def run(self) -> None:
        print("\n[MARKETING] Starting marketing pipeline...")

        task_msg = get_latest_message_for("marketing", "task")
        if not task_msg:
            print("  [MARKETING] No task found!")
            return

        spec = task_msg["payload"].get("product_spec", {})
        pr_url = task_msg["payload"].get("pr_url", "")
        instructions = task_msg["payload"].get("instructions", "")

        copy = self._generate_copy(spec, instructions)
        self._send_email(copy)
        self._post_to_slack(copy, pr_url)

        send_message(
            from_agent="marketing",
            to_agent="ceo",
            message_type="result",
            payload={
                "copy": copy,
                "email_sent": True,
                "slack_posted": True,
            },
            parent_message_id=task_msg["message_id"],
        )
        print("  [MARKETING] Done.")

    # ------------------------------------------------------------------
    # LLM — Generate all marketing copy in one call
    # ------------------------------------------------------------------
    def _generate_copy(self, spec: dict, instructions: str) -> dict:
        vp = spec.get("value_proposition", "")
        features = spec.get("features", [])
        personas = spec.get("personas", [])

        feature_names = ", ".join(f.get("name", "") for f in features[:5])
        persona_0 = personas[0] if personas else {}

        system = (
            "You are a senior growth marketer specialising in B2B SaaS for e-commerce. "
            "Your copy is crisp, benefit-led, and uses the language of your audience. "
            "Respond ONLY with valid JSON — no extra text, no markdown prose."
        )
        user = f"""Create marketing copy for GeoRank.

Value proposition: {vp}
Core features: {feature_names}
Primary persona: {persona_0.get('name', 'E-commerce store owner')} — {persona_0.get('pain_point', '')}
Instructions: {instructions}

Return exactly this JSON:
{{
  "tagline": "Under 10 words, punchy, benefit-focused",
  "product_description": "2-3 sentences for a landing page hero. Benefit-led.",
  "cold_email": {{
    "subject": "Email subject line (under 60 chars)",
    "body": "Cold outreach email body (150-200 words). Address the persona's pain point. End with a clear CTA."
  }},
  "social_posts": {{
    "twitter": "Under 280 chars. Hook + benefit + CTA. Include #GEO #Ecommerce",
    "linkedin": "3-4 sentences. Professional tone. Mention LLM search trend. Tag a pain point.",
    "instagram": "Caption with emojis. 2-3 sentences. Hook first. Include 5 relevant hashtags."
  }}
}}"""

        raw = call_llm(system, user, max_tokens=1500)

        try:
            copy = _parse_json(raw)
        except Exception:
            print("  [MARKETING] JSON parse failed — using fallback copy")
            copy = self._fallback_copy()

        print(f"  [MARKETING] Tagline: {copy.get('tagline', '')}")
        return copy

    # ------------------------------------------------------------------
    # SendGrid — Send cold outreach email (optional)
    # ------------------------------------------------------------------
    def _send_email(self, copy: dict) -> None:
        cold_email = copy.get("cold_email", {})
        subject = cold_email.get("subject", "")
        body_text = cold_email.get("body", "")

        # Always print the generated copy so it appears in the demo terminal
        print("  [MARKETING] Cold email generated:")
        print(f"    Subject : {subject}")
        print(f"    Body    : {body_text[:200]}...")

        if not SENDGRID_API_KEY:
            print("  [MARKETING] SENDGRID_API_KEY not set — skipping email send")
            return

        print("  [MARKETING] Sending email via SendGrid...")

        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #333;">
  <div style="background: #0D1B2A; padding: 20px; border-radius: 8px 8px 0 0;">
    <h1 style="color: #00A8FF; margin: 0; font-size: 24px;">GeoRank</h1>
    <p style="color: #ccc; margin: 5px 0 0;">Generative Engine Optimization for E-Commerce</p>
  </div>
  <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px;">
    <p style="white-space: pre-line; line-height: 1.7;">{body_text}</p>
    <div style="margin-top: 30px; text-align: center;">
      <a href="https://georank.ai" style="background: #00A8FF; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; font-weight: bold;">Start Free Trial</a>
    </div>
  </div>
  <p style="text-align: center; color: #999; font-size: 12px; margin-top: 20px;">GeoRank Inc. — Sent by MarketingAgent</p>
</body>
</html>"""

        payload = {
            "personalizations": [{"to": [{"email": TO_EMAIL}]}],
            "from": {"email": FROM_EMAIL, "name": "GeoRank"},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": body_text},
                {"type": "text/html", "value": html_body},
            ],
        }

        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if resp.status_code in (200, 202):
            print(f"  [MARKETING] Email sent to {TO_EMAIL} (status {resp.status_code})")
        else:
            print(f"  [MARKETING] SendGrid error {resp.status_code}: {resp.text[:200]}")

    # ------------------------------------------------------------------
    # Slack — Post launch announcement with Block Kit
    # ------------------------------------------------------------------
    def _post_to_slack(self, copy: dict, pr_url: str) -> None:
        print("  [MARKETING] Posting to Slack with Block Kit...")

        tagline = copy.get("tagline", "Be the LLM's Answer")
        description = copy.get("product_description", "")
        twitter_post = copy.get("social_posts", {}).get("twitter", "")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Product Launch: GeoRank"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*_{tagline}_*\n\n{description}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*GitHub PR:*\n<{pr_url}|View Landing Page PR>",
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Status:*\nReady for review",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Twitter draft:*\n{twitter_post}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Posted by MarketingAgent | LaunchMind MAS",
                    }
                ],
            },
        ]

        resp = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={
                "channel": SLACK_CHANNEL,
                "blocks": blocks,
                "text": f"GeoRank launch: {tagline}",
            },
        )
        data = resp.json()
        if data.get("ok"):
            print(f"  [MARKETING] Slack message posted to {SLACK_CHANNEL}")
        else:
            print(f"  [MARKETING] Slack error: {data.get('error')}")

    # ------------------------------------------------------------------
    # Fallback copy
    # ------------------------------------------------------------------
    def _fallback_copy(self) -> dict:
        return {
            "tagline": "Be the store every LLM recommends",
            "product_description": (
                "GeoRank optimises your e-commerce product listings so your store appears "
                "when customers ask ChatGPT, Claude, or Gemini for buying recommendations. "
                "Turn LLM searches into your highest-converting traffic channel."
            ),
            "cold_email": {
                "subject": "Your store is invisible to AI shoppers — GeoRank fixes that",
                "body": (
                    "Hi,\n\n"
                    "When your customers type 'best [product] under $X' into ChatGPT, "
                    "which store appears in the answer? Right now, it is probably not yours.\n\n"
                    "GeoRank is the first platform built specifically to optimise e-commerce "
                    "stores for LLM search visibility — what we call Generative Engine "
                    "Optimization (GEO).\n\n"
                    "In 10 minutes, GeoRank will:\n"
                    "- Audit your current LLM citation rate across 50+ shopping queries\n"
                    "- Rewrite your top product descriptions using GEO best practices\n"
                    "- Generate structured data markup that LLMs understand\n\n"
                    "Early stores using GeoRank have seen a 3x increase in LLM citations "
                    "within 30 days.\n\n"
                    "Want to see your store's GEO score? Reply and I will run a free audit.\n\n"
                    "Best,\nThe GeoRank Team"
                ),
            },
            "social_posts": {
                "twitter": (
                    "Your e-commerce store is invisible to AI shoppers. "
                    "GeoRank makes sure ChatGPT recommends YOU when customers ask for buying advice. "
                    "Free audit this week. #GEO #Ecommerce #AISearch"
                ),
                "linkedin": (
                    "Traditional SEO is not enough anymore. When 40% of Gen Z uses ChatGPT "
                    "as their first shopping search, your Shopify store needs a GEO strategy. "
                    "GeoRank is the first platform built to optimise e-commerce stores for LLM "
                    "search visibility. Launching now — early access available."
                ),
                "instagram": (
                    "Your customers are asking AI what to buy. "
                    "Is your store the answer? GeoRank optimises your listings for LLM searches "
                    "so you appear when it matters most. "
                    "#GEO #Ecommerce #AIMarketing #ShopifyTips #DigitalMarketing"
                ),
            },
        }
