"""
Query Router for Vault KB using LLM classification.
Now with stateful routing (accepts chat history context)
and a 'drafting' category for legal document generation.
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
COLLECTION_L4 = "vault_l4_drafting"


@dataclass
class RouteResult:
    """Result of query routing."""
    intent: str
    collections: list[str]
    confidence: float
    reason: str
    is_drafting: bool = False


def route_query(query: str, chat_context: str = "", is_drafting_active: bool = False) -> RouteResult:
    """
    Use LLM to classify query and route to appropriate collections.

    Args:
        query: The user's current message
        chat_context: Formatted chat history from Redis for stateful routing
        is_drafting_active: Whether user is currently in an active drafting session
    """

    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    except (ImportError, AttributeError):
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        # Fallback to simple routing if no API key
        return RouteResult("general", [COLLECTION_L1], 0.5, "Fallback routing", is_drafting=False)

    client = genai.Client(api_key=api_key)

    # Build context section for the prompt
    context_section = ""
    if chat_context:
        context_section = f"""
CONVERSATION CONTEXT (use this to understand follow-up messages and user intent):
{chat_context}
"""

    # Build drafting guidance based on current state
    if is_drafting_active:
        drafting_guidance = """4. drafting - User wants to DRAFT, CREATE, WRITE, PREPARE, or EDIT a legal document. This includes:
   sale deed, sale agreement, gift deed, Will, Power of Attorney (PoA),
   rectification deed, release deed, partition deed.
   The user is CURRENTLY IN an active drafting session, so also route here if they are
   continuing the draft (e.g. editing, adding clauses, changing names/details, providing
   property info, or giving party details for the draft)."""
    else:
        drafting_guidance = """4. drafting - User EXPLICITLY wants to DRAFT, CREATE, WRITE, PREPARE, or GENERATE a legal document.
   They must clearly express intent to create a document (e.g. "draft a sale deed", "prepare a gift deed").
   Do NOT classify as drafting if the user is merely mentioning a property name, asking about
   a property, or providing general information without explicitly asking for a document to be created."""

    prompt = f"""Classify this user query about property services in Bangalore into ONE category:

CATEGORIES:
1. general - Pure legal/process questions (What is X? How does Y work? Legal requirements, documents, procedures)
2. service - Questions about Vault PropTech's services, pricing, booking, or offerings
3. issue - Problems, rejections, delays, complaints, discrepancies, or troubleshooting, FAQs
{drafting_guidance}
{context_section}
QUERY: "{query}"

Respond ONLY in this format:
CATEGORY: [general OR service OR issue OR drafting]
CONFIDENCE: [0.0-1.0]
REASON: [brief explanation]"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
        "general": [COLLECTION_L1, COLLECTION_L2],
        "service": [COLLECTION_L2],  # Only L2 for services
        "issue": [COLLECTION_L1, COLLECTION_L2, COLLECTION_L3],
        "drafting": [COLLECTION_L4],
    }

    collections = collection_map.get(category, [COLLECTION_L1])
    is_drafting = category == "drafting"

    return RouteResult(
        intent=category,
        collections=collections,
        confidence=confidence,
        reason=reason,
        is_drafting=is_drafting,
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
        # Drafting queries
        "I need to draft a sale deed for my property",
        "Can you help me write a gift deed?",
        "Prepare a power of attorney document",
        "I want to create a will",
        "Help me prepare a sale agreement",
    ]

    for q in test_queries:
        result = route_query(q)
        marker = " 📝" if result.is_drafting else ""
        print(f"\nQ: {q}")
        print(f"  Intent: {result.intent} (confidence: {result.confidence:.2f}){marker}")
        print(f"  Collections: {result.collections}")
        print(f"  Reason: {result.reason}")
