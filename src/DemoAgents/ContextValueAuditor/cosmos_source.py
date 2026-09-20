"""Read agent-run audit events from Cosmos and assemble ContextBundles.

The auditor process starts here: it queries the audit container for a session,
segments the chronological event stream into runs, and folds each run's
``llm_response_received`` calls plus its ``agent_response_completed`` result
into a ContextBundle ready for scoring.

Event stream within one run (as emitted by the middleware)::

    user_prompt_received
    llm_request_sent      (ignored; pre-compaction prompt)
    llm_response_received -> payload.prompt.{messages, options}, payload.usage
    tool_call_completed   (ignored; tool results also ride in the next llm call)
    llm_response_received
    ...
    agent_response_completed -> payload.{response, usage}
"""

from __future__ import annotations

import os
from typing import Any

from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential

from DemoAgents.ContextValueAuditor.normalizer import (
    from_response_record,
    normalize_run,
)
from DemoAgents.ContextValueAuditor.schema import AggregatedReport, ContextBundle

_RUN_START = "user_prompt_received"
_LLM_OUTPUT = "llm_response_received"
_RUN_END = "agent_response_completed"


def get_audit_container(container: str | None = None) -> Any:
    """Return a Cosmos container client in the audit database.

    Reads endpoint/key/database from the ``AUDIT_COSMOS_*`` variables, falling
    back to the generic ``COSMOS_*`` ones. Uses the key when present, otherwise
    ``DefaultAzureCredential``.
    """
    endpoint = os.environ.get("AUDIT_COSMOS_ENDPOINT") or os.environ["COSMOS_ENDPOINT"]
    database = os.getenv("AUDIT_COSMOS_DATABASE", "auditdb")
    container = container or os.getenv("AUDIT_COSMOS_CONTAINER", "audit_records")
    key = os.environ.get("AUDIT_COSMOS_KEY") or os.environ.get("COSMOS_KEY")
    credential: Any = key or DefaultAzureCredential()
    client = CosmosClient(url=endpoint, credential=credential)
    database_client = client.create_database_if_not_exists(id=database)
    database_client.create_container_if_not_exists(
        id=container,
        partition_key=PartitionKey(path="/session_id"),
    )
    return database_client.get_container_client(container)


def read_session_events(session_id: str) -> list[dict[str, Any]]:
    """Read all audit events for a session, oldest first."""
    container = get_audit_container()
    query = "SELECT * FROM c WHERE c.session_id = @sid ORDER BY c.event_time_utc ASC"
    return list(
        container.query_items(
            query=query,
            parameters=[{"name": "@sid", "value": session_id}],
            partition_key=session_id,
        )
    )


def split_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Segment chronologically ordered events into per-run groups.

    A run starts at ``user_prompt_received`` and ends at
    ``agent_response_completed``; the ``llm_response_received`` events in between
    carry each call's post-compaction prompt and token usage. Other event types
    (for example ``llm_request_sent`` and ``tool_call_completed``) are ignored.
    """
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for event in events:
        action = event.get("action")
        if action == _RUN_START:
            current = {"start": event, "llm_outputs": [], "response": None}
            runs.append(current)
        elif current is None:
            continue
        elif action == _LLM_OUTPUT:
            current["llm_outputs"].append(event)
        elif action == _RUN_END:
            current["response"] = event
            current = None

    return runs


def bundle_from_run(run: dict[str, Any], *, session_id: str | None = None) -> ContextBundle:
    """Fold one segmented run into a ContextBundle.

    Messages come from the ``llm_response_received`` events, which carry the
    post-compaction prompt (excluded messages flagged); their ``input_tokens``
    drive the per-call attribution.
    """
    response_event = run.get("response") or {}
    start_event = run["start"]
    final_output, _ = from_response_record(response_event)
    run_id = start_event.get("event_id")

    outputs = run.get("llm_outputs") or []
    call_input_tokens = [
        int(from_response_record(output_event)[1].get("input_tokens", 0) or 0)
        for output_event in outputs
    ]
    call_output_tokens = [
        int(from_response_record(output_event)[1].get("output_tokens", 0) or 0)
        for output_event in outputs
    ]

    return normalize_run(
        outputs,
        final_output,
        run_id=run_id,
        session_id=session_id,
        call_input_tokens=call_input_tokens,
        call_output_tokens=call_output_tokens,
    )


def read_session_bundles(session_id: str) -> list[ContextBundle]:
    """Read a session from Cosmos and return one ContextBundle per run."""
    events = read_session_events(session_id)
    return [
        bundle_from_run(run, session_id=session_id)
        for run in split_runs(events)
        if run.get("llm_outputs")
    ]


def read_session_runs(session_id: str) -> list[dict[str, Any]]:
    """Read a session and return its segmented runs (with paired llm_outputs)."""
    events = read_session_events(session_id)
    return split_runs(events)


def build_context_records(bundle: ContextBundle) -> list[dict[str, Any]]:
    """Build one context-contribution record per LLM call from the bundle."""
    records: list[dict[str, Any]] = []
    for breakdown in bundle.call_breakdowns:
        index = breakdown["call_index"]
        records.append(
            {
                "id": f"{bundle.run_id}:{index}",
                "type": "context_contribution",
                "session_id": bundle.session_id,
                "run_id": bundle.run_id,
                "call_index": index,
                "input_tokens": breakdown["input_tokens"],
                "output_tokens": breakdown["output_tokens"],
                "components": breakdown["components"],
            }
        )
    return records


def build_output_record(report: AggregatedReport) -> dict[str, Any]:
    """Build one output-contribution record for a run."""
    return {
        "id": f"{report.run_id}",
        "type": "output_contribution",
        "session_id": report.session_id,
        "run_id": report.run_id,
        "user_question": report.user_question,
        "passes": report.passes,
        "final_decision": report.final_decision_mode,
        "components": [
            {
                "component": component.component,
                "mean_output_contribution": component.mean_output_contribution,
                "mean_output_share": component.mean_output_share,
                "output_variance": component.output_variance,
                "rationales": component.rationales,
            }
            for component in report.components
        ],
    }


def get_context_container() -> Any:
    """Return the Cosmos container for context-contribution records."""
    return get_audit_container(os.getenv("AUDIT_CONTEXT_CONTAINER", "context_contribution"))


def get_output_container() -> Any:
    """Return the Cosmos container for output-contribution records."""
    return get_audit_container(os.getenv("AUDIT_OUTPUT_CONTAINER", "output_contribution"))


def read_session_output_records(session_id: str) -> list[dict[str, Any]]:
    """Read output-contribution records for a session."""
    container = get_output_container()
    query = "SELECT * FROM c WHERE c.session_id = @sid AND c.type = 'output_contribution'"
    return list(
        container.query_items(
            query=query,
            parameters=[{"name": "@sid", "value": session_id}],
            partition_key=session_id,
        )
    )


def write_context_records(records: list[dict[str, Any]]) -> int:
    """Upsert context-contribution records (one per LLM call). Returns the count."""
    container = get_context_container()
    for record in records:
        container.upsert_item(record)
    return len(records)


def write_output_records(records: list[dict[str, Any]]) -> int:
    """Upsert output-contribution records (one per run). Returns the count."""
    container = get_output_container()
    for record in records:
        container.upsert_item(record)
    return len(records)

