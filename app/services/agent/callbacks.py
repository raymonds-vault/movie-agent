"""
LangChain streaming callbacks for logging and monitoring.
"""

from langchain_core.callbacks import AsyncCallbackHandler
from app.core.logging import get_logger

logger = get_logger(__name__)


class AgentLoggingCallback(AsyncCallbackHandler):
    """Logs agent actions and tool invocations for observability."""

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:
        tool_name = serialized.get("name", "unknown")
        logger.info(f"🔧 Tool invoked: {tool_name} | Input: {input_str[:200]}")

    async def on_tool_end(self, output: str, **kwargs) -> None:
        logger.info(f"✅ Tool completed | Output length: {len(output)} chars")

    async def on_tool_error(self, error: BaseException, **kwargs) -> None:
        logger.error(f"❌ Tool error: {error}")

    async def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs) -> None:
        logger.debug(f"🤖 LLM call started")

    async def on_llm_end(self, response, **kwargs) -> None:
        logger.debug(f"🤖 LLM call completed")
