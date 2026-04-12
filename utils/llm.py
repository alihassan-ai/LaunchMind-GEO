"""
LLM utility — thin wrapper around the Anthropic SDK.
CEO and QA use the smarter Sonnet model for complex reasoning.
Product, Engineer, and Marketing use Haiku for speed.
"""

import os
import anthropic

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Fast model — used by Product, Engineer, and Marketing agents."""
    client = _get_client()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def call_llm_smart(system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> str:
    """Smarter model — used by CEO and QA for reasoning, review, and decisions."""
    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text
