"""Context value auditor agent and multi-pass aggregation.

Given the assembled context of one agent run (all LLM calls folded into
components) plus the final output, this agent estimates how much each part
(instructions, user input, history, tool definitions, tool results)
contributed to the outcome. Run it multiple times to measure stability.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import statistics
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

from agent_framework.openai import OpenAIChatClient
from coreagent.maf.common import BaseAgent
from dotenv import load_dotenv
from urllib3.exceptions import InsecureRequestWarning

from DemoAgents.ContextValueAuditor.cosmos_source import (
    build_context_records,
    build_output_record,
    bundle_from_run,
    read_session_runs,
    write_context_records,
    write_output_records,
)
from DemoAgents.ContextValueAuditor.normalizer import (
    bundle_to_judge_text,
)
from DemoAgents.ContextValueAuditor.schema import (
    AggregatedReport,
    ComponentScore,
    ComponentStability,
    ContextBundle,
    ContributionReport,
)

load_dotenv()

warnings.filterwarnings(
    "ignore",
    message=r"Unverified HTTPS request is being made to host '(localhost|127\.0\.0\.1)'.*",
    category=InsecureRequestWarning,
    module=r"urllib3\.connectionpool",
)

_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.txt")
_ALL_COMPONENTS = (
    "instructions",
    "user_input",
    "tool_definitions",
    "tool_results",
    "assistant-tools",
    "history-user",
    "history-tool-results",
    "history-assistant-responses",
    "history-assistant-tools",
)


class ContextValueAuditorAgent(BaseAgent):
    """Judge that scores per-component contribution for a single agent run."""

    def __init__(self, *, client=None, **client_kwargs) -> None:
        logger = logging.getLogger(__name__)
        if client is None:
            api_key = os.getenv("AZURE_AI_FOUNDRY_API_KEY")
            project_endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
            model = os.getenv("FOUNDRY_MODEL") or os.getenv("FOUNDRY_MODEL_DEPLOYMENT_NAME")
            if api_key and project_endpoint and model:
                client = OpenAIChatClient(
                    api_key=api_key,
                    base_url=f"{project_endpoint.rstrip('/')}/openai/v1",
                    model=model,
                )
        super().__init__(
            name="context-value-auditor",
            instructions=_INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip(),
            logger=logger,
            client=client,
            client_kwargs=client_kwargs or None,
        )


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first top-level JSON object from the model response."""
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in auditor response.")
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
                return json.loads(text[start : index + 1])
    raise ValueError("Unbalanced JSON object in auditor response.")


def _normalize_output_shares(components: list[ComponentScore]) -> None:
    """Assign output_share by normalizing positive output contributions."""
    weights = [max(c.output_contribution, 0.0) for c in components]
    total = sum(weights)
    for component, weight in zip(components, weights):
        component.output_share = round(weight / total, 4) if total > 0 else 0.0


def _finalize_report(parsed: dict[str, Any], bundle: ContextBundle) -> ContributionReport:
    """Build the judged output-contribution report for one pass."""
    judged = {item.get("component"): item for item in parsed.get("components", [])}
    components: list[ComponentScore] = []
    for name in _ALL_COMPONENTS:
        item = judged.get(name, {})
        components.append(
            ComponentScore(
                component=name,  # type: ignore[arg-type]
                output_contribution=float(item.get("output_contribution", 0.0)),
                rationale=str(item.get("rationale", "")),
            )
        )
    _normalize_output_shares(components)

    return ContributionReport(
        run_id=bundle.run_id,
        user_question=bundle.user_input,
        final_decision=str(parsed.get("final_decision", "unknown")),
        components=components,
    )


async def audit_run(bundle: ContextBundle, *, agent: ContextValueAuditorAgent | None = None) -> ContributionReport:
    """Run one audit pass over a normalized run bundle."""
    judge_text = bundle_to_judge_text(bundle)

    async def _invoke(active: ContextValueAuditorAgent) -> ContributionReport:
        result = await active.run(judge_text)
        parsed = _extract_json(result.text)
        return _finalize_report(parsed, bundle)

    if agent is not None:
        return await _invoke(agent)
    async with ContextValueAuditorAgent() as owned_agent:
        return await _invoke(owned_agent)


def _aggregate_reports(
    bundle: ContextBundle, reports: list[ContributionReport], passes: int
) -> AggregatedReport:
    """Aggregate per-pass reports into stability statistics per component."""
    stabilities: list[ComponentStability] = []
    for name in _ALL_COMPONENTS:
        scores: list[float] = []
        out_shares: list[float] = []
        rationales: list[str] = []
        for report in reports:
            for component in report.components:
                if component.component == name:
                    scores.append(component.output_contribution)
                    out_shares.append(component.output_share)
                    if component.rationale:
                        rationales.append(component.rationale)
        if not scores:
            continue
        stabilities.append(
            ComponentStability(
                component=name,  # type: ignore[arg-type]
                mean_output_contribution=round(statistics.fmean(scores), 4),
                output_variance=round(statistics.pvariance(scores), 4) if len(scores) > 1 else 0.0,
                mean_output_share=round(statistics.fmean(out_shares), 4),
                rationales=rationales,
            )
        )

    decision_mode = Counter(r.final_decision for r in reports).most_common(1)[0][0]

    return AggregatedReport(
        run_id=bundle.run_id,
        session_id=bundle.session_id,
        user_question=bundle.user_input,
        passes=passes,
        final_decision_mode=decision_mode,
        components=stabilities,
        per_pass=reports,
    )


async def audit_session(session_id: str, *, passes: int = 5) -> None:
    """Audit every run in a session and write context + output records to Cosmos."""
    context_records: list[dict[str, Any]] = []
    output_records: list[dict[str, Any]] = []

    async with ContextValueAuditorAgent() as agent:
        for run in read_session_runs(session_id):
            if not run.get("llm_outputs"):
                continue
            bundle = bundle_from_run(run, session_id=session_id)
            context_records.extend(build_context_records(bundle))
            reports = [await audit_run(bundle, agent=agent) for _ in range(passes)]
            output_records.append(build_output_record(_aggregate_reports(bundle, reports, passes)))

    write_context_records(context_records)
    write_output_records(output_records)
    print(f"Session '{session_id}': {len(context_records)} context, {len(output_records)} output records.")


def main() -> None:
    """Audit a Cosmos session and generate both output types.

    Usage: python -m DemoAgents.ContextValueAuditor.agent [session_id]"""
    session_id = sys.argv[1] if len(sys.argv) > 1 else "session-noncompact"
    asyncio.run(audit_session(session_id))


if __name__ == "__main__":
    main()
