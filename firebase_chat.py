"""Firebase chat history management — keyed by user email.

Supports both regular chat messages and mutable legal document drafts.
Drafts exist as ONE message per chat that gets mutated in-place on edits.
"""
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from redis_cache import cache_chat_history, get_cached_history, cache_draft_summary

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


# ── Draft Management ─────────────────────────────────────────────────────────

def save_draft(user_email, user_name, chat_id, draft_content, deed_type, 
               summary, chat_name, doc_link=None):
    """
    Save or update a draft in Firebase.
    
    The draft exists as ONE message with role='draft' in the chat's messages.
    If a draft message already exists, it is MUTATED IN PLACE (not appended).
    This gives the Gemini-like canvas behavior where edits update the same block.
    """
    db = init_firebase()
    doc_ref = db.collection("ChatHistory").document(user_email)
    
    # Load existing data
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if "chats" not in data:
            data["chats"] = {}
    else:
        data = {"chats": {}}
    
    data["Name"] = user_name
    data["email"] = user_email
    
    # Get or create the chat
    if chat_id not in data["chats"]:
        data["chats"][chat_id] = {
            "chat_name": chat_name,
            "messages": [],
            "updated_at": datetime.utcnow(),
        }
    
    chat = data["chats"][chat_id]
    messages = chat.get("messages", [])
    
    # Build the draft message
    draft_message = {
        "role": "draft",
        "content": draft_content,
        "deed_type": deed_type,
        "summary": summary,
        "doc_link": doc_link or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    # Find existing draft message and mutate it, or append new one
    draft_index = None
    for i, msg in enumerate(messages):
        if msg.get("role") == "draft":
            draft_index = i
            break
    
    if draft_index is not None:
        # Mutate in place — this is the key behavior
        messages[draft_index] = draft_message
    else:
        # First draft in this chat — append it
        messages.append(draft_message)
    
    chat["messages"] = messages
    chat["updated_at"] = datetime.utcnow()
    chat["chat_name"] = chat_name
    
    data["chats"][chat_id] = chat
    doc_ref.set(data)
    
    # Cache only the summary + link in Redis (not the full draft)
    cache_draft_summary(user_email, chat_id, summary, doc_link)
    
    # Also update the full message cache
    cache_chat_history(user_email, chat_id, messages)


def get_draft(user_email, chat_id):
    """
    Get the current draft message from a chat, if one exists.
    
    Returns:
        The draft message dict, or None if no draft exists.
    """
    chat_data = load_chat(user_email, chat_id)
    if not chat_data or "messages" not in chat_data:
        return None
    
    for msg in chat_data["messages"]:
        if msg.get("role") == "draft":
            return msg
    
    return None
