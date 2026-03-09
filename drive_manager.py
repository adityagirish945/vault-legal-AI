"""
Google Drive integration for Vault Legal AI.

Handles file uploads to shared Drive folder and Google Docs export
using the user's OAuth token.

Drive structure:
    chatDocs/{username_gmailID}/{deed_name}/...docs...
"""

import os
import io
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account

# Shared root folder ID for chatDocs
CHAT_DOCS_FOLDER_ID = "17zm6e1pSdzWxRK3kmVd5ZKx13pg2Qo38"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


def _get_service_account_creds():
    """Get service account credentials from secrets or local file."""
    try:
        import streamlit as st
        if "drive" in st.secrets:
            cred_dict = dict(st.secrets["drive"])
            return service_account.Credentials.from_service_account_info(
                cred_dict, scopes=SCOPES
            )
    except (ImportError, KeyError, AttributeError):
        pass

    # Local dev fallback
    cred_path = os.path.join(os.path.dirname(__file__), "L1", "drive-auth.json")
    if os.path.exists(cred_path):
        return service_account.Credentials.from_service_account_file(
            cred_path, scopes=SCOPES
        )

    raise ValueError("Drive service account credentials not found")


def get_drive_service():
    """Initialize Google Drive API client using service account."""
    creds = _get_service_account_creds()
    return build("drive", "v3", credentials=creds)


def _find_folder(service, name, parent_id):
    """Find a folder by name under a parent folder."""
    query = (
        f"name = '{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"trashed = false"
    )
    results = service.files().list(
        q=query, spaces="drive", fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(service, name, parent_id):
    """Create a folder under a parent folder."""
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def get_or_create_user_folder(user_email, deed_name):
    """
    Get or create the folder structure:
    chatDocs/{username_gmailID}/{deed_name}/

    Returns the deed folder ID.
    """
    service = get_drive_service()

    # Build user folder name: e.g. "aditya_adityadeepa634"
    email_parts = user_email.split("@")
    username = email_parts[0] if email_parts else user_email
    user_folder_name = f"{username}_{email_parts[0]}" if len(email_parts) > 1 else username

    # Find or create user folder
    user_folder_id = _find_folder(service, user_folder_name, CHAT_DOCS_FOLDER_ID)
    if not user_folder_id:
        user_folder_id = _create_folder(service, user_folder_name, CHAT_DOCS_FOLDER_ID)

    # Normalize deed name for folder
    deed_folder_name = deed_name.lower().replace(" ", "_")

    # Find or create deed folder
    deed_folder_id = _find_folder(service, deed_folder_name, user_folder_id)
    if not deed_folder_id:
        deed_folder_id = _create_folder(service, deed_folder_name, user_folder_id)

    return deed_folder_id


def upload_file(user_email, deed_name, file_bytes, filename, mime_type):
    """
    Upload a file (PDF/image) to the user's deed folder on Drive.

    Returns:
        dict with file_id and web_view_link
    """
    service = get_drive_service()
    folder_id = get_or_create_user_folder(user_email, deed_name)

    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        resumable=True,
    )

    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
    ).execute()

    return {
        "file_id": uploaded["id"],
        "web_view_link": uploaded.get("webViewLink", ""),
        "filename": filename,
    }


def list_user_files(user_email, deed_name):
    """List all files in the user's deed folder."""
    service = get_drive_service()

    try:
        folder_id = get_or_create_user_folder(user_email, deed_name)
    except Exception:
        return []

    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, mimeType, webViewLink)",
    ).execute()

    return results.get("files", [])


def get_file_bytes(file_id):
    """Download file content as bytes from Drive."""
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)

    buffer = io.BytesIO()
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    buffer.seek(0)
    return buffer.read()


def extract_text_with_gemini(file_bytes, mime_type, filename="document"):
    """
    Use Gemini 2.5 Flash's native multimodal OCR to extract text
    from uploaded PDFs and images.
    """
    from google import genai
    from google.genai import types

    # Get API key
    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    except (ImportError, AttributeError):
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return f"[Could not extract text from {filename}: no API key]"

    client = genai.Client(api_key=api_key)

    # Build the multimodal content
    file_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

    prompt = (
        "Extract ALL text content from this document accurately. "
        "Preserve the structure, formatting, and all details including names, "
        "addresses, dates, amounts, survey numbers, and legal descriptions. "
        "If this is an identity document (Aadhaar, PAN), extract all visible fields. "
        "Return only the extracted text, no commentary."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[file_part, prompt],
        )
        return response.text
    except Exception as e:
        return f"[Error extracting text from {filename}: {str(e)}]"


def export_to_google_doc(title, content, user_access_token):
    """
    Create a Google Doc using the USER's OAuth token (not service account).
    This creates the doc in the user's personal Drive.

    Args:
        title: Document title
        content: Markdown content of the draft
        user_access_token: The user's OAuth access token

    Returns:
        URL of the created Google Doc
    """
    import requests

    # Create the document via Docs API
    doc_response = requests.post(
        "https://docs.googleapis.com/v1/documents",
        headers={
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
        },
        json={"title": title},
        timeout=15,
    )

    if not doc_response.ok:
        raise Exception(f"Failed to create Google Doc: {doc_response.text}")

    doc_id = doc_response.json()["documentId"]
    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

    # Insert the content into the document
    # Convert markdown to plain text with basic formatting
    plain_content = content.replace("**", "").replace("##", "").replace("# ", "")

    requests_body = {
        "requests": [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": plain_content,
                }
            }
        ]
    }

    update_response = requests.post(
        f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
        headers={
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json",
        },
        json=requests_body,
        timeout=30,
    )

    if not update_response.ok:
        # Doc was created but content insert failed — still return URL
        pass

    return doc_url
