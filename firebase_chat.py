"""Firebase chat history management — keyed by user email."""
import os
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


def save_chat(user_email, user_name, chat_id, messages, chat_name):
    """Save chat to Firestore under the user's email document.
    
    Firestore structure:
        ChatHistory/{user_email}
            Name: "Aditya"
            email: "adityadeepa634@gmail.com"
            chats:
                {chat_id}:
                    chat_name: "..."
                    messages: [...]
                    updated_at: timestamp
    """
    db = init_firebase()
    doc_ref = db.collection("ChatHistory").document(user_email)
    
    # Get existing data or create new
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if "chats" not in data:
            data["chats"] = {}
    else:
        data = {"chats": {}}
    
    # Always set the top-level user fields
    data["Name"] = user_name
    data["email"] = user_email
    
    # Update the specific chat
    data["chats"][chat_id] = {
        "chat_name": chat_name,
        "messages": messages,
        "updated_at": datetime.utcnow()
    }
    
    # Save back to Firestore
    doc_ref.set(data)
    
    # Update cache immediately
    cache_chat_history(user_email, chat_id, messages)

def load_chats(user_email):
    """Load chat list (metadata only) for a user."""
    db = init_firebase()
    doc = db.collection("ChatHistory").document(user_email).get()
    if not doc.exists:
        return []
    
    chats = doc.to_dict().get("chats", {})
    return sorted([
        {"chat_id": cid, "chat_name": data["chat_name"], "updated_at": data["updated_at"]}
        for cid, data in chats.items()
    ], key=lambda x: x["updated_at"], reverse=True) if chats else []

def load_chat(user_email, chat_id):
    """Load specific chat messages (lazy load with Redis cache)."""
    # Try cache first
    cached = get_cached_history(user_email, chat_id)
    if cached:
        return {"messages": cached}
    
    # Load from Firebase
    db = init_firebase()
    doc = db.collection("ChatHistory").document(user_email).get()
    if not doc.exists:
        return None
    
    chats = doc.to_dict().get("chats", {})
    chat_data = chats.get(chat_id)
    
    # Cache for next time
    if chat_data and "messages" in chat_data:
        cache_chat_history(user_email, chat_id, chat_data["messages"])
    
    return chat_data

def delete_chat(user_email, chat_id):
    """Delete a chat."""
    db = init_firebase()
    db.collection("ChatHistory").document(user_email).update({
        f"chats.{chat_id}": firestore.DELETE_FIELD
    })
