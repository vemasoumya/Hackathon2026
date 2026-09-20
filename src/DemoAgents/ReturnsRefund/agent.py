"""Returns and refunds agent backed by customer and order lookup tools."""

from __future__ import annotations

import asyncio
import logging
import sys
import warnings
from pathlib import Path

from agent_framework import (
    AgentSession,
    SelectiveToolCallCompactionStrategy,
)
from common.audit.pkg_audit import build_audit_log
from common.observability.pkg_observability import configure_observability
from coreagent.maf.common import BaseAgent
from coreagent.maf.middleware import (
    ChatTokenMetricsMiddleware,
    SecurityInjectionMiddleware,
    TokenMetricsMiddleware,
    ToolMiddleware,
)
from dotenv import load_dotenv
from agent_framework.azure import CosmosHistoryProvider
import os
from urllib3.exceptions import InsecureRequestWarning


load_dotenv()

warnings.filterwarnings(
    "ignore",
    message=r"Unverified HTTPS request is being made to host '(localhost|127\.0\.0\.1)'.*",
    category=InsecureRequestWarning,
    module=r"urllib3\.connectionpool",
)

from DemoAgents.ReturnsRefund.tools import get_customer, get_order, search_return_policy


_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.txt")

_COMPACTION_SESSION_MODE = "compact"


def _uses_compaction(session_id: str) -> bool:
    """Return whether the session ID explicitly selects compaction."""
    return session_id.rsplit("-", maxsplit=1)[-1].lower() == _COMPACTION_SESSION_MODE


class ReturnsRefundAgent(BaseAgent):
    """Help customers assess return, refund, replacement, and exchange requests."""

    def __init__(self, *, client=None, credential=None, **client_kwargs) -> None:
        configure_observability()
        logging.getLogger("azure").setLevel(logging.WARNING)
        logging.getLogger("azure.cosmos").setLevel(logging.WARNING)
        logging.getLogger("azure.core").setLevel(logging.WARNING)
        logging.getLogger("agent_framework").setLevel(logging.WARNING)
        logger = logging.getLogger(__name__)
        audit_log = build_audit_log(
            service_name="returns-refund-agent",
            logger=logger,
            credential=credential,
            max_prompt_length=100000
        )
        self._history = CosmosHistoryProvider(            
            credential=os.environ.get("COSMOS_KEY"),            
            database_name= "hackathon2026",
            container_name="return_history",
            endpoint=os.environ.get("COSMOS_ENDPOINT"),
        )

        super().__init__(
            name="returns-refund-agent",
            instructions=_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip(),
            tools=[get_customer, get_order, search_return_policy],
            context_providers=[self._history],
            # compaction_strategy=selective_tool,
            middleware=[
                SecurityInjectionMiddleware(logger),
                ToolMiddleware(logger, audit_log=audit_log),
                TokenMetricsMiddleware(logger, audit_log=audit_log),
                ChatTokenMetricsMiddleware(logger, audit_log=audit_log),
            ],
            logger=logger,
            client=client,
            client_kwargs=client_kwargs if client_kwargs else None,
            audit_log=audit_log,
        )

async def run_chat(session_id: str) -> None:
    """Run an interactive returns and refunds conversation."""
    agent_kwargs = {}
    if _uses_compaction(session_id):
        agent_kwargs["compaction_strategy"] = SelectiveToolCallCompactionStrategy(
            keep_last_tool_call_groups=2
        )

    async with ReturnsRefundAgent(**agent_kwargs) as agent:
        session = agent.create_session(session_id=session_id)
        print(f"Returns and refunds agent ready. Session: {session_id}. Type 'exit' to stop.")

        while True:
            message = input("You: ").strip()
            if message.lower() in {"exit", "quit"}:
                break
            if not message:
                continue

            result = await agent.run(message, session=session)
            print(f"Agent: {result.text}")


def main() -> None:
    """Run the agent using the optional session ID command-line argument."""
    session_id = sys.argv[1] if len(sys.argv) > 1 else "session-noncompact"
    asyncio.run(run_chat(session_id))


if __name__ == "__main__":
    main()
