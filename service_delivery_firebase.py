"""
Firebase helpers for the Service Delivery AI Agent.

Responsibilities:
- Look up user profile from `vaultUsers` by phoneNumber field
- Save / load service-delivery chat history (under ChatHistory, tagged as service_delivery)
- Write escalation flags to `vaultAIescalations`
"""

from datetime import datetime
from firebase_chat import init_firebase   # reuse the same initialised client


# ── vaultUsers Lookup ────────────────────────────────────────────────────────

def get_vault_user_by_phone(phone_number: str) -> dict | None:
    """
    Lookup a user document from the `vaultUsers` collection using the
    `phoneNumber` field value.

    Args:
        phone_number: E.164 or local format, e.g. '+919876543210'

    Returns:
        The user dict if found, else None.
    """
    db = init_firebase()
    try:
        results = (
            db.collection("vaultUsers")
            .where("phoneNumber", "==", phone_number)
            .limit(1)
            .get()
        )
        for doc in results:
            data = doc.to_dict()
            data["_doc_id"] = doc.id
            return data
    except Exception:
        pass
    return None


# ── Service Delivery Chat History ────────────────────────────────────────────

def save_sd_chat(phone_number: str, chat_id: str, messages: list, chat_name: str):
    """
    Save a service-delivery chat session to Firestore.

    Structure:
        SDChatHistory/{phone_number}
            chats:
                {chat_id}:
                    chat_name: str
                    messages: list
                    updated_at: timestamp
    """
    db = init_firebase()
    doc_ref = db.collection("SDChatHistory").document(phone_number)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        if "chats" not in data:
            data["chats"] = {}
    else:
        data = {"chats": {}, "phoneNumber": phone_number}

    data["chats"][chat_id] = {
        "chat_name": chat_name,
        "messages": messages,
        "updated_at": datetime.utcnow(),
    }
    doc_ref.set(data)


def load_sd_chats(phone_number: str) -> list:
    """Return list of service-delivery chat metadata for a phone number."""
    db = init_firebase()
    doc = db.collection("SDChatHistory").document(phone_number).get()
    if not doc.exists:
        return []
    chats = doc.to_dict().get("chats", {})
    return sorted(
        [
            {"chat_id": cid, "chat_name": d["chat_name"], "updated_at": d["updated_at"]}
            for cid, d in chats.items()
        ],
        key=lambda x: x["updated_at"],
        reverse=True,
    ) if chats else []


def load_sd_chat(phone_number: str, chat_id: str) -> dict | None:
    """Load messages for a specific service-delivery chat."""
    db = init_firebase()
    doc = db.collection("SDChatHistory").document(phone_number).get()
    if not doc.exists:
        return None
    chats = doc.to_dict().get("chats", {})
    return chats.get(chat_id)


def delete_sd_chat(phone_number: str, chat_id: str):
    """Delete a service-delivery chat."""
    from firebase_admin import firestore as _fs
    db = init_firebase()
    db.collection("SDChatHistory").document(phone_number).update(
        {f"chats.{chat_id}": _fs.DELETE_FIELD}
    )


# ── Escalation Flags ─────────────────────────────────────────────────────────

def write_escalation(
    phone_number: str,
    escalation_type: str,          # "POC" or "CT" (Control Tower)
    user_data: dict,
    chat_id: str,
    last_messages: list,
):
    """
    Write an escalation flag to the `vaultAIescalations` collection.

    Fields written:
        phoneNumber, escalationType, POCescalate / CTescalate: True,
        userData, chatId, lastMessages, createdAt
    """
    db = init_firebase()
    doc_ref = db.collection("vaultAIescalations").document()

    payload = {
        "phoneNumber": phone_number,
        "escalationType": escalation_type,
        "POCescalate": escalation_type == "POC",
        "CTescalate": escalation_type == "CT",
        "userData": user_data or {},
        "chatId": chat_id,
        "lastMessages": last_messages[-5:] if last_messages else [],   # last 5 msgs for context
        "createdAt": datetime.utcnow(),
        "resolved": False,
    }
    doc_ref.set(payload)
    return doc_ref.id
