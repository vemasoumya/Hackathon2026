---
title: Local setup guide
description: Step-by-step instructions to run this project locally with the Azure Cosmos DB Emulator and the required environment variables.
author: Hackathon 2026
date: 2026-09-13
ms.date: 2026-09-13
ms.topic: tutorial
keywords:
  - cosmos db
  - emulator
  - local development
  - azure ai
  - setup
estimated_reading_time: 10
---

## Prerequisites

Before you begin, make sure you have the following installed on your Windows machine:

* Python 3.13
* Git
* VS Code
* Azure CLI
* Azure Cosmos DB Emulator
* Access to an Azure AI Foundry project and an embedding deployment

This project expects:

* a Cosmos DB endpoint and key
* an Azure AI Foundry project endpoint
* an embedding deployment name
* local authentication via Azure CLI or environment variables

## 1. Clone the repo and open it in VS Code

```powershell
cd C:\hack-2026\Hackathon2026
code .
```

## 2. Create and activate a virtual environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```

## 3. Install the project dependencies

From the project root:

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .[tokenoptimizer]
```

This installs the project itself plus the Streamlit, pandas, tiktoken, and GitHub Copilot SDK extras needed by the token optimization dashboard.

The package layout is intentionally split between:

* [src/DemoAgents/ReturnsRefund](src/DemoAgents/ReturnsRefund) for the agent itself
* [src/DemoAgents/ContextValueAuditor](src/DemoAgents/ContextValueAuditor) for the audit/value analysis agent
* [tokenoptimization](tokenoptimization) for the repo-root token dashboard and export tooling

The root package [tokenoptimization](tokenoptimization) is the correct target for the token workflow. The old `DemoAgents.tokenoptimization` layout was removed.

If the local wheel path is not valid on your machine, update it in [pyproject.toml](pyproject.toml) to the correct Windows file path before running the install command.

### Install check

```powershell
python -c "import tokenoptimization, DemoAgents.ReturnsRefund.agent, DemoAgents.ContextValueAuditor.agent; print('imports OK')"
```

## 4. Install and start the Azure Cosmos DB Emulator

### Install the emulator

Install the Azure Cosmos DB Emulator from Microsoft documentation, or use the Windows installer if it is already available on your machine.

### Start the emulator

You can usually start it from Windows Start or from a path like:

```powershell
"C:\Program Files\Azure Cosmos DB Emulator\CosmosDBEmulator.exe"
```

Then open the emulator explorer in a browser:

```text
https://localhost:8081/_explorer/index.html
```

The emulator runs with a default connection string and key. Use the key shown in the emulator UI or the emulator documentation.

## 5. Sign in to Azure

This project uses `DefaultAzureCredential` for Azure AI access in several places. For local machine development, the easiest option is to sign in with Azure CLI:

```powershell
az login
az account set --subscription "<your-subscription-id>"
```

If you prefer explicit credentials, set the usual Azure environment variables instead.

## 6. Create a local .env file

Create a file named `.env` in the project root with contents similar to this:

```env
COSMOS_ENDPOINT=https://localhost:8081
COSMOS_KEY=<cosmos-emulator-key>

# Send agent audit events to Cosmos DB
AUDIT_BACKEND=cosmos
AUDIT_COSMOS_ENDPOINT=${COSMOS_ENDPOINT}
AUDIT_COSMOS_KEY=${COSMOS_KEY}
AUDIT_COSMOS_DATABASE=auditdb
AUDIT_COSMOS_CONTAINER=audit_records

FOUNDRY_PROJECT_ENDPOINT=https://<your-ai-project>.services.ai.azure.com/api/projects/<your-project-name>
FOUNDRY_EMBEDDING_DEPLOYMENT_NAME=<your-embedding-deployment-name>

# Optional, if you use Azure CLI auth and not explicit credentials
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>
```

Notes:

* `COSMOS_ENDPOINT` should be the emulator endpoint, typically `https://localhost:8081`
* `COSMOS_KEY` should be the local emulator key
* `FOUNDRY_PROJECT_ENDPOINT` must point to your Azure AI Foundry project
* `FOUNDRY_EMBEDDING_DEPLOYMENT_NAME` must be a valid embedding model deployment name in that project

## 7. Create the required Cosmos databases and containers

The app expects the following databases and containers:

* `vectordb` / `returns_policy_vectors`
* `hackathon2026` / `return_history`
* `auditdb` / `audit_records` for agent audit events and the context auditor

When `AUDIT_BACKEND=cosmos`, the shared audit package creates the audit
database and container automatically with `/session_id` as the partition key.

The easiest way to initialize the vector policy store is to run the helper script:

```powershell
python .\src\DemoAgents\ReturnsRefund\create_vector.py
```

This script reads [src/DemoAgents/ReturnsRefund/knowledge/policy.md](src/DemoAgents/ReturnsRefund/knowledge/policy.md), splits it into sections, creates vector embeddings, and uploads them into Cosmos DB.

The script will also create the `vectordb` database and `returns_policy_vectors` container if they do not already exist.

## 8. Verify the environment

Run the following check to confirm the required variables are available:

```powershell
python -c "import os; print(os.getenv('COSMOS_ENDPOINT')); print(os.getenv('FOUNDRY_PROJECT_ENDPOINT')); print(os.getenv('FOUNDRY_EMBEDDING_DEPLOYMENT_NAME'))"
```

If any values are blank, fix them in the `.env` file before continuing.

## 9. Run the returns/refund agent

From the project root:

### Run without compaction

Use `session-noncompact` when you do not want tool-call compaction. This is also the default when you omit the session ID.

```powershell
python -m DemoAgents.ReturnsRefund.agent
```

The equivalent command with the console script is:

```powershell
returns-refund-agent
```

You can also provide the noncompact session ID explicitly:

```powershell
python -m DemoAgents.ReturnsRefund.agent session-noncompact
```

### Run with compaction

To enable selective tool-call compaction, pass a session ID ending in `-compact`. The final hyphen-separated token must be exactly `compact`.

```powershell
python -m DemoAgents.ReturnsRefund.agent session-compact
```

The equivalent command with the console script is:

```powershell
returns-refund-agent session-compact
```

Session IDs such as `session-noncompact` or `session-test` run without compaction. The app will prompt for chat input. Type your messages after the `You:` prompt and press Enter. Type `exit` to stop.

### Sample back-and-forth chat

The following is a complete example conversation using the built-in sample data. Lines starting with `You:` are what you type; lines starting with `Agent:` are the responses you should expect.

```text
You: I am customer CUST-001 and my order ORD-1001 for Wireless Headphones arrived defective. I want a refund.
Agent: Approved for refund. Outcome: approve_refund. Your Wireless Headphones are electronics, you reported them as defective, and the order is 18 days old, which is within the 30-day window for defective electronics. The policy allows a refund or replacement, and I used your stated preference for a refund.

You: Yes, please process the refund.
Agent: I cannot process the refund directly because this demo has read-only tools. The request is eligible under the defective electronics policy. Use your return portal or contact support to submit the refund request.

You: exit
```

#### Sample conversation with multiple return requests

```text
You: My customer id is CUST-001 and I want to return my order ORD-1001 as the headphones are not working on unpackaging itself
Agent: [Agent response]

You: My customer id is CUST-001 and I want to return my order ORD-1004 as tooth brush was broken on unpackaging itself
Agent: [Agent response]

You: thanks
```

### More sample prompts to try

Each of these uses a valid customer and order from the sample data:

* Refund for a defective item:
  `I am customer CUST-001 and my order ORD-1001 arrived defective. I want a refund.`
* Replacement for a damaged item:
  `I am customer CUST-003 and my order ORD-1003 was damaged on delivery. I want a replacement.`
* Change of mind on a recent order:
  `I am customer CUST-002 and I want to return my order ORD-1002 because I changed my mind.`
* Digital goods return question:
  `I am customer CUST-002 and I want a refund for my order ORD-1005 for the Design Software License.`

> [!TIP]
> Provide the customer ID, the order ID, the product issue, and the resolution you want in a single message. The agent looks up the customer, validates the order, searches the return policy, and then recommends a resolution.

## 10. Run the token optimization dashboard

The token optimization workflow lives in the repo-root package [tokenoptimization](tokenoptimization), not under `src/DemoAgents`.

### 10.1 Export both sessions to JSON

```powershell
python -m tokenoptimization.export session-noncompact --passes 3
python -m tokenoptimization.export session-compact --passes 3
```

Run both commands after completing the same test conversation in the noncompact and compact agent sessions. Each command reads the corresponding Cosmos audit records, rebuilds the context bundle, and writes a report under `output/token_report/`:

* `output/token_report/session-noncompact.json`
* `output/token_report/session-compact.json`

To include GitHub Copilot optimization suggestions, add `--review` to each command:

```powershell
python -m tokenoptimization.export session-noncompact --passes 3 --review
python -m tokenoptimization.export session-compact --passes 3 --review
```

Optional flags:

* `--passes 3` runs the auditor value-scoring loop multiple times
* `--no-value` skips the value-scoring pass when you want a pure token-only export
* `--review` asks the GitHub Copilot SDK to add optimization suggestions to the report

### 10.2 Launch the dashboard

```powershell
streamlit run tokenoptimization/app.py
```

Open the Streamlit URL shown in the terminal, usually <http://localhost:8501>. The app reads both reports from `output/token_report/`. Use the **Report** selector in the sidebar to switch between the noncompact and compact sessions.

The **Token attribution** tab shows the metrics for the selected session. The **Comparison** tab compares runs within the selected report. To compare compact versus noncompact, select each report in turn and compare the displayed token metrics.

### 10.3 Useful token dashboard commands

```powershell
python -m tokenoptimization.export --help
streamlit run tokenoptimization/app.py
```

The dashboard expects the exported report files to exist in `output/token_report/` before it renders. If no report exists, the UI shows a warning and asks you to generate one first.

## 11. Run the context auditor

The auditor reads Cosmos audit records and reconstructs how much each context input contributed to an answer.

Run the auditor once for each session. For the noncompact scenario, run:

```powershell
python -m DemoAgents.ContextValueAuditor.agent session-noncompact
```

For the compact scenario, run:

```powershell
python -m DemoAgents.ContextValueAuditor.agent session-compact
```

Each command writes context-contribution and output-contribution records for its selected session.

If you omit the argument, it processes `session-noncompact`:

```powershell
python -m DemoAgents.ContextValueAuditor.agent
```

The auditor uses `AZURE_AI_FOUNDRY_API_KEY` to call the judge model. It reads
the agent audit records from `auditdb` / `audit_records`, then creates and
writes its results to `auditdb` / `context_contribution` and
`auditdb` / `output_contribution`. These two result containers are created
automatically when they do not exist.

## 12. Troubleshooting

### `DefaultAzureCredential` errors

If Azure authentication fails, make sure you ran:

```powershell
az login
```

and that your current account has access to the Azure AI project.

### Cosmos emulator connection errors

Check these items:

* the emulator is running
* you are using `https://localhost:8081`
* the key matches the emulator key shown in the explorer
* no firewall or proxy is blocking local requests

### `InsecureRequestWarning` messages

The returns/refund agent filters the expected Cosmos DB Emulator warning for
`localhost` and `127.0.0.1`, because the Cosmos SDK intentionally disables TLS
verification for those local endpoints. You should not normally see
`InsecureRequestWarning` when starting the agent. Warnings for other hosts are
not filtered and should be investigated.

### Audit events still go to a local file

Confirm that the `.env` file contains `AUDIT_BACKEND=cosmos` and that
`AUDIT_COSMOS_ENDPOINT` and `AUDIT_COSMOS_KEY` resolve to the same endpoint and
key as `COSMOS_ENDPOINT` and `COSMOS_KEY`. On startup, the agent should log
`Audit backend: Cosmos DB` and identify the configured database and container.

### Missing embedding deployment

Ensure `FOUNDRY_EMBEDDING_DEPLOYMENT_NAME` matches an actual deployment name in your Azure AI Foundry project.

### Local wheel installation fails

Update the dependency path in [pyproject.toml](pyproject.toml) to your local wheel location, for example:

```toml
frontier-shared @ file:///C:/Petronas/Repos/commoncomponents/shared/dist/frontier_shared-0.1.13-py3-none-any.whl
```

Then reinstall:

```powershell
python -m pip install -e .
```

## 13. Recommended local development flow

1. Start the Cosmos emulator
2. Sign in with Azure CLI
3. Create the `.env` file
4. Create and activate `.venv`
5. Install the package with `python -m pip install -e .[tokenoptimizer]`
6. Seed the vector DB with `create_vector.py`
7. Start the agent
8. Export and review a token session with `python -m tokenoptimization.export`
9. Launch the Streamlit dashboard with `streamlit run tokenoptimization/app.py`
10. Test with customer and order IDs
11. Review the auditor output for context attribution

This is the simplest local flow for getting the project running in a development environment without a cloud-hosted Cosmos instance.

## 14. Full local startup checklist

Use this checklist to get the project running from a clean machine:

```powershell
cd C:\hack-2026\Hackathon2026
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .[tokenoptimizer]
python -c "import tokenoptimization, DemoAgents.ReturnsRefund.agent, DemoAgents.ContextValueAuditor.agent; print('imports OK')"
```

Then create your `.env` file and start the services as described above.

If you are only working on the optimization dashboard, you can skip the vector DB and agent startup and just run:

```powershell
python -m tokenoptimization.export session-noncompact --review
python -m tokenoptimization.export session-compact --review
streamlit run tokenoptimization/app.py
```
