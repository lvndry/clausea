"""Agentic Q&A for Clausea — multi-round reasoning over policy documents.

The agent loop:
  1. Ask the model: answer directly or use tools?
  2. If tools: execute all calls in parallel, append results, go to 1.
  3. Repeat up to MAX_TOOL_ROUNDS; force a streamed answer if the limit is hit.
  4. Stream the final answer.

Entry points (module-level, replacing the deleted rag.py):
  get_answer_stream(question, product_slug)  — async generator of text chunks
  get_answer(question, product_slug)         — non-streaming convenience wrapper
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from src.agent.tools import analyze_policy_documents, format_matches_for_context, search_query
from src.core.logging import get_logger
from src.llm import acompletion_with_fallback
from src.prompts.agent_prompts import AGENT_SYSTEM_PROMPT

logger = get_logger(__name__)

# Maximum tool-use rounds before forcing a final answer.
# Prevents runaway loops while allowing genuine multi-step reasoning.
MAX_TOOL_ROUNDS = 5

# Maximum search results shown to the model per search_query call.
# search_query defaults to top_k=8 so this just applies a safety ceiling.
MAX_SEARCH_SOURCES = 8

# Tool definitions at module level — built once, reused across all Agent instances.
_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_query",
            "description": (
                "Search the product's policy documents for sections relevant to the user's question. "
                "Use a specific, targeted query — prefer exact terms over vague ones. "
                "Call multiple times with different queries if the first result is insufficient "
                "or if the question covers multiple topics (e.g. data collection AND data sharing). "
                "Always call this before making any factual claim about the organization's documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Specific search query. Good: 'precise GPS location sharing with advertisers'. "
                            "Bad: 'data'. Use the same terminology the policy would use."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_policy_documents",
            "description": (
                "Summarize what privacy-conscious users are agreeing to: practical implications, risks, "
                "notable or surprising clauses, rights described in the text, and gaps. "
                "Use when the user wants the big picture, worries about data use, or asks what the terms "
                "or privacy policy means for them. "
                "Optional regulation_context adds plain-language comparison to what people often expect "
                "in notices (educational — not a compliance verdict). "
                "Do NOT use for narrow factual lookups — use search_query instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": (
                            "Optional user angle (e.g. 'location data', 'account deletion', 'cookies', "
                            "'selling my data'). Omit for a full-document-style overview."
                        ),
                    },
                    "regulation_context": {
                        "type": "string",
                        "description": (
                            "Optional regulation name (e.g. GDPR, CCPA) when the user wants that lens. "
                            "Produces educational comparison only — never claim legal compliance."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]


async def _execute_tool(tool_call: Any, product_slug: str) -> str:
    """Execute a single tool call and return its string output."""
    function_name = tool_call.function.name

    try:
        function_args = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError) as e:
        return f"Error: could not parse tool arguments — {e}"

    if function_name == "search_query":
        query = function_args.get("query", "").strip()
        if not query:
            return "Error: search_query requires a non-empty query string."
        try:
            results = await search_query(query, product_slug)
            matches = (results.get("matches") or [])[:MAX_SEARCH_SOURCES]
            if not matches:
                return "No relevant information found for this query. Try a different or more specific query."
            return format_matches_for_context(matches, max_chars=1800)
        except Exception as e:
            logger.error(f"search_query failed for '{query}': {e}")
            return f"Search failed: {e}"

    if function_name == "analyze_policy_documents":
        focus = (function_args.get("focus") or "").strip() or None
        regulation_context = (function_args.get("regulation_context") or "").strip() or None
        try:
            return await analyze_policy_documents(
                product_slug,
                focus=focus,
                regulation_context=regulation_context,
            )
        except Exception as e:
            logger.error(f"analyze_policy_documents failed: {e}")
            return f"Policy analysis failed: {e}"

    return f"Error: unknown tool '{function_name}'."


class Agent:
    def __init__(self, system_prompt: str = AGENT_SYSTEM_PROMPT):
        self.system_prompt = system_prompt

    async def chat(
        self, messages: list[dict[str, Any]], product_slug: str
    ) -> AsyncGenerator[str, None]:
        """Run the agentic loop and stream the final answer."""
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": self.system_prompt}] + list(messages)
        else:
            messages = list(messages)

        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = await acompletion_with_fallback(
                    messages=messages,
                    tools=_TOOLS,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.error(f"Agent decision step failed (round {round_num + 1}): {e}")
                yield "I encountered an error while processing your request."
                return

            message = response.choices[0].message  # type: ignore[attr-defined]
            tool_calls = message.tool_calls  # type: ignore[attr-defined]

            if not tool_calls:
                # Model chose to answer directly — stream or yield the content.
                if message.content:  # type: ignore[attr-defined]
                    yield message.content  # type: ignore[attr-defined]
                else:
                    async for chunk in self._stream_response(messages):
                        yield chunk
                return

            logger.info(
                f"Agent round {round_num + 1}/{MAX_TOOL_ROUNDS}: "
                + ", ".join(
                    f"{tc.function.name}({tc.function.arguments[:80].rstrip()})"
                    for tc in tool_calls
                )
            )

            # Record the assistant's tool-call decision.
            messages.append(message.model_dump())  # type: ignore[attr-defined]

            # Execute all tool calls in this round in parallel.
            outputs = await asyncio.gather(*[_execute_tool(tc, product_slug) for tc in tool_calls])

            for tc, output in zip(tool_calls, outputs, strict=True):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": output,
                    }
                )

        # Reached MAX_TOOL_ROUNDS without a final answer — force one.
        logger.warning(
            f"Agent reached MAX_TOOL_ROUNDS ({MAX_TOOL_ROUNDS}) for product '{product_slug}'. "
            "Forcing final streamed answer."
        )
        async for chunk in self._stream_response(messages):
            yield chunk

    async def _stream_response(self, messages: list[dict[str, Any]]) -> AsyncGenerator[str, None]:
        try:
            response = await acompletion_with_fallback(messages=messages, stream=True)
            async for chunk in response:  # type: ignore[union-attr]
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Streaming response failed: {e}")
            yield "I encountered an error while generating the response."


async def get_answer_stream(
    question: str, product_slug: str, *, namespace: str | None = None
) -> AsyncGenerator[str, None]:
    """Stream an answer to a question about a product's policy documents."""
    agent = Agent()
    async for chunk in agent.chat([{"role": "user", "content": question}], product_slug):
        yield chunk


async def get_answer(question: str, product_slug: str, *, namespace: str | None = None) -> str:
    """Return a complete answer to a question about a product's policy documents."""
    chunks: list[str] = []
    async for chunk in get_answer_stream(question, product_slug, namespace=namespace):
        chunks.append(chunk)
    return "".join(chunks)
