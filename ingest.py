"""
ChromaDB Ingestion Pipeline for Vault KB.

Creates 3 persistent collections (L1, L2, L3) and populates them
with semantically chunked documents from the knowledge base.
"""

import os
import sys
import time

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from chunker import (
    load_and_chunk_l1,
    load_and_chunk_l2,
    load_and_chunk_l3,
)

console = Console()

# Collection names
COLLECTION_L1 = "vault_l1_legal"
COLLECTION_L2 = "vault_l2_services"
COLLECTION_L3 = "vault_l3_discrepancies"

# Embedding model
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def get_chroma_client(kb_dir: str) -> chromadb.PersistentClient:
    """Get or create a persistent ChromaDB client."""
    db_path = os.path.join(kb_dir, "chroma_db")
    return chromadb.PersistentClient(path=db_path)


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    """Get the sentence transformer embedding function."""
    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
    )


def ingest_chunks(
    client: chromadb.PersistentClient,
    collection_name: str,
    chunks: list,
    embedding_fn: SentenceTransformerEmbeddingFunction,
) -> int:
    """
    Ingest chunks into a ChromaDB collection.
    Recreates the collection if it already exists.

    Returns:
        Number of chunks ingested.
    """
    # Delete existing collection if present
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    if not chunks:
        console.print(f"  [yellow]⚠ No chunks to ingest for {collection_name}[/yellow]")
        return 0

    # ChromaDB has a batch size limit; process in batches of 100
    batch_size = 100
    total = len(chunks)

    # Deduplicate chunks globally by chunk_id before batching
    seen_ids = set()
    unique_chunks = []
    for c in chunks:
        if c.chunk_id not in seen_ids:
            seen_ids.add(c.chunk_id)
            unique_chunks.append(c)
    total = len(unique_chunks)

    for i in range(0, total, batch_size):
        batch = unique_chunks[i:i + batch_size]

        ids = [c.chunk_id for c in batch]
        documents = [c.text for c in batch]
        metadatas = []
        for c in batch:
            # ChromaDB metadata values must be str, int, float, or bool
            clean_meta = {}
            for k, v in c.metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    clean_meta[k] = v
                else:
                    clean_meta[k] = str(v)
            metadatas.append(clean_meta)

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    return total


def run_ingestion(kb_dir: str):
    """Run the full ingestion pipeline."""
    console.print("\n[bold cyan]╔══════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Vault KB — ChromaDB Ingestion Pipeline  ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════════╝[/bold cyan]\n")

    start_time = time.time()

    # Initialize embedding function
    console.print("[bold]1. Loading embedding model...[/bold]")
    embedding_fn = get_embedding_function()
    console.print(f"   ✅ Model: [green]{EMBEDDING_MODEL}[/green]\n")

    # Initialize ChromaDB client
    console.print("[bold]2. Initializing ChromaDB...[/bold]")
    client = get_chroma_client(kb_dir)
    db_path = os.path.join(kb_dir, "chroma_db")
    console.print(f"   ✅ Persistent DB: [green]{db_path}[/green]\n")

    # Chunk and ingest each level
    results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[bold]{task.completed}/{task.total}"),
        console=console,
    ) as progress:

        # L1 — Legal expertise
        task = progress.add_task("[cyan]L1: Chunking legal expertise docs...", total=3)
        progress.update(task, completed=0)

        l1_chunks = load_and_chunk_l1(kb_dir)
        progress.update(task, completed=1, description="[cyan]L1: Embedding & ingesting...")

        count = ingest_chunks(client, COLLECTION_L1, l1_chunks, embedding_fn)
        results["L1"] = count
        progress.update(task, completed=3, description=f"[green]L1: ✅ {count} chunks ingested")

        # L2 — Vault service info
        task = progress.add_task("[cyan]L2: Chunking Vault service docs...", total=3)
        progress.update(task, completed=0)

        l2_chunks = load_and_chunk_l2(kb_dir)
        progress.update(task, completed=1, description="[cyan]L2: Embedding & ingesting...")

        count = ingest_chunks(client, COLLECTION_L2, l2_chunks, embedding_fn)
        results["L2"] = count
        progress.update(task, completed=3, description=f"[green]L2: ✅ {count} chunks ingested")

        # L3 — Discrepancies
        task = progress.add_task("[cyan]L3: Chunking discrepancy docs...", total=3)
        progress.update(task, completed=0)

        l3_chunks = load_and_chunk_l3(kb_dir)
        progress.update(task, completed=1, description="[cyan]L3: Embedding & ingesting...")

        count = ingest_chunks(client, COLLECTION_L3, l3_chunks, embedding_fn)
        results["L3"] = count
        progress.update(task, completed=3, description=f"[green]L3: ✅ {count} chunks ingested")

    elapsed = time.time() - start_time

    # Summary table
    console.print()
    table = Table(title="Ingestion Summary", show_header=True, header_style="bold magenta")
    table.add_column("Level", style="cyan")
    table.add_column("Collection", style="white")
    table.add_column("Chunks", justify="right", style="green")

    table.add_row("L1 — Legal Expertise", COLLECTION_L1, str(results.get("L1", 0)))
    table.add_row("L2 — Vault Services", COLLECTION_L2, str(results.get("L2", 0)))
    table.add_row("L3 — Discrepancies", COLLECTION_L3, str(results.get("L3", 0)))
    table.add_row(
        "[bold]Total[/bold]", "", f"[bold]{sum(results.values())}[/bold]"
    )

    console.print(table)
    console.print(f"\n⏱  Completed in [bold]{elapsed:.1f}s[/bold]\n")

    return results


def get_stats(kb_dir: str):
    """Print statistics for all collections."""
    client = get_chroma_client(kb_dir)
    embedding_fn = get_embedding_function()

    console.print("\n[bold cyan]Collection Statistics[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Collection", style="cyan")
    table.add_column("Documents", justify="right", style="green")
    table.add_column("Metadata Keys", style="white")

    for name in [COLLECTION_L1, COLLECTION_L2, COLLECTION_L3]:
        try:
            col = client.get_collection(name=name, embedding_function=embedding_fn)
            count = col.count()
            # Get a sample to show metadata keys
            sample = col.peek(limit=1)
            meta_keys = list(sample["metadatas"][0].keys()) if sample["metadatas"] else []
            table.add_row(name, str(count), ", ".join(meta_keys))
        except Exception as e:
            table.add_row(name, "[red]Not found[/red]", str(e))

    console.print(table)


if __name__ == "__main__":
    kb_dir = os.path.dirname(os.path.abspath(__file__))
    run_ingestion(kb_dir)
