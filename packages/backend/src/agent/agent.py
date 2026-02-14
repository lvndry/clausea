import json
from collections.abc import AsyncGenerator

from src.agent.tools import check_compliance, search_query
from src.core.logging import get_logger
from src.llm import acompletion_with_fallback

logger = get_logger(__name__)


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 15].rstrip() + "\n\n[... truncated ...]"


# RAG context budgeting: prefer fewer, higher-signal excerpts with enough surrounding text
# to capture definitions/exceptions common in legal clauses.
MAX_TOOL_SOURCES = 12
EXCERPT_CHARS_FEW_SOURCES = 1800
EXCERPT_CHARS_MANY_SOURCES = 1200


class Agent:
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt

    async def chat(
        self, messages: list[dict[str, str]], product_slug: str
    ) -> AsyncGenerator[str, None]:
        """
        Run the agent loop:
        1. Check if tool use is needed (non-streaming).
        2. If tool needed, execute and recurse.
        3. If no tool needed, stream the response.
        """
        # Ensure system prompt is at the start
        if not messages or messages[0]["role"] != "system":
            messages = [{"role": "system", "content": self.system_prompt}] + messages

        # Define tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_query",
                    "description": "Search for information in the product's legal documents.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query to find relevant information.",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_compliance",
                    "description": "Check if the product's documents comply with a specific regulation (e.g. GDPR, CCPA).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "regulation": {
                                "type": "string",
                                "description": "The regulation to check (e.g. 'GDPR', 'CCPA').",
                            },
                        },
                        "required": ["regulation"],
                    },
                },
            },
        ]

        # Step 1: Decide on action (Tool vs Answer)
        try:
            response = await acompletion_with_fallback(
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except Exception as e:
            logger.error(f"Agent error in decision step: {e}")
            yield "I encountered an error while processing your request."
            return

        choice = response.choices[0]
        if not hasattr(choice, "message"):
            raise ValueError("Unexpected response format: missing message attribute")
        message = choice.message  # type: ignore[attr-defined]
        if not message:
            raise ValueError("Unexpected response format: message is None")
        tool_calls = message.tool_calls  # type: ignore[attr-defined]

        # Step 2: Handle Tool Calls
        if tool_calls:
            logger.info(f"Agent decided to use tools: {len(tool_calls)} calls")

            # Add the assistant's tool call message to history
            messages.append(message.model_dump())  # type: ignore[attr-defined]

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                if function_name == "search_query":
                    query = function_args.get("query")
                    logger.info(f"Executing search_query: {query}")

                    # Yield a status update to the user (optional, but good for UX)
                    # yield f"Searching for: {query}...\n\n"

                    try:
                        # Execute tool
                        search_results = await search_query(query, product_slug)

                        # Format results for the model
                        if not search_results.get("matches"):
                            content = "No relevant information found."
                        else:
                            chunks = []
                            # Hard cap to keep prompts token-efficient, while giving enough room
                            # for legal definitions/exceptions (adaptive excerpt sizing).
                            matches = (search_results.get("matches") or [])[:MAX_TOOL_SOURCES]
                            max_chars = (
                                EXCERPT_CHARS_FEW_SOURCES
                                if len(matches) <= 3
                                else EXCERPT_CHARS_MANY_SOURCES
                            )
                            for i, match in enumerate(matches, start=1):
                                md = match.get("metadata", {}) or {}
                                url = md.get("url", "Unknown")
                                doc_type = md.get("document_type", "Unknown")
                                start = md.get("chunk_start", "")
                                end = md.get("chunk_end", "")
                                excerpt = _truncate(
                                    str(md.get("chunk_text", "") or ""), max_chars=max_chars
                                )
                                chunks.append(
                                    f"SOURCE[{i}] url={url} type={doc_type} chars={start}-{end}\n"
                                    f"excerpt:\n{excerpt}"
                                )
                            content = "\n\n---\n\n".join(chunks)

                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        content = f"Error executing search: {str(e)}"

                elif function_name == "check_compliance":
                    regulation = function_args.get("regulation")
                    logger.info(f"Executing check_compliance: {regulation}")

                    try:
                        assessment = await check_compliance(regulation, product_slug)
                        content = assessment
                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        content = f"Error checking compliance: {str(e)}"

                else:
                    content = "Unknown tool."

                # Add tool result to history
                messages.append(  # type: ignore[arg-type]
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": content,
                    }
                )

            # Step 3: Recurse (Stream the final answer based on tool outputs)
            # We call chat again (or just stream from here).
            # Calling chat again allows for multi-step reasoning (e.g. search -> not found -> search again).
            # But for "super fast", let's just stream the answer now.
            # Actually, let's allow one level of recursion for now to keep it simple but "agentic".
            # To support true multi-step, we'd loop. Let's do a simple loop.
            async for chunk in self._stream_response(messages):
                yield chunk

        else:
            # No tool call, just stream the response
            # We need to stream the content from the *current* response if it has content,
            # but we used a non-streaming call. So we just yield the content.
            # OR, we can make a second streaming call to get the token-by-token effect.
            # Since the user wants "streaming", re-generating with stream=True is better UX
            # than dumping a block of text, even if it costs a bit more latency/tokens.
            # Optimization: If the first response already has content, we could just yield it.
            # But for consistency, let's stream.
            if message.content:  # type: ignore[attr-defined]
                yield message.content  # type: ignore[attr-defined]
            else:
                # This shouldn't happen if no tools and no content, but just in case
                async for chunk in self._stream_response(messages):
                    yield chunk

    async def _stream_response(self, messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
        """Helper to stream the final response."""
        logger.debug(f"Streaming response with messages: {json.dumps(messages, default=str)}")
        try:
            response = await acompletion_with_fallback(
                messages=messages,
                stream=True,
            )

            async for chunk in response:  # type: ignore[union-attr]
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            yield "I encountered an error while generating the response."
