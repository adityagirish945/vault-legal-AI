"""
Query Router for Vault KB using LLM classification.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Collection names (must match ingest.py)
COLLECTION_L1 = "vault_l1_legal"
COLLECTION_L2 = "vault_l2_services"
COLLECTION_L3 = "vault_l3_discrepancies"


@dataclass
class RouteResult:
    """Result of query routing."""
    intent: str
    collections: list[str]
    confidence: float
    reason: str


def route_query(query: str) -> RouteResult:
    """Use LLM to classify query and route to appropriate collections."""
    
    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    except (ImportError, AttributeError):
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        # Fallback to simple routing if no API key
        return RouteResult("general", [COLLECTION_L1], 0.5, "Fallback routing")
    
    client = genai.Client(api_key=api_key)
    
    prompt = f"""Classify this user query about property services in Bangalore into ONE category:

CATEGORIES:
1. general - Pure legal/process questions (What is X? How does Y work? Legal requirements, documents, procedures)
2. service - Questions about Vault PropTech's services, pricing, booking, or offerings
3. issue - Problems, rejections, delays, complaints, discrepancies, or troubleshooting

QUERY: "{query}"

Respond ONLY in this format:
CATEGORY: [general OR service OR issue]
CONFIDENCE: [0.0-1.0]
REASON: [brief explanation]"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt
        )
        text = response.text.strip()
    except Exception:
        # Fallback on API error
        return RouteResult("general", [COLLECTION_L1], 0.5, "API error fallback")
    
    # Parse response
    category = "general"
    confidence = 0.7
    reason = "LLM classification"
    
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip().lower()
        elif line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except:
                confidence = 0.7
        elif line.startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    
    # Map to collections
    collection_map = {
        "general": [COLLECTION_L1],
        "service": [COLLECTION_L2, COLLECTION_L3],
        "issue": [COLLECTION_L1, COLLECTION_L2, COLLECTION_L3],
    }
    
    collections = collection_map.get(category, [COLLECTION_L1])
    
    return RouteResult(
        intent=category,
        collections=collections,
        confidence=confidence,
        reason=reason,
    )


if __name__ == "__main__":
    """Test the LLM router."""
    test_queries = [
        "What is Khata Transfer?",
        "How much does Vault charge for E-Khata?",
        "My E-Khata application was rejected, what should I do?",
        "What documents are needed for property registration?",
        "I need help with BESCOM name change",
        "Why is my Khata transfer stuck in pending?",
        "What is the legal process for MODT cancellation and can Vault help?",
        "Can Vault help with due diligence?",
        "The property tax portal shows wrong owner name",
    ]

    for q in test_queries:
        result = route_query(q)
        print(f"\nQ: {q}")
        print(f"  Intent: {result.intent} (confidence: {result.confidence:.2f})")
        print(f"  Collections: {result.collections}")
        print(f"  Reason: {result.reason}")
