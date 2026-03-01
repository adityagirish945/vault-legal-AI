#!/usr/bin/env python3
"""
Vault KB — ChromaDB Embedding System

CLI entry point for ingesting the knowledge base and querying it.

Usage:
    python setup.py ingest     — Embed all KB documents into ChromaDB
    python setup.py query "your question here"  — Query the KB
    python setup.py ask "your question here"    — Ask LLM with RAG
    python setup.py stats      — Show collection statistics
    python setup.py test       — Run system tests
"""

import os
import sys


def main():
    kb_dir = os.path.dirname(os.path.abspath(__file__))

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "ingest":
        from ingest import run_ingestion
        run_ingestion(kb_dir)

    elif command == "query":
        if len(sys.argv) < 3:
            print("Usage: python setup.py query \"your question here\"")
            sys.exit(1)
        user_query = " ".join(sys.argv[2:])
        from query import query_kb
        query_kb(kb_dir, user_query)

    elif command == "stats":
        from ingest import get_stats
        get_stats(kb_dir)

    elif command == "test":
        from test_system import run_tests
        run_tests(kb_dir)

    elif command == "ask":
        if len(sys.argv) < 3:
            print("Usage: python setup.py ask \"your question here\"")
            sys.exit(1)
        question = " ".join(sys.argv[2:])
        from llm import ask
        ask(kb_dir, question)

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
