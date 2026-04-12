"""
LaunchMind — GeoRank Startup Pipeline
======================================
Entry point. Run this to launch the full 5-agent MAS.

  python main.py

The system will:
  1. CEO decomposes the startup idea (LLM call)
  2. Product agent generates a product spec
  3. CEO reviews spec — sends revision if needed (LLM call — FEEDBACK LOOP 1)
  4. Engineer agent commits HTML landing page & opens GitHub PR
  5. Marketing agent sends email + posts to Slack
  6. QA agent reviews outputs & posts GitHub PR comments
  7. CEO reviews QA verdict — sends revision if needed (FEEDBACK LOOP 2)
  8. CEO posts final launch summary to Slack
"""

import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Validate required environment variables before importing agents
REQUIRED_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_REPO",
    "SLACK_BOT_TOKEN",
    "SLACK_CHANNEL",
    "SENDGRID_API_KEY",
    "FROM_EMAIL",
    "TO_EMAIL",
]

def check_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        print("ERROR: Missing required environment variables:")
        for v in missing:
            print(f"  - {v}")
        print("\nCopy .env.example to .env and fill in your credentials.")
        sys.exit(1)

check_env()

from message_bus import clear_bus, get_all_messages
from agents.ceo_agent import CEOAgent
from agents.product_agent import ProductAgent
from agents.engineer_agent import EngineerAgent
from agents.marketing_agent import MarketingAgent
from agents.qa_agent import QAAgent


STARTUP_IDEA = """
GeoRank: A Generative Engine Optimization (GEO) platform for e-commerce store owners.

When a customer asks ChatGPT "What is the best running shoe under $100?" or asks Claude
"Where can I buy organic coffee online?", GeoRank ensures YOUR store is the answer.

GeoRank analyses how LLMs (ChatGPT, Claude, Gemini, Perplexity) discover and cite
e-commerce stores, then automatically optimises product descriptions, metadata, and
structured data so the store appears prominently in LLM-generated shopping recommendations.

Target users: Shopify/WooCommerce store owners, DTC brands, and e-commerce SEO consultants
who want to capture the growing wave of AI-assisted shopping.

Monetisation: SaaS subscription ($49/month Starter, $199/month Pro) with a free audit tier.
"""


def print_banner() -> None:
    print("=" * 60)
    print("  LaunchMind — Multi-Agent Startup System")
    print("  Startup: GeoRank (GEO for E-Commerce)")
    print("=" * 60)
    print()


def print_message_log() -> None:
    messages = get_all_messages()
    print("\n" + "=" * 60)
    print("  FULL MESSAGE BUS LOG")
    print("=" * 60)
    for msg in messages:
        print(
            f"\n  [{msg['timestamp'][:19]}] "
            f"{msg['from_agent'].upper()} -> {msg['to_agent'].upper()} "
            f"[{msg['message_type']}]"
        )
        payload_preview = json.dumps(msg["payload"])[:120]
        print(f"  Payload: {payload_preview}...")
    print("=" * 60)


def main() -> None:
    print_banner()

    # ------------------------------------------------------------------
    # Initialise agents
    # ------------------------------------------------------------------
    ceo = CEOAgent()
    product = ProductAgent()
    engineer = EngineerAgent()
    marketing = MarketingAgent()
    qa = QAAgent()

    # ------------------------------------------------------------------
    # Clear message bus for fresh run
    # ------------------------------------------------------------------
    clear_bus()

    # ------------------------------------------------------------------
    # PHASE 1: CEO decomposes idea → tasks Product agent
    # ------------------------------------------------------------------
    print("\n>>> PHASE 1: Idea decomposition")
    ceo.decompose_idea(STARTUP_IDEA)

    # ------------------------------------------------------------------
    # PHASE 2: Product agent generates spec
    # ------------------------------------------------------------------
    print("\n>>> PHASE 2: Product specification")
    product.run()

    # ------------------------------------------------------------------
    # PHASE 3: CEO reviews spec (FEEDBACK LOOP 1)
    # ------------------------------------------------------------------
    print("\n>>> PHASE 3: CEO review + feedback loop")
    spec_approved = ceo.review_product_output()

    if not spec_approved:
        print("\n  [MAIN] CEO requested revision — Product agent revising...")
        product.revise()
        ceo.accept_revised_product()
    # ------------------------------------------------------------------
    # PHASE 4: CEO tasks Engineer
    # ------------------------------------------------------------------
    print("\n>>> PHASE 4: Engineer — build & push to GitHub")
    ceo.task_engineer()
    engineer.run()
    ceo.collect_engineer_result()

    # ------------------------------------------------------------------
    # PHASE 5: CEO tasks Marketing (now has PR URL)
    # ------------------------------------------------------------------
    print("\n>>> PHASE 5: Marketing — email + Slack")
    ceo.task_marketing()
    marketing.run()
    ceo.collect_marketing_result()

    # ------------------------------------------------------------------
    # PHASE 6: QA review
    # ------------------------------------------------------------------
    print("\n>>> PHASE 6: QA review")
    ceo.task_qa()
    qa.run()

    # ------------------------------------------------------------------
    # PHASE 7: CEO reviews QA verdict (FEEDBACK LOOP 2)
    # ------------------------------------------------------------------
    print("\n>>> PHASE 7: CEO reviews QA verdict + feedback loop")
    qa_passed = ceo.review_qa_verdict()

    if not qa_passed:
        print("\n  [MAIN] QA failed — Engineer revising...")
        engineer.revise()
        ceo.collect_revised_engineer_result()

    # ------------------------------------------------------------------
    # PHASE 8: CEO posts final Slack summary
    # ------------------------------------------------------------------
    print("\n>>> PHASE 8: Final Slack summary")
    ceo.post_final_summary()

    # ------------------------------------------------------------------
    # Done — print decision log and message history
    # ------------------------------------------------------------------
    ceo.print_decision_log()
    print_message_log()

    print("\n" + "=" * 60)
    print("  LAUNCHMIND PIPELINE COMPLETE")
    print(f"  GitHub PR: {ceo.pr_url}")
    print(f"  GitHub Issue: {ceo.issue_url}")
    print("  Check your Slack #launches channel and email inbox!")
    print("=" * 60)


if __name__ == "__main__":
    main()
