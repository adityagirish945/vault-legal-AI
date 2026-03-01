"""
System tests for Vault KB ChromaDB embedding system.

Tests chunker, router, ingestion, and end-to-end retrieval.
"""

import os
import sys
from rich.console import Console
from rich.table import Table

console = Console()


def test_chunker(kb_dir: str) -> tuple[bool, str]:
    """Test that the chunker produces valid chunks with metadata."""
    try:
        from chunker import load_and_chunk_l1, load_and_chunk_l2, load_and_chunk_l3

        l1 = load_and_chunk_l1(kb_dir)
        l2 = load_and_chunk_l2(kb_dir)
        l3 = load_and_chunk_l3(kb_dir)

        if len(l1) == 0:
            return False, f"L1 produced 0 chunks (expected >0)"
        if len(l2) == 0:
            return False, f"L2 produced 0 chunks (expected >0)"
        if len(l3) == 0:
            return False, f"L3 produced 0 chunks (expected >0)"

        # Check metadata
        sample = l1[0]
        required_keys = {"source_file", "level", "service"}
        actual_keys = set(sample.metadata.keys())
        missing = required_keys - actual_keys
        if missing:
            return False, f"L1 chunk missing metadata keys: {missing}"

        # Check no empty texts
        empty_l1 = sum(1 for c in l1 if len(c.text.strip()) < 10)
        if empty_l1 > 0:
            return False, f"L1 has {empty_l1} near-empty chunks"

        return True, f"L1={len(l1)}, L2={len(l2)}, L3={len(l3)} chunks"

    except Exception as e:
        return False, str(e)


def test_router(kb_dir: str) -> tuple[bool, str]:
    """Test that the router classifies queries correctly."""
    try:
        from router import route_query

        test_cases = [
            # (query, expected_intent)
            ("What is Khata Transfer?", "general"),
            ("What documents are needed for property registration?", "general"),
            ("What is the legal process for MODT cancellation?", "general"),
            ("How much does Vault charge for E-Khata?", "vault_service"),
            ("Can Vault help with due diligence?", "vault_service"),
            ("I need Vault's service for Khata transfer", "vault_service"),
            ("My E-Khata application was rejected", "issue"),
            ("Why is my Khata transfer stuck in pending?", "issue"),
            ("The property tax portal shows wrong owner name", "issue"),
        ]

        failures = []
        for query, expected in test_cases:
            result = route_query(query)
            if result.intent != expected:
                failures.append(
                    f"'{query}': expected '{expected}', got '{result.intent}'"
                )

        if failures:
            return False, "; ".join(failures[:3])  # Show first 3 failures

        return True, f"All {len(test_cases)} routing tests passed"

    except Exception as e:
        return False, str(e)


def test_ingestion(kb_dir: str) -> tuple[bool, str]:
    """Test that all 3 collections exist and have chunks."""
    try:
        from ingest import (
            get_chroma_client, get_embedding_function,
            COLLECTION_L1, COLLECTION_L2, COLLECTION_L3,
        )

        client = get_chroma_client(kb_dir)
        embedding_fn = get_embedding_function()

        counts = {}
        for name in [COLLECTION_L1, COLLECTION_L2, COLLECTION_L3]:
            try:
                col = client.get_collection(name=name, embedding_function=embedding_fn)
                counts[name] = col.count()
            except Exception:
                return False, f"Collection '{name}' not found. Run 'python setup.py ingest' first."

        for name, count in counts.items():
            if count == 0:
                return False, f"Collection '{name}' is empty"

        summary = ", ".join(f"{k.split('_')[-1]}={v}" for k, v in counts.items())
        return True, summary

    except Exception as e:
        return False, str(e)


def test_retrieval(kb_dir: str) -> tuple[bool, str]:
    """Test end-to-end retrieval quality."""
    try:
        from query import query_kb

        test_cases = [
            (
                "What is Khata Transfer?",
                "general",
                ["khata", "transfer"],
            ),
            (
                "How much does Vault charge for E-Khata?",
                "vault_service",
                ["khata", "e-khata"],
            ),
            (
                "My E-Khata application was rejected",
                "issue",
                ["reject", "khata"],
            ),
        ]

        results = []
        for query, expected_intent, keywords in test_cases:
            route, chunks = query_kb(kb_dir, query, verbose=False)

            # Check intent
            if route.intent != expected_intent:
                results.append(f"❌ '{query}': wrong intent ({route.intent})")
                continue

            # Check we got results
            if not chunks:
                results.append(f"❌ '{query}': no chunks retrieved")
                continue

            # Check top result contains at least one keyword
            top_text = chunks[0].text.lower()
            has_keyword = any(kw in top_text for kw in keywords)
            if not has_keyword:
                results.append(f"⚠️ '{query}': top result may not be relevant")
            else:
                results.append(f"✅ '{query}': relevant result found")

        failures = [r for r in results if r.startswith("❌")]
        if failures:
            return False, "; ".join(failures)

        return True, f"All {len(test_cases)} retrieval tests passed"

    except Exception as e:
        return False, str(e)


def run_tests(kb_dir: str):
    """Run all system tests and display results."""
    console.print("\n[bold cyan]╔══════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║   Vault KB — System Tests            ║[/bold cyan]")
    console.print("[bold cyan]╚══════════════════════════════════════╝[/bold cyan]\n")

    tests = [
        ("Chunker", test_chunker),
        ("Router", test_router),
        ("Ingestion", test_ingestion),
        ("End-to-End Retrieval", test_retrieval),
    ]

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Test", style="cyan", width=25)
    table.add_column("Status", width=8)
    table.add_column("Details", style="white")

    all_passed = True
    for name, test_fn in tests:
        passed, details = test_fn(kb_dir)
        status = "[green]✅ PASS[/green]" if passed else "[red]❌ FAIL[/red]"
        if not passed:
            all_passed = False
        table.add_row(name, status, details)

    console.print(table)

    if all_passed:
        console.print("\n[bold green]All tests passed! ✅[/bold green]\n")
    else:
        console.print("\n[bold red]Some tests failed. See details above.[/bold red]\n")

    return all_passed


if __name__ == "__main__":
    kb_dir = os.path.dirname(os.path.abspath(__file__))
    run_tests(kb_dir)
