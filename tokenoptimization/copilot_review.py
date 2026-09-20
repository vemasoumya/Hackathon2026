"""Advisory token-optimization suggestions via the GitHub Copilot SDK.

Given one run's token profile and the ReturnsRefund source, this module asks the
Copilot agent to propose instruction rewrites and code changes that reduce token
usage without changing behavior. It is advisory only: every tool request is denied,
so the agent answers purely from the source embedded in the prompt and never edits
files on disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_APP_DIR = Path(__file__).resolve().parents[1] / "ReturnsRefund"
_SOURCE_FILES = ("agent.py", "tools.py", "instructions.txt")
_DEFAULT_MODEL = os.getenv("COPILOT_MODEL", "gpt-5.4")
_TIMEOUT_SECONDS = float(os.getenv("COPILOT_REVIEW_TIMEOUT", "240"))


def _read_sources() -> str:
    """Read the ReturnsRefund source files the review reasons about."""
    parts: list[str] = []
    for name in _SOURCE_FILES:
        path = _APP_DIR / name
        if path.exists():
            parts.append(f"=== {name} ===\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first balanced top-level JSON object from a model response."""
    start = text.find("{")
    if start == -1:
        return {"summary": text.strip(), "items": []}
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    break
    return {"summary": text.strip(), "items": []}


def _build_prompt(run: dict[str, Any], sources: str) -> str:
    """Build the review prompt from a run's token profile and the agent source."""
    token_lines = "\n".join(
        f"- {c['component']}: {c['context_tokens']} tokens "
        f"(context_share {c['context_share']}, output_value {c.get('output_share')})"
        for c in run["components"]
    )
    return (
        "You are a token-optimization and code-review assistant for an AI agent.\n"
        "Do not use any tools or edit files; answer only from the source below.\n\n"
        "GOAL: reduce the tokens spent per run on the returns-refund agent WITHOUT\n"
        "changing its decisions or removing security boundaries. Components with high\n"
        "token cost but low output_value are the best optimization targets.\n\n"
        f"RUN TOKEN PROFILE (model {run.get('model', 'unknown')}, "
        f"{run.get('num_llm_calls')} LLM call(s)):\n{token_lines}\n"
        f"final_output tokens (estimated): {run['final_output_tokens_estimated']}\n"
        f"billed input tokens (all calls): {run['billed_input_tokens_total']}\n"
        f"final decision: {run.get('final_decision')}\n\n"
        "AGENT SOURCE:\n"
        f"{sources}\n\n"
        "Respond with ONE JSON object and nothing else, using this shape:\n"
        "{\n"
        '  "summary": "one paragraph on where tokens go and the biggest wins",\n'
        '  "items": [\n'
        "    {\n"
        '      "target": "instructions|tool_definitions|tool_results|history|code",\n'
        '      "title": "short action title",\n'
        '      "recommendation": "what to change and why it is safe",\n'
        '      "estimated_token_savings": "approximate per-run tokens saved",\n'
        '      "severity": "high|medium|low",\n'
        '      "change": "concrete instruction rewrite or code snippet (optional)"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )


async def review_run(run: dict[str, Any], *, model: str = _DEFAULT_MODEL) -> dict[str, Any]:
    """Ask the Copilot SDK for advisory optimization suggestions for one run."""
    from copilot import CopilotClient
    from copilot.rpc import PermissionDecisionReject
    from copilot.session import PermissionRequest, PermissionRequestResult

    def deny_all(request: PermissionRequest, invocation: dict) -> PermissionRequestResult:
        return PermissionDecisionReject(
            feedback="Advisory review only: tool use is disabled; answer from the provided source."
        )

    prompt = _build_prompt(run, _read_sources())
    client = CopilotClient()
    async with client:
        session = await client.create_session(
            on_permission_request=deny_all,
            model=model,
        )
        try:
            response = await session.send_and_wait(prompt, timeout=_TIMEOUT_SECONDS)
        finally:
            # Older local Copilot CLI builds do not support the session cleanup
            # RPC used by newer SDKs. The client process is still shut down below.
            client._sessions.pop(session.session_id, None)

    if response is None:
        return {"summary": "No Copilot review response was returned.", "items": []}

    content = getattr(getattr(response, "data", None), "content", "") or ""
    if not content:
        return {"summary": "Copilot returned an empty review response.", "items": []}
    return _extract_json(content)


async def review_records(records: list[dict[str, Any]], *, model: str = _DEFAULT_MODEL) -> None:
    """Attach a ``suggestions`` object to each run record in place."""
    for record in records:
        record["suggestions"] = await review_run(record, model=model)
