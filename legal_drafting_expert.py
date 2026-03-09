"""
Legal Drafting Expert Agent for Vault KB.

Specialized LLM agent that drafts legal documents using L4 embeddings
and user-uploaded documents as context. Produces full legal document
drafts and handles in-place edits.
"""

import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types

from query import query_kb, format_context_for_llm
from redis_cache import format_history_context, build_router_context

load_dotenv()

# Supported deed types for normalization
DEED_TYPES = {
    "sale deed": "sale_deed",
    "sale agreement": "sale_agreement",
    "gift deed": "gift_deed",
    "will": "will",
    "testament": "will",
    "poa": "power_of_attorney",
    "power of attorney": "power_of_attorney",
    "rectification deed": "rectification_deed",
    "release deed": "release_deed",
    "partition deed": "partition_deed",
}


def _detect_deed_type(question: str, chat_history: list = None) -> str:
    """Detect which deed type the user is asking about."""
    combined = question.lower()
    if chat_history:
        for m in chat_history:
            if m.get("role") == "draft":
                return m.get("deed_type", "")
            combined += " " + m.get("content", "").lower()

    for keyword, deed_type in DEED_TYPES.items():
        if keyword in combined:
            return deed_type

    return "legal_document"


def _get_gemini_client():
    """Initialize Gemini client."""
    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    except (ImportError, AttributeError):
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError("GEMINI_API_KEY not found")

    return genai.Client(api_key=api_key)


def ask_drafting(
    kb_dir: str,
    question: str,
    chat_history: list = None,
    user_name: str = None,
    user_email: str = None,
    uploaded_docs_context: str = "",
    existing_draft: str = "",
) -> dict:
    """
    Generate or edit a legal document draft.

    Args:
        kb_dir: Path to KB directory
        question: User's current message/request
        chat_history: Previous messages for context
        user_name: Authenticated user's name
        user_email: Authenticated user's email
        uploaded_docs_context: Extracted text from user-uploaded documents
        existing_draft: The current draft content (for edits)

    Returns:
        dict with keys: draft, summary, deed_type, assistant_message
    """
    # Detect deed type
    deed_type = _detect_deed_type(question, chat_history)

    # Build chat context for the router
    chat_context = build_router_context(chat_history) if chat_history else ""

    # Retrieve relevant L4 chunks
    route, chunks = query_kb(kb_dir, question, verbose=False, chat_context=chat_context)
    context = format_context_for_llm(chunks) if chunks else ""

    # Build history context
    history_context = format_history_context(chat_history) if chat_history else ""

    # User personalization
    user_line = ""
    if user_name:
        user_line = f"\nThe user's name is {user_name}."
    if user_email:
        user_line += f" Their email is {user_email}."

    # Current server time (IST)
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    time_line = f"\nCurrent date and time: {now.strftime('%d %B %Y, %I:%M %p IST')} (use this for dates in the document instead of placeholders — e.g. execution date, document date)."

    # Uploaded documents section
    uploaded_section = ""
    if uploaded_docs_context:
        uploaded_section = f"""

USER-UPLOADED DOCUMENTS (use these for actual property details, party details, etc.):
{uploaded_docs_context}
"""

    # Existing draft section (for edits)
    draft_section = ""
    if existing_draft:
        draft_section = f"""

CURRENT DRAFT (the user wants to modify this - apply their requested changes and return the COMPLETE updated document):
--- START OF CURRENT DRAFT ---
{existing_draft}
--- END OF CURRENT DRAFT ---
"""

    # Build the prompt
    if existing_draft:
        # Edit mode
        prompt = f"""You are a legal drafting expert specializing in property law in Karnataka, India.{user_line}{time_line}

The user has an existing legal document draft and wants to make changes to it.

INSTRUCTIONS:
- Apply the user's requested changes to the existing draft
- Return the COMPLETE updated document (not just the changes)
- Maintain all legal formatting, clauses, and structure
- Preserve all details that the user hasn't asked to change
- Use proper legal language appropriate for Karnataka property law
{draft_section}{uploaded_section}{history_context}

Legal reference context from knowledge base:
{context}

based on the context and requirements of the deed that the user has asked you to draft, 
understand and parse the relavant named entities/ important information from the user query 
BE AS ACCURATE AS POSSIBLE - DO NOT HALLUCINATE OR MAKE UP NAMES, STATS, ADDRESSES, ENTITIES, DATES, LAWS OR ANY OTHER 
SENSITIVE INFORMATION - THIS IS ABSOLUTELY CRITICAL.
User's edit request: {question}

give a disclaimer in BOLD on top of doc to the user like 
Disclaimer: This is a template for informational purposes. Property transactions involve significant legal and financial implications. It is strongly recommended to have the final draft reviewed by a legal professional and verified against the latest Karnataka Registration rules before execution.

give a disclaimer in BOLD on the bottom of doc to the user like
Disclaimer: This is a template for informational purposes. Property transactions involve significant legal and financial implications. It is strongly recommended to have the final draft reviewed by a legal professional and verified against the latest Karnataka Registration rules before execution.
This doc was generated by Vault-Legal-Assistant, an AI-backed assistant solely for text generation : not an official lawyer/legal consultant in any way, shape or form.
please consult an official before proceeding with any due legalities
Return the COMPLETE updated draft document in markdown format:"""

    else:
        # New draft mode
        deed_display = deed_type.replace("_", " ").title()
        prompt = f"""You are a legal drafting expert specializing in property law in Karnataka, India.{user_line}{time_line}

Your task is to draft a complete, legally sound {deed_display} document.

INSTRUCTIONS:
- Draft a COMPLETE, production-ready legal document
- Use proper Indian legal formatting with numbered clauses
- Include all standard sections: parties, recitals, operative clauses, schedules, witness section
- Use language appropriate for Karnataka property registration
- If user has uploaded documents (previous deeds, ID documents), extract and use relevant details (names, addresses, survey numbers, etc.)
- If specific details are not available, use clear placeholders like [SELLER_NAME], [PROPERTY_ADDRESS], [SURVEY_NUMBER] etc.
- Include standard legal boilerplate appropriate for the deed type
- Format the document in clean markdown with proper headings and numbered clauses
- The document should be ready for a lawyer to review and finalize
{uploaded_section}{history_context}

Legal reference context from knowledge base (use for structure, required clauses, and legal requirements):
{context}
based on the context and requirements of the deed that the user has asked you to draft, 
understand and parse the relavant named entities/ important information from the user query 
BE AS ACCURATE AS POSSIBLE - DO NOT HALLUCINATE OR MAKE UP NAMES, STATS, ADDRESSES, ENTITIES, DATES, LAWS OR ANY OTHER 
SENSITIVE INFORMATION - THIS IS ABSOLUTELY CRITICAL.

give a disclaimer in BOLD on top of doc to the user like 
Disclaimer: This is a template for informational purposes. Property transactions involve significant legal and financial implications. It is strongly recommended to have the final draft reviewed by a legal professional and verified against the latest Karnataka Registration rules before execution.

give a disclaimer in BOLD on the bottom of doc to the user like
Disclaimer: This is a template for informational purposes. Property transactions involve significant legal and financial implications. It is strongly recommended to have the final draft reviewed by a legal professional and verified against the latest Karnataka Registration rules before execution.
This doc was generated by Vault-Legal-Assistant, an AI-backed assistant solely for text generation : not an official lawyer/legal consultant in any way, shape or form.
please consult an official before proceeding with any due legalities

User's request: {question}

Draft the complete {deed_display} document in markdown format:"""

    # Generate with Gemini
    client = _get_gemini_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    draft_content = response.text

    # Generate a brief summary for Redis cache (not the full draft)
    summary_prompt = f"""Summarize this legal document draft in ONE sentence (under 100 words).
Include: document type, key parties (if known), and property details (if known).

Document:
{draft_content[:2000]}

One-sentence summary:"""

    try:
        summary_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=summary_prompt,
        )
        summary = summary_response.text.strip()
    except Exception:
        summary = f"{deed_type.replace('_', ' ').title()} draft generated"

    # Build a short assistant message (shown in chat, not the canvas)
    if existing_draft:
        assistant_message = f"I've updated the {deed_type.replace('_', ' ')} draft with your requested changes. You can see the updated document in the canvas above."
    else:
        assistant_message = f"I've drafted a {deed_type.replace('_', ' ')} for you. The document is displayed in the canvas above. You can ask me to make any changes — just describe what you'd like modified."

    return {
        "draft": draft_content,
        "summary": summary,
        "deed_type": deed_type,
        "assistant_message": assistant_message,
    }
