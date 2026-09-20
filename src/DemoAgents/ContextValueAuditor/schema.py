"""Typed models for the context value auditor input bundle and output report."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ComponentName = Literal[
    "instructions",
    "user_input",
    "tool_definitions",
    "tool_results",
    "assistant-tools",
    "history-user",
    "history-tool-results",
    "history-assistant-responses",
    "history-assistant-tools",
]


class ToolDefinition(BaseModel):
    """A tool the model was offered during the run."""

    name: str
    description: str = ""


class ToolResult(BaseModel):
    """A single tool/function result returned to the model during the run."""

    call_id: str = ""
    name: str = ""
    result: str


class ContextBundle(BaseModel):
    """Normalized view of one agent run, assembled from all its LLM calls."""

    run_id: str | None = None
    session_id: str | None = None
    model: str = ""
    instructions: str = ""
    user_input: str = ""
    history: dict[str, str] = Field(default_factory=dict)
    tool_definitions: list[ToolDefinition] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    assistant_tools: str = ""
    final_output: str = ""
    # Per-call token attribution computed alongside the bundle (one per LLM call).
    call_breakdowns: list[dict[str, Any]] = Field(default_factory=list)


class ComponentScore(BaseModel):
    """Per-component contribution to the final output for one audit pass."""

    component: ComponentName
    output_contribution: float = Field(ge=0.0, le=1.0)
    output_share: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class ContributionReport(BaseModel):
    """Contribution report for a single audit pass over one run."""

    run_id: str | None = None
    user_question: str = ""
    final_decision: str = "unknown"
    components: list[ComponentScore] = Field(default_factory=list)


class ComponentStability(BaseModel):
    """Aggregated statistics for one component across multiple audit passes."""

    component: ComponentName
    mean_output_contribution: float
    output_variance: float
    mean_output_share: float
    rationales: list[str] = Field(default_factory=list)


class AggregatedReport(BaseModel):
    """Stability-aware summary produced by running the audit multiple times."""

    run_id: str | None = None
    session_id: str | None = None
    user_question: str = ""
    passes: int
    final_decision_mode: str
    components: list[ComponentStability] = Field(default_factory=list)
    per_pass: list[ContributionReport] = Field(default_factory=list)
