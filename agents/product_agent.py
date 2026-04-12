"""
Product Agent — Product Manager.

Reads a task from the CEO, uses an LLM to generate a structured product specification
for GeoRank, and sends it back. Supports revision cycles.
"""

import json
import re

from message_bus import send_message, get_latest_message_for, get_messages_for
from utils.llm import call_llm


def _parse_json(text: str) -> dict:
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if match:
        text = match.group(1).strip()
    match = re.search(r"\{[\s\S]+\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


class ProductAgent:
    def run(self) -> None:
        print("\n[PRODUCT] Generating product specification...")

        task_msg = get_latest_message_for("product", "task")
        if not task_msg:
            print("  [PRODUCT] No task found!")
            return

        idea = task_msg["payload"].get("idea", "")
        instructions = task_msg["payload"].get("instructions", "")

        spec = self._generate_spec(idea, instructions)
        self._send_result(spec, task_msg["message_id"])

    def revise(self) -> None:
        print("\n[PRODUCT] Revising product specification based on CEO feedback...")

        revision_msgs = [
            m for m in get_messages_for("product")
            if m["message_type"] == "revision_request"
        ]
        if not revision_msgs:
            print("  [PRODUCT] No revision request found.")
            return

        revision = revision_msgs[-1]
        feedback = revision["payload"].get("feedback", "")
        reasoning = revision["payload"].get("reasoning", "")

        # Get the original task for context
        task_msg = get_latest_message_for("product", "task")
        idea = task_msg["payload"].get("idea", "") if task_msg else ""

        print(f"  [PRODUCT] CEO feedback: {feedback[:120]}...")

        spec = self._generate_spec(idea, feedback, is_revision=True, reasoning=reasoning)
        self._send_result(spec, revision["message_id"])

    def _generate_spec(
        self, idea: str, instructions: str, is_revision: bool = False, reasoning: str = ""
    ) -> dict:
        system = (
            "You are a world-class product manager specialising in AI-powered SaaS tools "
            "for e-commerce. Your job is to create precise, actionable product specifications. "
            "Respond ONLY with valid JSON — no extra text, no markdown prose."
        )

        revision_note = ""
        if is_revision:
            revision_note = f"""
REVISION REQUEST from CEO:
Reason for revision: {reasoning}
Specific improvements needed: {instructions}

Address ALL points above in your revised spec.
"""

        user = f"""Startup idea:
{idea}

CEO instructions: {instructions}
{revision_note}

Produce a complete product specification for GeoRank (the GEO platform) as JSON:

{{
  "value_proposition": "One sentence: what GeoRank does and for whom",
  "personas": [
    {{"name": "...", "role": "...", "pain_point": "..."}},
    {{"name": "...", "role": "...", "pain_point": "..."}},
    {{"name": "...", "role": "...", "pain_point": "..."}}
  ],
  "features": [
    {{"name": "...", "description": "...", "priority": 1}},
    {{"name": "...", "description": "...", "priority": 2}},
    {{"name": "...", "description": "...", "priority": 3}},
    {{"name": "...", "description": "...", "priority": 4}},
    {{"name": "...", "description": "...", "priority": 5}}
  ],
  "user_stories": [
    {{"as_a": "...", "i_want": "...", "so_that": "..."}},
    {{"as_a": "...", "i_want": "...", "so_that": "..."}},
    {{"as_a": "...", "i_want": "...", "so_that": "..."}}
  ]
}}

Rules:
- value_proposition must mention LLM search / generative engine optimization
- personas must be specific e-commerce roles (e.g. Shopify store owner, DTC brand CMO)
- features must be GEO-specific (e.g. LLM citation analysis, schema markup generator)
- user stories must be actionable and product-specific"""

        raw = call_llm(system, user, max_tokens=2500)

        try:
            spec = _parse_json(raw)
        except (json.JSONDecodeError, AttributeError):
            print("  [PRODUCT] JSON parse failed — using fallback spec")
            spec = self._fallback_spec()

        print(f"  [PRODUCT] Spec generated: {spec.get('value_proposition', '')[:100]}...")
        return spec

    def _send_result(self, spec: dict, parent_id: str) -> None:
        send_message(
            from_agent="product",
            to_agent="ceo",
            message_type="result",
            payload={
                "product_spec": spec,
                "status": "complete",
            },
            parent_message_id=parent_id,
        )

    def _fallback_spec(self) -> dict:
        return {
            "value_proposition": (
                "GeoRank helps e-commerce store owners optimise their product listings "
                "and content so their store appears as the answer when customers ask LLMs "
                "like ChatGPT or Claude for buying recommendations."
            ),
            "personas": [
                {
                    "name": "Sarah Chen",
                    "role": "Shopify store owner (fashion)",
                    "pain_point": (
                        "Her products never appear when shoppers ask ChatGPT "
                        "'best sustainable clothing brands under $50'"
                    ),
                },
                {
                    "name": "Marcus Webb",
                    "role": "DTC brand CMO",
                    "pain_point": (
                        "Cannot measure or optimise how often the brand "
                        "is cited in LLM responses compared to competitors."
                    ),
                },
                {
                    "name": "Priya Nair",
                    "role": "E-commerce SEO consultant",
                    "pain_point": (
                        "Traditional SEO tactics do not translate to LLM visibility; "
                        "needs a new playbook for her clients."
                    ),
                },
            ],
            "features": [
                {
                    "name": "LLM Citation Tracker",
                    "description": (
                        "Monitors how often your store is cited across major LLMs "
                        "for target queries and tracks ranking changes over time."
                    ),
                    "priority": 1,
                },
                {
                    "name": "GEO Content Optimiser",
                    "description": (
                        "Rewrites product descriptions using patterns that LLMs "
                        "prefer to cite: structured facts, authority signals, specificity."
                    ),
                    "priority": 2,
                },
                {
                    "name": "Schema Markup Generator",
                    "description": (
                        "Auto-generates JSON-LD structured data for products, "
                        "reviews, and FAQs to improve LLM comprehension."
                    ),
                    "priority": 3,
                },
                {
                    "name": "Competitor GEO Audit",
                    "description": (
                        "Shows which competitor stores appear in LLM answers "
                        "for your target queries and why."
                    ),
                    "priority": 4,
                },
                {
                    "name": "GEO Score Dashboard",
                    "description": (
                        "A single score (0-100) quantifying your store's overall "
                        "LLM visibility, with weekly trend and recommendations."
                    ),
                    "priority": 5,
                },
            ],
            "user_stories": [
                {
                    "as_a": "Shopify store owner",
                    "i_want": (
                        "to see which of my product pages are being cited by ChatGPT "
                        "for relevant shopping queries"
                    ),
                    "so_that": (
                        "I can prioritise optimising the pages with the highest "
                        "LLM traffic potential"
                    ),
                },
                {
                    "as_a": "DTC brand CMO",
                    "i_want": (
                        "GeoRank to automatically rewrite my product descriptions "
                        "using GEO best practices"
                    ),
                    "so_that": (
                        "my team spends zero time on manual GEO copywriting "
                        "and still sees measurable citation improvements"
                    ),
                },
                {
                    "as_a": "SEO consultant",
                    "i_want": (
                        "a competitor GEO audit that shows exactly why rival stores "
                        "rank higher in LLM responses"
                    ),
                    "so_that": (
                        "I can build a targeted GEO strategy for my client "
                        "within the first week of engagement"
                    ),
                },
            ],
        }
