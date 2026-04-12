"""
LLM utility — wrapper around the OpenAI SDK.
CEO and QA use gpt-4o for complex reasoning and review.
Product, Engineer, and Marketing use gpt-4o-mini for speed.
"""

import os
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def call_llm(system_prompt: str, user_prompt: str, max_tokens: int = 2048) -> str:
    """Fast model (gpt-4o-mini) — used by Product, Engineer, and Marketing agents."""
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def call_llm_smart(system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> str:
    """Smarter model (gpt-4o) — used by CEO and QA for reasoning and decisions."""
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content
