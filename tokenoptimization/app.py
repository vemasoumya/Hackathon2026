"""Streamlit report: per-run token attribution, Copilot optimization suggestions,
and a last-run-vs-current-run comparison for the ReturnsRefund agent.

Reads the offline JSON produced by ``export.py`` from ``output/token_report/``.
Run with::

    streamlit run src/DemoAgents/tokenoptimization/app.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

# Allow `streamlit run tokenoptimization/app.py` to import the package by root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tokenoptimization.copilot_review import review_run

_REPORT_DIR = Path(__file__).resolve().parents[1] / "output" / "token_report"
_COMPONENT_ORDER = (
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


def _list_reports() -> list[Path]:
    """Return available exported report files, newest first."""
    if not _REPORT_DIR.exists():
        return []
    return sorted(_REPORT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _load_report(path: Path) -> dict[str, Any]:
    """Load one exported report file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _run_label(run: dict[str, Any], index: int) -> str:
    """Human-readable label for a run in selectors."""
    run_id = run.get("run_id") or f"run-{index + 1}"
    return f"{index + 1}. {run_id[:18]} ({run.get('final_decision', 'unknown')})"


def _select_run(
    reports: list[tuple[Path, dict[str, Any]]], key_prefix: str
) -> tuple[Path, dict[str, Any], dict[str, Any]] | None:
    """Render local report/run selectors and return the selected run."""
    report_names = [path.name for path, _ in reports]
    chosen_name = st.selectbox("Report", report_names, key=f"{key_prefix}_report")
    report_path, report = next(
        (path, data) for path, data in reports if path.name == chosen_name
    )
    runs = report.get("runs", [])
    if not runs:
        st.warning("This report has no runs.")
        return None

    st.caption(
        f"Session: {report.get('session_id', '?')} | "
        f"Generated: {report.get('generated_at', '?')}"
    )
    labels = [_run_label(run, index) for index, run in enumerate(runs)]
    selected = st.selectbox(
        "Run",
        range(len(runs)),
        format_func=lambda index: labels[index],
        key=f"{key_prefix}_run",
    )
    return report_path, report, runs[selected]


def _token_frame(run: dict[str, Any]) -> pd.DataFrame:
    """Build a component/token DataFrame for the selected run."""
    return pd.DataFrame(
        [
        {
            "component": c["component"],
            "tokens": c["context_tokens"],
            "context_share": c["context_share"],
            "output_share": c.get("output_share"),
        }
        for c in run["components"]
        ]
    )


def _render_token_attribution(run: dict[str, Any]) -> None:
    """View 1: where the tokens go for the selected run."""
    st.subheader("1. Token attribution")

    top = st.columns(3)
    top[0].metric("LLM calls", run.get("num_llm_calls", 0))
    top[1].metric("Billed input tokens", run.get("billed_input_tokens_total", 0))
    top[2].metric("Billed output tokens", run.get("billed_output_tokens_total", 0))

    frame = _token_frame(run)
    st.bar_chart(frame.set_index("component")["tokens"])

    display = frame.rename(
        columns={
            "tokens": "Tokens",
            "context_share": "Context share",
            "output_share": "Output Contribution",
            "component": "Component",
        }
    )
    st.dataframe(display, hide_index=True, use_container_width=True)

    inputs = frame.copy()
    inputs = inputs.dropna(subset=["output_share"])
    if not inputs.empty:
        inputs["cost_vs_value"] = inputs["context_share"] - inputs["output_share"]
        worst = inputs.sort_values("cost_vs_value", ascending=False).iloc[0]
        if worst["cost_vs_value"] > 0:
            st.info(
                f"**Optimization target:** `{worst['component']}` uses "
                f"{worst['context_share']:.0%} of context tokens but drives only "
                f"{worst['output_share']:.0%} of the output value."
            )

    with st.expander("Per-LLM-call breakdown (cumulative prompt growth)"):
        for call in run.get("per_call", []):
            st.caption(
                f"Call {call['call_index']} — input tokens: {call['input_tokens']}"
            )
            call_frame = pd.DataFrame(call["components"])
            st.dataframe(call_frame, hide_index=True, use_container_width=True)


def _render_suggestions(run: dict[str, Any], report_path: Path, report: dict[str, Any]) -> None:
    """View 2: Copilot SDK optimization suggestions (advisory only)."""
    st.subheader("2. Optimization suggestions (GitHub Copilot SDK)")
    st.caption("Advisory only — no files are modified.")

    suggestions = run.get("suggestions")
    if st.button("Run Copilot review for this run", type="primary"):
        with st.spinner("Asking Copilot to review the agent and token profile..."):
            try:
                suggestions = asyncio.run(review_run(run))
                run["suggestions"] = suggestions
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                st.success("Review complete and cached to the report file.")
            except Exception as exc:  # SDK/auth boundary surfaced to the user
                st.error(f"Copilot review failed: {type(exc).__name__}: {exc}")

    if not suggestions:
        st.write("No suggestions yet. Run the review, or export with `--review`.")
        return

    if suggestions.get("summary"):
        st.markdown(f"**Summary.** {suggestions['summary']}")

    for item in suggestions.get("items", []):
        severity = str(item.get("severity", "medium")).lower()
        icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}.get(severity, "🟠")
        with st.expander(f"{icon} {item.get('title', 'Suggestion')} — target: {item.get('target', '?')}"):
            st.markdown(f"**Recommendation.** {item.get('recommendation', '')}")
            if item.get("estimated_token_savings"):
                st.markdown(f"**Estimated savings.** {item['estimated_token_savings']}")
            if item.get("change"):
                st.code(item["change"])


def _render_comparison(reports: list[tuple[Path, dict[str, Any]]]) -> None:
    """View 3: compare any two session/run combinations."""
    st.subheader("3. Comparison")

    options: list[tuple[str, dict[str, Any], str, int]] = []
    for path, report in reports:
        session_id = report.get("session_id", path.stem)
        for index, run in enumerate(report.get("runs", [])):
            options.append(
                (
                    f"{session_id} / {_run_label(run, index)}",
                    run,
                    path.name,
                    index,
                )
            )

    if len(options) < 2:
        st.write("Need at least two session/run combinations to compare.")
        return

    selectors = st.columns(2)
    baseline_choice = selectors[0].selectbox(
        "Baseline session / run",
        range(len(options)),
        index=1,
        format_func=lambda index: options[index][0],
    )
    candidate_choice = selectors[1].selectbox(
        "Candidate session / run",
        range(len(options)),
        index=0,
        format_func=lambda index: options[index][0],
    )
    baseline = options[baseline_choice][1]
    candidate = options[candidate_choice][1]

    prev_tokens = {c["component"]: c["context_tokens"] for c in baseline["components"]}
    curr_tokens = {c["component"]: c["context_tokens"] for c in candidate["components"]}

    rows = []
    for name in _COMPONENT_ORDER:
        before = prev_tokens.get(name, 0)
        after = curr_tokens.get(name, 0)
        rows.append({"component": name, "previous": before, "current": after, "delta": after - before})
    frame = pd.DataFrame(rows)

    head = st.columns(3)
    head[0].metric(
        "Billed input tokens",
        candidate.get("billed_input_tokens_total", 0),
        delta=candidate.get("billed_input_tokens_total", 0)
        - baseline.get("billed_input_tokens_total", 0),
        delta_color="inverse",
    )
    head[1].metric(
        "Billed output tokens",
        candidate.get("billed_output_tokens_total", 0),
        delta=candidate.get("billed_output_tokens_total", 0)
        - baseline.get("billed_output_tokens_total", 0),
        delta_color="inverse",
    )
    head[2].metric(
        "Decision",
        candidate.get("final_decision", "unknown"),
        delta="changed"
        if candidate.get("final_decision") != baseline.get("final_decision")
        else "same",
        delta_color="off",
    )

    st.bar_chart(frame.set_index("component")[["previous", "current"]])
    st.dataframe(frame, hide_index=True, use_container_width=True)


def main() -> None:
    """Render the Streamlit report."""
    st.set_page_config(page_title="Token Optimizer", layout="wide")
    st.title("ReturnsRefund token optimizer")

    reports = _list_reports()
    if not reports:
        st.warning(
            "No report found. Generate one first:\n\n"
            "`python -m tokenoptimization.export <session_id> --review`"
        )
        return

    loaded_reports = [(path, _load_report(path)) for path in reports]
    attribution_tab, suggestions_tab, comparison_tab = st.tabs(
        ["Token attribution", "Optimization", "Comparison"]
    )
    with attribution_tab:
        selection = _select_run(loaded_reports, "attribution")
        if selection:
            _, _, run = selection
            _render_token_attribution(run)
    with suggestions_tab:
        selection = _select_run(loaded_reports, "optimization")
        if selection:
            report_path, report, run = selection
            _render_suggestions(run, report_path, report)
    with comparison_tab:
        _render_comparison(loaded_reports)


if __name__ == "__main__":
    main()
