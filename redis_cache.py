"""Redis cache for chat history context."""
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

def format_history_context(messages):
    """Format chat history for LLM context."""
    if not messages:
        return ""
    
    history = "\n".join([
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages[:-1]  # Exclude current message
    ])
    return f"\n\nPrevious conversation:\n{history}\n" if history else ""
