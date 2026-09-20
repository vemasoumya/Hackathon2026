"""Create vector embeddings from policy.md and store in Azure Cosmos DB.

Each chunk stores two logical columns:
    text      — the H2 heading plus its body
    embedding — the embedding of that same text

Prerequisites:
    pip install openai azure-cosmos azure-identity python-dotenv

Usage:
    Comment or uncomment the operation at the bottom, then run:
    python create_vector.py

Environment variables (from .env):
    FOUNDRY_PROJECT_ENDPOINT          — Azure AI Foundry project endpoint
    FOUNDRY_EMBEDDING_DEPLOYMENT_NAME — Embedding deployment name
    COSMOS_ENDPOINT                   — Cosmos DB endpoint
    COSMOS_KEY                        — Cosmos DB key
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
SOURCE_FILE = KNOWLEDGE_DIR / "policy.md"

ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
MODEL = os.environ["FOUNDRY_EMBEDDING_DEPLOYMENT_NAME"]
COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
COSMOS_KEY = os.environ["COSMOS_KEY"]

DATABASE_NAME = "vectordb"
CONTAINER_NAME = "returns_policy_vectors"

_parsed = urlparse(ENDPOINT)
AZURE_ENDPOINT = f"{_parsed.scheme}://{_parsed.netloc}"


# ---------------------------------------------------------------------------
# Markdown H2 splitter
# ---------------------------------------------------------------------------

@dataclass
class PolicyChunk:
    """A single H2 policy section as heading + body."""
    heading: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.heading}\n\n{self.body}".strip()


_FRONTMATTER_PATTERN = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
_H2_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "chunk"


def split_policy_by_h2(text: str) -> list[PolicyChunk]:
    """Split the policy markdown into chunks at each ``##`` heading."""
    text = _FRONTMATTER_PATTERN.sub("", text, count=1)

    chunks: list[PolicyChunk] = []
    matches = list(_H2_PATTERN.finditer(text))

    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            chunks.append(PolicyChunk(heading=heading, body=body))

    return chunks


def _create_openai_client() -> AzureOpenAI:
    # api_key = os.getenv("AZURE_AI_FOUNDRY_API_KEY")
    # if api_key:
    #     return AzureOpenAI(
    #         api_key=api_key,
    #         azure_endpoint=AZURE_ENDPOINT,
    #         api_version="2024-10-21",
    #     )

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version="2024-10-21",
    )


def create_vectors() -> None:
    """Create policy embeddings and upsert them into Cosmos DB."""
    text = SOURCE_FILE.read_text(encoding="utf-8")
    print(f"Read {len(text)} chars from {SOURCE_FILE.name}")

    chunks = split_policy_by_h2(text)
    print(f"Split into {len(chunks)} chunks")

    openai_client = _create_openai_client()
    texts = [chunk.text for chunk in chunks]
    print(f"Embedding {len(texts)} chunks with model '{MODEL}'...")
    response = openai_client.embeddings.create(input=texts, model=MODEL)
    vectors = [item.embedding for item in response.data]
    dimension = len(vectors[0])
    print(f"Embedding dimension: {dimension}")

    cosmos_client = CosmosClient(url=COSMOS_ENDPOINT, credential=COSMOS_KEY)
    database = cosmos_client.create_database_if_not_exists(DATABASE_NAME)

    vector_embedding_policy = {
        "vectorEmbeddings": [
            {
                "path": "/embedding",
                "dataType": "float32",
                "distanceFunction": "cosine",
                "dimensions": dimension,
            }
        ]
    }

    indexing_policy = {
        "includedPaths": [{"path": "/*"}],
        "excludedPaths": [{"path": "/embedding/*"}],
        "vectorIndexes": [
            {"path": "/embedding", "type": "quantizedFlat"}
        ],
    }

    container = database.create_container_if_not_exists(
        id=CONTAINER_NAME,
        partition_key=PartitionKey(path="/id"),
        vector_embedding_policy=vector_embedding_policy,
        indexing_policy=indexing_policy,
    )
    print(f"Cosmos container '{CONTAINER_NAME}' ready")

    for chunk, vector in zip(chunks, vectors):
        item = {
            "id": _slugify(chunk.heading),
            "text": chunk.text,
            "embedding": vector,
        }
        container.upsert_item(item)
        print(f"  Upserted {item['id']}")

    print(f"\n{len(chunks)} chunks upserted into {DATABASE_NAME}/{CONTAINER_NAME}")


def query_vectors(query_text: str, limit: int = 5) -> None:
    """Query previously created policy vectors in Cosmos DB."""
    openai_client = _create_openai_client()
    query_embedding = openai_client.embeddings.create(input=[query_text], model=MODEL).data[0].embedding

    cosmos_client = CosmosClient(url=COSMOS_ENDPOINT, credential=COSMOS_KEY)
    container = cosmos_client.get_database_client(DATABASE_NAME).get_container_client(CONTAINER_NAME)

    results = container.query_items(
        query=(
            "SELECT TOP @limit c.id, c.text, VectorDistance(c.embedding, @embedding) AS score "
            "FROM c ORDER BY VectorDistance(c.embedding, @embedding)"
        ),
        parameters=[
            {"name": "@limit", "value": limit},
            {"name": "@embedding", "value": query_embedding},
        ],
        enable_cross_partition_query=True,
    )
    print(f"\n--- Results for: '{query_text}' ---")
    for r in results:
        print(f"  score={r['score']:.4f} | {r['id']}")


if __name__ == "__main__":
    create_vectors()
    # query_vectors("my headphones stopped working", 2)
    # query_vectors("my hair oil has a leak", 2)