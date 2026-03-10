"""
RAG Query Engine for Vault KB.

Routes queries, retrieves relevant chunks from ChromaDB,
deduplicates, ranks, and returns structured context.
Uses Gemini gemini-embedding-001 via google-genai SDK.
"""

import os
from dataclasses import dataclass

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings
from google import genai
from google.genai import types
import streamlit as st
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from router import route_query, RouteResult

console = Console()

# Must match ingest.py
EMBEDDING_MODEL = "gemini-embedding-001"


class GeminiEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function using google-genai SDK.
    Uses 'RETRIEVAL_QUERY' task type for search queries.
    """
    
    def __init__(self, task_type: str = "RETRIEVAL_QUERY"):
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = None
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
        except (ImportError, AttributeError):
            api_key = os.getenv("GEMINI_API_KEY")
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        
        self._client = genai.Client(api_key=api_key)
        self._task_type = task_type
    
    def __call__(self, input: Documents) -> Embeddings:
        """Embed a list of texts using Gemini API."""
        result = self._client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=input,
            config=types.EmbedContentConfig(task_type=self._task_type)
        )
        return [e.values for e in result.embeddings]


@dataclass
class RetrievedChunk:
    """A chunk retrieved from ChromaDB."""
    text: str
    metadata: dict
    distance: float
    collection: str


@st.cache_resource
def get_chroma_client(kb_dir: str) -> chromadb.PersistentClient:
    """Get the persistent ChromaDB client (cached across reruns)."""
    db_path = os.path.join(kb_dir, "chroma_db")
    settings = chromadb.config.Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
    return chromadb.PersistentClient(path=db_path, settings=settings)


@st.cache_resource
def get_embedding_function(task_type: str = "RETRIEVAL_QUERY") -> GeminiEmbeddingFunction:
    """Get the Gemini embedding function (cached across reruns)."""
    return GeminiEmbeddingFunction(task_type=task_type)


def retrieve_from_collection(
    client: chromadb.PersistentClient,
    collection_name: str,
    query: str,
    embedding_fn: GeminiEmbeddingFunction,
    top_k: int = 12,
) -> list[RetrievedChunk]:
    """Retrieve top-k chunks from a specific collection."""
    try:
        collection = client.get_collection(
            name=collection_name,
            embedding_function=embedding_fn,
        )
    except Exception as e:
        console.print(f"[red]Collection '{collection_name}' not found. Run ingestion first.[/red]")
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append(RetrievedChunk(
                text=doc,
                metadata=meta,
                distance=dist,
                collection=collection_name,
            ))

    return chunks


def query_kb(
    kb_dir: str,
    query: str,
    top_k: int = 12,
    verbose: bool = True,
    chat_context: str = "",
    is_drafting_active: bool = False,
) -> tuple[RouteResult, list[RetrievedChunk]]:
    """
    Full RAG query pipeline:
    1. Route the query to appropriate collection(s)
    2. Retrieve chunks from each collection
    3. Deduplicate and rank by distance
    4. Return route result and ranked chunks
    """
    # Step 1: Route
    route = route_query(query, chat_context=chat_context, is_drafting_active=is_drafting_active)

    if verbose:
        console.print(Panel(
            f"[bold]{query}[/bold]",
            title="Query",
            border_style="cyan",
        ))
        console.print(
            f"  🎯 Intent: [bold cyan]{route.intent}[/bold cyan] "
            f"(confidence: {route.confidence:.0%})\n"
            f"  📁 Collections: {', '.join(route.collections)}\n"
            f"  💡 {route.reason}\n"
        )

    # Step 2: Retrieve
    client = get_chroma_client(kb_dir)
    embedding_fn = get_embedding_function()

    all_chunks = []
    for col_name in route.collections:
        chunks = retrieve_from_collection(
            client, col_name, query, embedding_fn, top_k=top_k
        )
        all_chunks.extend(chunks)

    # Step 3: Deduplicate (by text hash) and sort by distance
    seen_texts = set()
    unique_chunks = []
    for chunk in all_chunks:
        text_key = chunk.text[:200]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_chunks.append(chunk)

    # Sort by distance (lower = more similar for cosine)
    unique_chunks.sort(key=lambda c: c.distance)

    # Limit total results
    unique_chunks = unique_chunks[:top_k]

    # Step 4: Display
    if verbose and unique_chunks:
        console.print(f"[bold green]Found {len(unique_chunks)} relevant chunks:[/bold green]\n")

        for i, chunk in enumerate(unique_chunks, 1):
            meta_parts = []
            if chunk.metadata.get("service"):
                meta_parts.append(f"Service: {chunk.metadata['service']}")
            if chunk.metadata.get("level"):
                meta_parts.append(f"Level: {chunk.metadata['level']}")
            if chunk.metadata.get("h1"):
                meta_parts.append(f"§ {chunk.metadata['h1']}")
            if chunk.metadata.get("h2"):
                meta_parts.append(f"→ {chunk.metadata['h2']}")

            meta_str = " | ".join(meta_parts)

            display_text = chunk.text[:500]
            if len(chunk.text) > 500:
                display_text += "..."

            console.print(Panel(
                f"[dim]{meta_str}[/dim]\n"
                f"[dim]Distance: {chunk.distance:.4f} | Source: {chunk.metadata.get('source_file', 'N/A')}[/dim]\n\n"
                f"{display_text}",
                title=f"[bold]Chunk {i}[/bold]",
                border_style="green" if chunk.distance < 0.5 else "yellow",
                width=100,
            ))

    elif verbose:
        console.print("[yellow]No relevant chunks found. Have you run ingestion?[/yellow]")

    return route, unique_chunks


def format_context_for_llm(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks into a context string for LLM prompting."""
    if not chunks:
        return ""

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        header = []
        if chunk.metadata.get("service"):
            header.append(f"Service: {chunk.metadata['service']}")
        if chunk.metadata.get("h1"):
            header.append(f"Section: {chunk.metadata['h1']}")
        if chunk.metadata.get("h2"):
            header.append(f"Subsection: {chunk.metadata['h2']}")

        header_str = " | ".join(header) if header else f"Chunk {i}"

        context_parts.append(
            f"--- Context {i} [{header_str}] ---\n{chunk.text}\n"
        )

    return "\n".join(context_parts)


if __name__ == "__main__":
    import sys
    kb_dir = os.path.dirname(os.path.abspath(__file__))

    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    else:
        user_query = "What is Khata Transfer?"

    route, chunks = query_kb(kb_dir, user_query)

    console.print("\n[bold cyan]═══ LLM Context Format ═══[/bold cyan]\n")
    context = format_context_for_llm(chunks)
    console.print(context)
