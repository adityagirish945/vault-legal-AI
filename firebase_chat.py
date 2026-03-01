"""Firebase chat history management."""
import os
import hashlib
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from redis_cache import cache_chat_history, get_cached_history

_db = None

def init_firebase():
    """Initialize Firebase Admin SDK."""
    global _db
    if _db is not None:
        return _db
    
    # Try Streamlit secrets first (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        if "firebase" in st.secrets:
            cred = credentials.Certificate(dict(st.secrets["firebase"]))
        else:
            raise KeyError("firebase not in secrets")
    except (ImportError, KeyError, AttributeError):
        # Local dev fallback: load from JSON file
        cred_path = os.path.join(os.path.dirname(__file__), "L1", "firebase-auth.json")
        cred = credentials.Certificate(cred_path)
    
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    _db = firestore.client()
    return _db

def get_browser_id():
    """Generate persistent browser ID using localStorage.
    
    On first render, streamlit_js_eval returns None because the JS hasn't
    executed yet. We stop and let Streamlit re-run so the JS result
    arrives on the second render cycle. After 3 retries we fall back
    to a server-generated UUID to prevent an infinite blank page.
    """
    import streamlit as st
    from streamlit_js_eval import streamlit_js_eval
    import uuid
    
    # If we already resolved the browser_id this session, return it
    if "browser_id" in st.session_state and st.session_state.browser_id:
        return st.session_state.browser_id
    
    # Track how many times we've tried waiting for JS
    if "bid_retries" not in st.session_state:
        st.session_state.bid_retries = 0
    
    # Try to get from browser's localStorage
    browser_id = streamlit_js_eval(
        js_expressions="localStorage.getItem('vault_browser_id')",
        key="get_bid"
    )
    
    # On first render, streamlit_js_eval returns None (JS not ready).
    # Retry up to 3 times, then fall back to a server-side UUID.
    if browser_id is None:
        st.session_state.bid_retries += 1
        if st.session_state.bid_retries < 3:
            st.stop()
        else:
            browser_id = str(uuid.uuid4())[:16]
    
    # If localStorage had no value (empty string or literal null), generate one
    if not browser_id or browser_id == "null":
        browser_id = str(uuid.uuid4())[:16]
        # Persist to localStorage for future page loads / tabs
        streamlit_js_eval(
            js_expressions=f"localStorage.setItem('vault_browser_id', '{browser_id}')",
            key="set_bid"
        )
    
    # Cache in session state for the rest of this session
    st.session_state.bid_retries = 0
    st.session_state.browser_id = browser_id
    return browser_id

def save_chat(browser_id, chat_id, messages, chat_name):
    """Save chat to Firestore and update cache."""
    db = init_firebase()
    doc_ref = db.collection("ChatHistory").document(browser_id)
    
    # Get existing data or create new
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if "chats" not in data:
            data["chats"] = {}
    else:
        data = {"chats": {}}
    
    # Update the specific chat
    data["chats"][chat_id] = {
        "chat_name": chat_name,
        "messages": messages,
        "updated_at": datetime.utcnow()
    }
    
    # Save back to Firestore
    doc_ref.set(data)
    
    # Update cache immediately
    cache_chat_history(browser_id, chat_id, messages)

def load_chats(browser_id):
    """Load chat list (metadata only) for a browser."""
    db = init_firebase()
    doc = db.collection("ChatHistory").document(browser_id).get()
    if not doc.exists:
        return []
    
    chats = doc.to_dict().get("chats", {})
    return sorted([
        {"chat_id": cid, "chat_name": data["chat_name"], "updated_at": data["updated_at"]}
        for cid, data in chats.items()
    ], key=lambda x: x["updated_at"], reverse=True) if chats else []

def load_chat(browser_id, chat_id):
    """Load specific chat messages (lazy load with Redis cache)."""
    # Try cache first
    cached = get_cached_history(browser_id, chat_id)
    if cached:
        return {"messages": cached}
    
    # Load from Firebase
    db = init_firebase()
    doc = db.collection("ChatHistory").document(browser_id).get()
    if not doc.exists:
        return None
    
    chats = doc.to_dict().get("chats", {})
    chat_data = chats.get(chat_id)
    
    # Cache for next time
    if chat_data and "messages" in chat_data:
        cache_chat_history(browser_id, chat_id, chat_data["messages"])
    
    return chat_data

def delete_chat(browser_id, chat_id):
    """Delete a chat."""
    db = init_firebase()
    db.collection("ChatHistory").document(browser_id).update({
        f"chats.{chat_id}": firestore.DELETE_FIELD
    })
