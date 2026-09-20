"""Export one Cosmos audit session into a local token+value report for the web app.

This is the offline-generation step: it reads the audit events for a session,
reuses the ContextValueAuditor to fold each run into a ContextBundle (per-component
token footprint per LLM call), optionally scores each component's output value with
the auditor judge, and writes a single JSON file the Streamlit app reads offline.

Usage::

    python -m tokenoptimization.export <session_id> [--passes N] [--no-value] [--review]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from DemoAgents.ContextValueAuditor.cosmos_source import (
    bundle_from_run,
    read_session_output_records,
    read_session_runs,
)
from DemoAgents.ContextValueAuditor.normalizer import _estimate_tokens
from DemoAgents.ContextValueAuditor.schema import ContextBundle

load_dotenv()

_REPORT_DIR = Path(__file__).resolve().parents[1] / "output" / "token_report"


def _component_texts(bundle: ContextBundle) -> dict[str, str]:
    """Flatten the bundle's components into plain text for Copilot review."""
    return {
        "instructions": bundle.instructions,
        "user_input": bundle.user_input,
        "tool_definitions": "\n".join(
            f"{d.name}: {d.description}" for d in bundle.tool_definitions
        ),
        "tool_results": "\n".join(
            f"{r.name or r.call_id}: {r.result}" for r in bundle.tool_results
        ),
        "assistant-tools": bundle.assistant_tools,
        "history-user": bundle.history.get("user_input", ""),
        "history-tool-results": bundle.history.get("tool_results", ""),
        "history-assistant-responses": bundle.history.get("assistant_text", ""),
        "history-assistant-tools": bundle.history.get("assistant_tools", ""),
        "final_output": bundle.final_output,
    }


def _run_to_record(
    run: dict[str, Any], bundle: ContextBundle, value: dict[str, Any]
) -> dict[str, Any]:
    """Assemble one run's token profile, value scores, and component text."""
    breakdowns = bundle.call_breakdowns
    value_map: dict[str, dict[str, float]] = value.get("components", {})

    tokens_by_component: dict[str, list[int]] = {}
    shares_by_component: dict[str, list[float]] = {}
    for breakdown in breakdowns:
        for entry in breakdown["components"]:
            tokens_by_component.setdefault(entry["component"], []).append(
                entry["context_tokens"]
            )
            shares_by_component.setdefault(entry["component"], []).append(
                entry["context_share"]
            )

    max_components = {"assistant-tools", "tool_results"}
    aggregated_tokens = {
        name: max(tokens) if name in max_components else sum(tokens)
        for name, tokens in tokens_by_component.items()
    }

    components: list[dict[str, Any]] = []
    for name, context_tokens in aggregated_tokens.items():
        scores = value_map.get(name, {})
        context_shares = shares_by_component[name]
        components.append(
            {
                "component": name,
                "present": context_tokens > 0,
                "context_tokens": context_tokens,
                "context_share": round(sum(context_shares) / len(context_shares), 4),
                "output_contribution": scores.get("mean_output_contribution"),
                "output_share": scores.get("mean_output_share"),
            }
        )

    return {
        "run_id": bundle.run_id,
        "model": bundle.model,
        "final_decision": value.get("final_decision", "unknown"),
        "num_llm_calls": len(breakdowns),
        "billed_input_tokens_total": sum(b["input_tokens"] for b in breakdowns),
        "billed_output_tokens_total": sum(b["output_tokens"] for b in breakdowns),
        "final_output_tokens_estimated": _estimate_tokens(bundle.final_output),
        "components": components,
        "per_call": breakdowns,
        "texts": _component_texts(bundle),
        "suggestions": None,
    }


def _load_values(session_id: str) -> dict[str, dict[str, Any]]:
    """Load stored output-contribution values keyed by run ID."""
    results: dict[str, dict[str, Any]] = {}
    for record in read_session_output_records(session_id):
        results[record.get("run_id", "")] = {
            "final_decision": record.get("final_decision", "unknown"),
            "components": {
                component["component"]: component
                for component in record.get("components", [])
            },
        }
    return results


async def _build_report(
    session_id: str, *, passes: int, include_value: bool, with_review: bool
) -> dict[str, Any]:
    """Read the session, score it, and build the report dictionary."""
    pairs: list[tuple[dict[str, Any], ContextBundle]] = []
    for run in read_session_runs(session_id):
        if not run.get("llm_outputs"):
            continue
        pairs.append((run, bundle_from_run(run, session_id=session_id)))

    value_by_run: dict[str, dict[str, Any]] = {}
    if include_value and pairs:
        try:
            value_by_run = _load_values(session_id)
        except Exception as exc:  # Cosmos boundary: keep the token report usable
            print(f"Output values unavailable ({type(exc).__name__}: {exc}).")

    records = [
        _run_to_record(run, bundle, value_by_run.get(bundle.run_id or "", {}))
        for run, bundle in pairs
    ]

    if with_review and records:
        from tokenoptimization.copilot_review import review_records

        try:
            await review_records(records)
        except Exception as exc:  # Optional review boundary; keep the report usable.
            print(f"Copilot review skipped ({type(exc).__name__}: {exc}).")

    return {
        "session_id": session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": records,
    }


def export_session(
    session_id: str,
    *,
    passes: int = 3,
    include_value: bool = True,
    with_review: bool = False,
) -> Path:
    """Export a session to ``output/token_report/<session_id>.json`` and return the path."""
    report = asyncio.run(
        _build_report(
            session_id,
            passes=passes,
            include_value=include_value,
            with_review=with_review,
        )
    )
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _REPORT_DIR / f"{session_id}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {len(report['runs'])} run(s) to {out_path}")
    return out_path


def main() -> None:
    """CLI entry point for exporting a session token report."""
    parser = argparse.ArgumentParser(description="Export a Cosmos session token report.")
    parser.add_argument("session_id", nargs="?", default="session-123")
    parser.add_argument("--passes", type=int, default=3, help="Auditor value-scoring passes.")
    parser.add_argument("--no-value", action="store_true", help="Skip LLM value scoring.")
    parser.add_argument("--review", action="store_true", help="Attach Copilot SDK suggestions.")
    args = parser.parse_args()

    export_session(
        args.session_id,
        passes=args.passes,
        include_value=not args.no_value,
        with_review=args.review,
    )


if __name__ == "__main__":
    main()
