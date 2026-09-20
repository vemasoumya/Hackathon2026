"""Read-only tools and sample data for the returns and refunds agent."""

import os
from typing import Annotated
from urllib.parse import urlparse

from agent_framework import tool
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI
from pydantic import Field

DATABASE_NAME = "vectordb"
CONTAINER_NAME = "returns_policy_vectors"


CUSTOMERS: dict[str, dict[str, object]] = {
    "CUST-001": {
        "name": "Alex Morgan",
        "preferred_resolution": "replacement",
    },
    "CUST-002": {
        "name": "Priya Shah",
        "preferred_resolution": "refund",
    },
    "CUST-003": {
        "name": "Jordan Lee",
        "preferred_resolution": "replacement",
    },
}

ORDERS: dict[str, dict[str, object]] = {
    "ORD-1001": {
        "customer_id": "CUST-001",
        "product": "Wireless Headphones",
        "category": "electronics",
        "purchase_age_days": 18,
        "status": "delivered",
        "price": 79.99,
    },
    "ORD-1002": {
        "customer_id": "CUST-002",
        "product": "Running Jacket",
        "category": "clothing",
        "purchase_age_days": 8,
        "status": "delivered",
        "price": 64.00,
    },
    "ORD-1003": {
        "customer_id": "CUST-003",
        "product": "Ergonomic Office Chair",
        "category": "furniture",
        "purchase_age_days": 42,
        "status": "delivered",
        "price": 249.00,
    },
    "ORD-1004": {
        "customer_id": "CUST-001",
        "product": "Electric Toothbrush",
        "category": "personal_care",
        "purchase_age_days": 12,
        "status": "delivered",
        "price": 39.99,
    },
    "ORD-1005": {
        "customer_id": "CUST-002",
        "product": "Design Software License",
        "category": "digital_goods",
        "purchase_age_days": 3,
        "status": "fulfilled",
        "price": 29.00,
    },
}


@tool(approval_mode="never_require")
def get_customer(
    customer_id: Annotated[
        str,
        Field(description="The customer ID, for example CUST-001."),
    ],
) -> dict[str, object]:
    """Get the customer details needed to personalize a return decision."""
    customer = CUSTOMERS.get(customer_id.upper())
    if customer is None:
        return {"found": False, "error": "customer_not_found"}

    return {
        "found": True,
        "customer_id": customer_id.upper(),
        "name": customer["name"],
        "preferred_resolution": customer["preferred_resolution"],
    }


@tool(approval_mode="never_require")
def get_order(
    order_id: Annotated[
        str,
        Field(description="The order ID, for example ORD-1001."),
    ],
    customer_id: Annotated[
        str,
        Field(description="The customer ID claiming ownership of the order."),
    ],
) -> dict[str, object]:
    """Get return-relevant order details after verifying customer ownership."""
    normalized_order_id = order_id.upper()
    normalized_customer_id = customer_id.upper()
    order = ORDERS.get(normalized_order_id)

    if order is None or order["customer_id"] != normalized_customer_id:
        return {"found": False, "error": "order_not_found"}

    return {
        "found": True,
        "order_id": normalized_order_id,
        "customer_id": normalized_customer_id,
        "product": order["product"],
        "category": order["category"],
        "purchase_age_days": order["purchase_age_days"],
        "status": order["status"],
        "price": order["price"],
    }


@tool(approval_mode="never_require")
def search_return_policy(
    query: Annotated[
        str,
        Field(description="A concise description of the product, return reason, and known condition."),
    ],
    limit: Annotated[
        int,
        Field(description="The number of matching policy sections to return.", ge=1, le=5),
    ] = 3,
) -> dict[str, object]:
    """Find the policy sections most relevant to a return request."""
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    embedding_model = os.environ["FOUNDRY_EMBEDDING_DEPLOYMENT_NAME"]
    cosmos_endpoint = os.environ["COSMOS_ENDPOINT"]
    cosmos_key = os.environ["COSMOS_KEY"]

    parsed_endpoint = urlparse(project_endpoint)
    azure_endpoint = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}"
    api_key = os.getenv("AZURE_AI_FOUNDRY_API_KEY")
    if api_key:
        openai_client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version="2024-10-21",
        )
    else:
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://cognitiveservices.azure.com/.default",
        )
        openai_client = AzureOpenAI(
            azure_endpoint=azure_endpoint,
            azure_ad_token_provider=token_provider,
            api_version="2024-10-21",
        )
    query_embedding = openai_client.embeddings.create(
        input=[query],
        model=embedding_model,
    ).data[0].embedding

    cosmos_client = CosmosClient(url=cosmos_endpoint, credential=cosmos_key)
    container = cosmos_client.get_database_client(DATABASE_NAME).get_container_client(CONTAINER_NAME)
    results = container.query_items(
        query=(
            "SELECT TOP @limit c.id, c.text, "
            "VectorDistance(c.embedding, @embedding) AS score "
            "FROM c ORDER BY VectorDistance(c.embedding, @embedding)"
        ),
        parameters=[
            {"name": "@limit", "value": limit},
            {"name": "@embedding", "value": query_embedding},
        ],
        enable_cross_partition_query=True,
    )
    matches = [
        {"id": result["id"], "text": result["text"], "score": result["score"]}
        for result in results
    ]
    return {"found": bool(matches), "matches": matches}