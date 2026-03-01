"""
Vault PropTech - Property Legal Assistant
User-facing chat interface powered by RAG + Gemini
"""

# SQLite3 Patch for Streamlit Cloud (Streamlit uses Debian which has old sqlite3)
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import os
import streamlit as st
from llm import ask, get_gemini_client
from query import query_kb, format_context_for_llm
from firebase_chat import get_browser_id, save_chat, load_chats, load_chat, delete_chat
import uuid

# Page config
st.set_page_config(
    page_title="Vault PropTech Legal Assistant",
    layout="wide",
)

# ── Brand Assets ────────────────────────────────────────────────────────────
VAULT_LOGO_SVG = '''<svg width="84" height="30" viewBox="0 0 84 30" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M77.8514 11.5081H74.8991C74.7528 11.5081 74.6797 11.4425 74.6797 11.3114V10.1967C74.6797 10.0656 74.7528 10 74.8991 10H81.9008C82.6854 10 83.0777 10.3115 83.0777 10.9344V11.2786C83.0777 11.3332 83.0511 11.3879 82.9979 11.4425C82.958 11.4862 82.8915 11.5081 82.7984 11.5081H79.8262V18.9338C79.8262 19.054 79.7597 19.1141 79.6267 19.1141H78.0907C77.9312 19.1141 77.8514 19.054 77.8514 18.9338V11.5081Z" fill="#0C0A93"/>
  <path d="M70.451 17.6224H73.4032C74.1745 17.6224 74.5602 17.9284 74.5602 18.5404V18.8846C74.5602 19.0376 74.4738 19.1141 74.3009 19.1141H68.7155C68.5692 19.1141 68.4961 19.054 68.4961 18.9338V10.1967C68.4961 10.0656 68.5692 10 68.7155 10H68.895C69.4004 10 69.786 10.1147 70.052 10.3442C70.318 10.5628 70.451 10.9289 70.451 11.4425V17.6224Z" fill="#0C0A93"/>
  <path d="M61.6643 19.2781C60.7999 19.2781 60.0951 19.1633 59.5499 18.9338C59.0046 18.7043 58.5857 18.4093 58.2932 18.0486C58.0006 17.688 57.8011 17.3055 57.6947 16.9012C57.5884 16.4968 57.5352 16.1253 57.5352 15.7865V10.1967C57.5352 10.0656 57.6083 10 57.7546 10H57.9142C58.4461 10 58.8384 10.1093 59.0911 10.3278C59.357 10.5464 59.49 10.9125 59.49 11.4261V15.475C59.49 16.1526 59.6496 16.7045 59.9688 17.1307C60.2879 17.5569 60.8531 17.77 61.6643 17.77C62.4888 17.77 63.0673 17.5569 63.3998 17.1307C63.7323 16.6935 63.8985 16.1417 63.8985 15.475V10.1967C63.8985 10.0656 63.9783 10 64.1379 10H64.2974C64.8161 10 65.2084 10.1093 65.4744 10.3278C65.7403 10.5464 65.8733 10.9125 65.8733 11.4261V15.7701C65.8733 16.087 65.8201 16.4476 65.7137 16.852C65.6073 17.2454 65.4079 17.6279 65.1153 17.9995C64.8227 18.371 64.3972 18.677 63.8386 18.9174C63.2934 19.1578 62.5686 19.2781 61.6643 19.2781Z" fill="#0C0A93"/>
  <path d="M48.7311 16.8192L47.8335 18.901C47.7803 19.0431 47.6805 19.1141 47.5342 19.1141H45.9983C45.9318 19.1141 45.8852 19.0977 45.8586 19.065C45.832 19.0212 45.8254 18.9775 45.8387 18.9338L49.7085 10.1639C49.7484 10.0546 49.8282 10 49.9479 10H50.6062C51.0849 10 51.4573 10.082 51.7233 10.2459C51.9892 10.4098 52.2286 10.7322 52.4414 11.213L55.8524 18.9338C55.879 18.9775 55.879 19.0212 55.8524 19.065C55.8258 19.0977 55.7793 19.1141 55.7128 19.1141H54.1369C53.9375 19.1141 53.8111 19.0431 53.7579 18.901L52.8603 16.8192H48.7311ZM49.3295 15.4586H52.3017L50.8057 11.9343L49.3295 15.4586Z" fill="#0C0A93"/>
  <path d="M40.8573 17.2126L43.5502 10.2295C43.6167 10.0765 43.743 10 43.9292 10H45.3655C45.5117 10 45.5649 10.0656 45.525 10.1967L41.9544 18.9338C41.9012 19.054 41.8148 19.1141 41.6951 19.1141H39.8798C39.7203 19.1141 39.6205 19.054 39.5806 18.9338L36.01 10.2131C35.9967 10.1585 35.9967 10.1093 36.01 10.0656C36.0366 10.0219 36.0831 10 36.1496 10H36.8079C37.26 10 37.6124 10.082 37.8651 10.2459C38.1311 10.3989 38.3572 10.7213 38.5433 11.213L40.8573 17.2126Z" fill="#0C0A93"/>
  <path fill-rule="evenodd" clip-rule="evenodd" d="M16.1978 29.1445L9.37721 18.2207L20.7534 0H34.3945L16.1978 29.1445ZM16.3682 7.02357L8.25561 0L0.00121689 7.02357H16.3682Z" fill="#0C0A93"/>
</svg>'''

VAULT_MARK_DATA_URI = "data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 35 30' fill='none'%3E%3Cpath fill-rule='evenodd' clip-rule='evenodd' d='M16.1978 29.1445L9.37721 18.2207L20.7534 0H34.3945L16.1978 29.1445ZM16.3682 7.02357L8.25561 0L0.00121689 7.02357H16.3682Z' fill='%230C0A93'/%3E%3C/svg%3E"

USER_AVATAR = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/%3E"


# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ─── Font ─── */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

/* ═══════════════════════════════════════════════════════
   GLOBAL OVERRIDES
   ═══════════════════════════════════════════════════════ */
:root {
    --brand:        #0C0A93;
    --brand-light:  #4D4BFF;
    --brand-dim:    rgba(12,10,147,0.05);
    --brand-glow:   rgba(12,10,147,0.08);
    --text:         #111827;
    --text-2:       #4B5563;
    --text-3:       #9CA3AF;
    --border:       #E5E7EB;
    --surface:      #F9FAFB;
    --radius:       10px;
    --radius-lg:    14px;
    --ease:         cubic-bezier(.4,0,.2,1);
}

html, body, .stApp, .stApp > *, [class*="css"] {
    font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    -webkit-font-smoothing: antialiased !important;
}

/* Hide default Streamlit headings (we use custom HTML) */
.main h1, .main [data-testid="stHeading"] {
    display: none !important;
    height: 0 !important;
    overflow: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
}

section[data-testid="stSidebar"] h1 {
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* ═══════════════════════════════════════════════════════
   SIDEBAR
   ═══════════════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
    background: #FAFBFC !important;
    border-right: 1px solid var(--border) !important;
}

section[data-testid="stSidebar"] > div {
    padding-top: 0 !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
}

/* Brand header — flush to edges */
.sb-header {
    background: linear-gradient(135deg, #0C0A93 0%, #1a18b8 100%);
    margin: 0 -0.8rem;
    padding: 1.5rem 1.2rem 1.3rem 1.2rem;
}
.sb-header svg { height: 22px; width: auto; }
.sb-header svg path { fill: white !important; }
.sb-header svg path:last-child { fill: rgba(255,255,255,0.75) !important; }
.sb-header-label {
    font-size: 0.54rem; font-weight: 600;
    color: rgba(255,255,255,0.5);
    letter-spacing: 2.8px; text-transform: uppercase;
    margin-top: 0.45rem;
}

/* Section labels */
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: var(--text-3) !important;
    font-size: 0.58rem !important;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    font-weight: 600 !important;
    margin-top: 0.7rem !important;
    margin-bottom: 0.3rem !important;
    padding-left: 0.15rem !important;
}

section[data-testid="stSidebar"] .stMarkdown p {
    color: var(--text-2) !important;
    font-size: 0.82rem !important;
}

section[data-testid="stSidebar"] hr {
    border-color: var(--border) !important;
    margin: 0.35rem 0 !important;
}

/* ── ALL sidebar buttons base (chat history items) ── */
section[data-testid="stSidebar"] button {
    background: transparent !important;
    color: var(--text-2) !important;
    border: none !important;
    border-radius: 7px !important;
    font-size: 0.8rem !important;
    font-weight: 400 !important;
    padding: 0.42rem 0.6rem !important;
    transition: all 0.15s var(--ease) !important;
    text-align: left !important;
    box-shadow: none !important;
}

section[data-testid="stSidebar"] button:hover {
    background: #EDEEF1 !important;
    color: var(--text) !important;
}

section[data-testid="stSidebar"] button:active {
    background: #E2E4E8 !important;
}

/* ── New Chat button (override — MUST come after generic button rules) ── */
section[data-testid="stSidebar"] button[kind="secondary"],
section[data-testid="stSidebar"] button[kind="secondary"]:hover,
section[data-testid="stSidebar"] button[kind="secondary"]:active {
    background: var(--brand) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    padding: 0.5rem 1.2rem !important;
    box-shadow: 0 1px 6px rgba(12,10,147,0.18) !important;
    max-width: 150px !important;
    margin: 0.6rem auto 0.2rem auto !important;
    display: block !important;
    text-align: center !important;
    transition: all 0.3s var(--ease) !important;
}

section[data-testid="stSidebar"] button[kind="secondary"]:hover {
    background: var(--brand-light) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(12,10,147,0.25) !important;
}

section[data-testid="stSidebar"] button[kind="secondary"]:active {
    transform: scale(0.97) !important;
    box-shadow: 0 1px 3px rgba(12,10,147,0.12) !important;
}

/* ── Delete button ── */
.del-btn button,
.del-btn button:hover,
.del-btn button:active {
    padding: 0.3rem 0.35rem !important;
    min-width: 0 !important;
    font-size: 0.72rem !important;
    line-height: 1 !important;
    opacity: 0 !important;
    color: var(--text-3) !important;
    border-radius: 6px !important;
}

/* Show delete on row hover (via column container hover) */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:hover .del-btn button {
    opacity: 0.4 !important;
}

.del-btn button:hover {
    background: rgba(239,68,68,0.08) !important;
    color: #EF4444 !important;
    opacity: 1 !important;
}

.del-btn button:active {
    background: rgba(239,68,68,0.15) !important;
    opacity: 1 !important;
}

/* ── About card ── */
.about-card {
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1rem 1.1rem;
    margin-top: 0.5rem;
    font-size: 0.8rem;
    color: var(--text-2);
    line-height: 1.6;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.about-card strong { color: var(--text); font-weight: 600; }
.about-card hr { border: none; border-top: 1px solid var(--border); margin: 0.7rem 0; }
.about-card .ct-row {
    display: flex; align-items: center; gap: 0.55rem;
    margin-top: 0.35rem; font-size: 0.78rem; color: var(--text-2);
}
.about-card .ct-row svg {
    width: 14px; height: 14px; flex-shrink: 0; color: var(--brand); opacity: 0.7;
}

/* ═══════════════════════════════════════════════════════
   MAIN CONTENT
   ═══════════════════════════════════════════════════════ */
.main .block-container {
    max-width: 820px !important;
    padding-top: 2.5rem !important;
    padding-bottom: 0.5rem !important;
}

/* ── Hero header ── */
.hero-block {
    text-align: center;
    padding: 1.5rem 0 0.5rem 0;
}
.hero-block svg {
    height: 28px; width: auto; margin-bottom: 0.6rem;
}
.hero-block h2 {
    font-family: 'DM Sans', sans-serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.5px;
    margin: 0 0 0.3rem 0;
}
.hero-block p {
    color: var(--text-3);
    font-size: 0.9rem;
    margin: 0;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 3rem 1rem 1rem 1rem;
}
.empty-state .empty-icon {
    width: 64px;
    height: 64px;
    margin: 0 auto 1.2rem auto;
    background: linear-gradient(135deg, rgba(12,10,147,0.08) 0%, rgba(77,75,255,0.06) 100%);
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.empty-state .empty-icon svg {
    height: 28px; width: auto; opacity: 0.6;
}
.empty-state h3 {
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 0.4rem 0;
}
.empty-state p {
    font-size: 0.88rem;
    color: var(--text-3);
    max-width: 380px;
    margin: 0 auto 1.5rem auto;
    line-height: 1.6;
}
.empty-suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    justify-content: center;
    max-width: 520px;
    margin: 0 auto;
}
.empty-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.5rem 0.9rem;
    background: #FFFFFF;
    border: 1px solid var(--border);
    border-radius: 100px;
    font-size: 0.78rem;
    color: var(--text-2);
    cursor: default;
    transition: all 0.2s var(--ease);
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
}
.empty-chip:hover {
    border-color: var(--brand);
    color: var(--brand);
    box-shadow: 0 2px 8px rgba(12,10,147,0.08);
    transform: translateY(-1px);
}
.empty-chip .chip-icon {
    font-size: 0.85rem;
}

/* ═══════════════════════════════════════════════════════
   CHAT MESSAGES
   ═══════════════════════════════════════════════════════ */
div[data-testid="stChatMessage"] {
    background: #FFFFFF !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 1rem 1.25rem !important;
    margin-bottom: 0.5rem !important;
    transition: all 0.2s var(--ease) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
}

div[data-testid="stChatMessage"]:hover {
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}

div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    border-left: 3px solid var(--brand) !important;
    background: #FFFFFF !important;
}

div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
    border-left: 3px solid var(--brand-light) !important;
    background: var(--surface) !important;
}

div[data-testid="stChatMessage"] img {
    width: 24px !important; height: 24px !important; border-radius: 6px !important;
}

div[data-testid="stChatMessage"] p {
    color: var(--text) !important; line-height: 1.75 !important;
    font-size: 0.9rem !important; font-weight: 400 !important;
}

div[data-testid="stChatMessage"] strong { color: var(--text) !important; font-weight: 600 !important; }

div[data-testid="stChatMessage"] a {
    color: var(--brand) !important; text-decoration: none !important;
    font-weight: 500 !important;
    border-bottom: 1px solid rgba(12,10,147,0.2) !important;
    transition: all 0.2s var(--ease) !important;
}
div[data-testid="stChatMessage"] a:hover { border-bottom-color: var(--brand) !important; }

div[data-testid="stChatMessage"] li {
    color: var(--text) !important; font-size: 0.9rem !important; line-height: 1.75 !important;
}
div[data-testid="stChatMessage"] li::marker { color: var(--brand-light) !important; }

div[data-testid="stChatMessage"] h1,
div[data-testid="stChatMessage"] h2,
div[data-testid="stChatMessage"] h3 {
    display: block !important; color: var(--text) !important;
    font-weight: 700 !important; font-size: 1.05rem !important;
    margin-top: 1rem !important; margin-bottom: 0.35rem !important;
    letter-spacing: -0.2px !important;
}

/* Code blocks in messages */
div[data-testid="stChatMessage"] code {
    background: #F3F4F6 !important;
    color: var(--brand) !important;
    padding: 0.15rem 0.4rem !important;
    border-radius: 5px !important;
    font-size: 0.82rem !important;
}

/* ═══════════════════════════════════════════════════════
   CHAT INPUT — Floating style
   ═══════════════════════════════════════════════════════ */
div[data-testid="stChatInput"] {
    padding-bottom: 1rem !important;
}

div[data-testid="stBottom"] > div,
div[data-testid="stBottom"] {
    background: #FFFFFF !important;
}

div[data-testid="stChatInput"] > div {
    background: #FFFFFF !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 16px !important;
    transition: all 0.3s var(--ease) !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.06), 0 0 0 0px transparent !important;
}

div[data-testid="stChatInput"] > div:focus-within {
    border-color: var(--brand) !important;
    box-shadow: 0 4px 20px rgba(12,10,147,0.08), 0 0 0 3px rgba(12,10,147,0.06) !important;
}

div[data-testid="stChatInput"] textarea {
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.92rem !important;
    box-shadow: none !important; border: none !important; background: transparent !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color: #C9CCD1 !important; }

div[data-testid="stChatInput"] button {
    color: var(--brand) !important;
    transition: all 0.2s var(--ease) !important;
    border-radius: 10px !important;
}
div[data-testid="stChatInput"] button:hover {
    background: var(--brand-dim) !important;
    color: var(--brand-light) !important;
    transform: scale(1.1) !important;
}
div[data-testid="stChatInput"] button:active {
    transform: scale(0.92) !important;
    transition: all 0.08s !important;
}

/* ═══════════════════════════════════════════════════════
   SPINNER & ALERTS
   ═══════════════════════════════════════════════════════ */
.stSpinner > div { border-top-color: var(--brand) !important; }
.stSpinner p { color: var(--text-2) !important; font-size: 0.82rem !important; }

div[data-testid="stAlert"] {
    background: rgba(239,68,68,0.04) !important;
    border: 1px solid rgba(239,68,68,0.12) !important;
    border-radius: var(--radius) !important;
    color: var(--text) !important;
}

/* ═══════════════════════════════════════════════════════
   SCROLLBAR
   ═══════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.08); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.15); }

/* ═══════════════════════════════════════════════════════
   FOOTER
   ═══════════════════════════════════════════════════════ */
.vault-footer {
    text-align: center; padding: 1rem 0 0.5rem 0;
    font-size: 0.7rem; color: var(--text-3); letter-spacing: 0.3px;
}
.vault-footer .vf-brand { color: var(--brand); font-weight: 600; }
.vault-footer .vf-sep { margin: 0 0.5rem; opacity: 0.3; }

.main hr { border-color: var(--border) !important; margin-top: 1rem !important; margin-bottom: 0 !important; }

/* ═══════════════════════════════════════════════════════
   TOAST
   ═══════════════════════════════════════════════════════ */
div[data-testid="stToast"] {
    background: var(--text) !important; color: #FFFFFF !important;
    border-radius: 12px !important;
    box-shadow: 0 12px 40px rgba(0,0,0,0.12) !important;
    font-size: 0.84rem !important; font-weight: 500 !important;
}

/* ═══════════════════════════════════════════════════════
   HIDE DEPLOY BUTTON
   ═══════════════════════════════════════════════════════ */
.stDeployButton { display: none !important; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "chat_id" not in st.session_state:
    st.session_state.chat_id = str(uuid.uuid4())
if "chat_name" not in st.session_state:
    st.session_state.chat_name = "New Chat"

# Sidebar
with st.sidebar:
    st.title("Vault PropTech")  # Hidden by CSS

    # Brand header — indigo banner at top
    st.markdown(f"""
    <div class="sb-header">
        {VAULT_LOGO_SVG}
        <div class="sb-header-label">Legal Assistant</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_id = str(uuid.uuid4())
        st.session_state.chat_name = "New Chat"
        st.toast("New conversation started")
        st.rerun()

    st.markdown("---")
    st.subheader("Chat History")

    browser_id = get_browser_id()
    chats = load_chats(browser_id)

    if not chats:
        st.markdown(
            "<p style='color:#9CA3AF; font-size:0.78rem; padding:0.3rem 0; font-style:italic;'>No conversations yet</p>",
            unsafe_allow_html=True,
        )

    for chat in chats:
        col1, col2 = st.columns([6, 1], gap="small")
        with col1:
            if st.button(chat["chat_name"], key=chat["chat_id"], use_container_width=True):
                loaded = load_chat(browser_id, chat["chat_id"])
                if loaded:
                    st.session_state.messages = loaded["messages"]
                    st.session_state.chat_id = chat["chat_id"]
                    st.session_state.chat_name = chat["chat_name"]
                    st.rerun()
        with col2:
            st.markdown('<div class="del-btn">', unsafe_allow_html=True)
            if st.button("✕", key=f"del_{chat['chat_id']}"):
                delete_chat(browser_id, chat["chat_id"])
                if chat["chat_id"] == st.session_state.chat_id:
                    st.session_state.messages = []
                    st.session_state.chat_id = str(uuid.uuid4())
                    st.session_state.chat_name = "New Chat"
                st.toast("Chat deleted")
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("About")
    st.markdown("""
    <div class="about-card">
        <strong>Vault PropTech</strong> helps you navigate property documentation
        and legal services in Bangalore, Karnataka.
        <hr>
        <strong>Contact</strong>
        <div class="ct-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg>
            +91 88619 50376
        </div>
        <div class="ct-row">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
            info@vaultproptech.com
        </div>
    </div>
    """, unsafe_allow_html=True)

# Main content
# Hero — centered brand presentation
st.markdown(f"""
<div class="hero-block">
    {VAULT_LOGO_SVG}
    <h2>Legal Assistant</h2>
    <p>Property documentation & legal guidance · Exclusively in Bengaluru</p>
</div>
""", unsafe_allow_html=True)

# Empty state with suggestion chips
if not st.session_state.messages:
    st.markdown(f"""
    <div class="empty-state">
        <div class="empty-icon">
            {VAULT_LOGO_SVG}
        </div>
        <h3>How can I help you today?</h3>
        <p>Ask about property documentation, legal processes, or Vault's services in Bengaluru.</p>
        <div class="empty-suggestions">
            <span class="empty-chip">What is E-Khata?</span>
            <span class="empty-chip">Khata Transfer process</span>
            <span class="empty-chip">Due Diligence steps</span>
            <span class="empty-chip">Documents for registration</span>
            <span class="empty-chip">BESCOM name change</span>
            <span class="empty-chip">Vault service pricing</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Display chat messages
for message in st.session_state.messages:
    avatar = VAULT_MARK_DATA_URI if message["role"] == "assistant" else USER_AVATAR
    with st.chat_message(message["role"], avatar=avatar):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Ask your question here..."):
    if st.session_state.chat_name == "New Chat":
        st.session_state.chat_name = prompt[:20] + ("..." if len(prompt) > 20 else "")

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=VAULT_MARK_DATA_URI):
        with st.spinner("Searching knowledge base..."):
            kb_dir = os.path.dirname(os.path.abspath(__file__))

            try:
                answer = ask(kb_dir, prompt, st.session_state.messages, verbose=False)
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

                browser_id = get_browser_id()
                save_chat(browser_id, st.session_state.chat_id, st.session_state.messages, st.session_state.chat_name)

            except Exception as e:
                error_msg = f"I encountered an error: {str(e)}\n\nPlease make sure:\n1. The knowledge base is ingested (`python setup.py ingest`)\n2. Your GEMINI_API_KEY is set in .env"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})


# Footer
st.markdown("---")
st.markdown(
    "<div class='vault-footer'>"
    "© 2026 <span class='vf-brand'>Vault PropTech</span>"
    "<span class='vf-sep'>·</span>"
    "Bengaluru, Karnataka"
    "</div>",
    unsafe_allow_html=True
)
