"""Redis cache for chat history context and draft summaries."""
import os
import json
import redis
from dotenv import load_dotenv

load_dotenv()

_redis_client = None

def get_redis_client():
    """Initialize Redis client."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client

    # Try Streamlit secrets first, then .env fallback
    try:
        import streamlit as st
        redis_url = st.secrets.get("REDIS_URL", os.getenv("REDIS_URL"))
    except (ImportError, AttributeError):
        redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        raise ValueError("REDIS_URL not found in Streamlit secrets or .env")

    _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client

def cache_chat_history(user_email, chat_id, messages):
    """Cache chat history in Redis."""
    client = get_redis_client()
    key = f"chat:{user_email}:{chat_id}"
    client.setex(key, 3600, json.dumps(messages))  # 1 hour TTL

def get_cached_history(user_email, chat_id):
    """Get cached chat history from Redis."""
    client = get_redis_client()
    key = f"chat:{user_email}:{chat_id}"
    data = client.get(key)
    return json.loads(data) if data else None


# ── Router Context (stateful routing) ────────────────────────────────────────

def build_router_context(messages):
    """
    Build a compact context string from chat history for the router.
    Passes the full Redis cache to the router for stateful routing,
    ensuring the router can understand follow-up messages and user intent.
    
    Returns a formatted string with the recent conversation.
    """
    if not messages:
        return ""

    # Include all messages from the session for complete context
    context_lines = []
    for m in messages:
        role = "User" if m.get("role") == "user" else "Assistant"
        content = m.get("content", "")

        # For draft messages, include only the summary to avoid bloating router context
        if m.get("role") == "draft":
            summary = m.get("summary", "")
            deed = m.get("deed_type", "document")
            context_lines.append(f"[Draft generated: {deed} — {summary}]")
            continue

        # Truncate very long assistant responses to keep context focused
        if role == "Assistant" and len(content) > 400:
            content = content[:400] + "..."

        context_lines.append(f"{role}: {content}")

    return "\n".join(context_lines)


def format_history_context(messages):
    """
    Format chat history for LLM context.
    For draft messages, includes only the summary + doc link (not full content).
    """
    if not messages:
        return ""

    history_lines = []
    for m in messages[:-1]:  # Exclude current message
        role = m.get("role", "user")

        if role == "draft":
            # Only include summary and link — NOT the full document
            summary = m.get("summary", "A legal document draft")
            deed = m.get("deed_type", "document")
            doc_link = m.get("doc_link", "")
            link_text = f" (Doc: {doc_link})" if doc_link else ""
            history_lines.append(
                f"[Draft: {deed} — {summary}{link_text}]"
            )
        else:
            display_role = "User" if role == "user" else "Assistant"
            history_lines.append(f"{display_role}: {m.get('content', '')}")

    history = "\n".join(history_lines)
    return f"\n\nPrevious conversation:\n{history}\n" if history else ""


# ── Draft Summary Cache ──────────────────────────────────────────────────────

def cache_draft_summary(user_email, chat_id, summary, doc_link=None):
    """
    Cache only a draft summary + doc link in Redis.
    The full draft lives only in Firebase.
    """
    client = get_redis_client()
    key = f"draft_summary:{user_email}:{chat_id}"
    data = {
        "summary": summary[:500],  # Cap summary length
        "doc_link": doc_link or "",
    }
    client.setex(key, 3600, json.dumps(data))  # 1 hour TTL


def get_cached_draft_summary(user_email, chat_id):
    """Get cached draft summary from Redis."""
    client = get_redis_client()
    key = f"draft_summary:{user_email}:{chat_id}"
    data = client.get(key)
    return json.loads(data) if data else None
