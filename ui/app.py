import mimetypes
import os

import requests
import streamlit as st

try:  # `streamlit run ui/app.py` (script dir on sys.path) vs running from repo root
    from ui.chat_state import (
        TOKEN_KEY,
        USER_KEY,
        add_assistant_message,
        add_user_message,
        citation_page,
        citation_source_name,
        format_badge,
        format_line,
        format_meta,
        get_messages,
        init_chat_state,
        new_chat,
        strip_citations,
    )
except ImportError:  # pragma: no cover - depends on how Streamlit is launched
    from chat_state import (
        TOKEN_KEY,
        USER_KEY,
        add_assistant_message,
        add_user_message,
        citation_page,
        citation_source_name,
        format_badge,
        format_line,
        format_meta,
        get_messages,
        init_chat_state,
        new_chat,
        strip_citations,
    )


st.set_page_config(
    page_title="Support Knowledge Copilot",
    page_icon="🔎",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2.2rem; max-width: 1100px; }
      .app-header h1 { margin-bottom: 0; font-size: 1.9rem; }
      .app-header p { color: #6b7280; margin-top: .25rem; }
      .meta-line { font-size: .85rem; color: #6b7280; margin: .35rem 0 .1rem 0; }
      .user-card { border: 1px solid rgba(128,128,128,.25); border-radius: .6rem;
                   padding: .6rem .75rem; margin-bottom: .5rem; }
      .user-card .email { font-weight: 600; word-break: break-all; }
      .user-card .level { font-size: .8rem; color: #6b7280; }
    </style>
    """,
    unsafe_allow_html=True,
)


DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def _secret(key: str):
    """Read a Streamlit secret, tolerating a missing secrets.toml."""

    try:
        return st.secrets[key]
    except Exception:
        return None


# Streamlit Community Cloud provides this as a secret; locally it can come
# from the environment.
API_BASE_URL = (
    _secret("API_BASE_URL")
    or os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
)

QUERY_URL = f"{API_BASE_URL}/api/query"
UPLOAD_URL = f"{API_BASE_URL}/api/documents"
DOCS_LIST_URL = f"{API_BASE_URL}/api/documents"
LOGIN_URL = f"{API_BASE_URL}/api/auth/login"
SIGNUP_URL = f"{API_BASE_URL}/api/auth/signup"
ME_URL = f"{API_BASE_URL}/api/me"

SUPPORTED_FORMATS = "MD · TXT · PDF · DOCX · HTML"


# ==================================================
# API helpers
# ==================================================


def login(email: str, password: str):
    try:
        response = requests.post(
            LOGIN_URL,
            json={"email": email, "password": password},
            timeout=30,
        )
    except requests.RequestException:
        return None, "Could not reach the API."

    if response.status_code != 200:
        return None, "Invalid email or password"

    return response.json(), None


def signup(email: str, password: str, confirm_password: str):
    try:
        response = requests.post(
            SIGNUP_URL,
            json={
                "email": email,
                "password": password,
                "confirm_password": confirm_password,
            },
            timeout=30,
        )
    except requests.RequestException:
        return None, "Could not reach the API."

    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None

        return None, detail or "Sign up failed."

    return response.json(), None


def fetch_me(token: str):
    try:
        response = requests.get(
            ME_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    return response.json()


def ask_question(query: str):
    """Return ``(data, error)``. Never raises."""

    try:
        response = requests.post(
            QUERY_URL,
            json={"query": query},
            headers={
                "Authorization": f"Bearer {st.session_state[TOKEN_KEY]}"
            },
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return None, f"Could not reach the API: {error}"

    try:
        return response.json(), None
    except ValueError:
        return None, "The API returned an unreadable response."


# ==================================================
# Rendering
# ==================================================


def render_sources(citations):
    if not citations:
        st.caption("No verified sources were returned.")
        return

    st.markdown("**Sources**")

    for citation in citations:
        citation = citation or {}

        supported = bool(citation.get("supported"))
        icon = "✅" if supported else "⚠️"
        status = "Verified" if supported else "Not verified"

        source_name = citation_source_name(citation)
        page = citation_page(citation)
        page_or_none = page if page is not None else citation.get("page")
        meta = format_line(citation.get("file_type"), page_or_none)

        with st.expander(f"{icon} {source_name} · {status}"):
            st.caption(f"{format_badge(citation.get('file_type'))} — {meta}")
            st.caption(f"Chunk: {citation.get('chunk_id', 'Unknown')}")

            claim = citation.get("claim")

            if claim:
                st.write(claim)

            explanation = citation.get("explanation")

            if explanation:
                st.caption(explanation)


def render_message_body(message: dict):
    """Render a turn's contents, assuming a chat_message block is already open."""

    if message.get("role") == "user":
        st.markdown(message.get("content", ""))
        return

    error = message.get("error")

    if error:
        st.error(error)

    content = message.get("content")

    if content:
        st.markdown(strip_citations(content))

    confidence = float(message.get("confidence") or 0.0)
    answerable = bool(message.get("answerable"))

    st.markdown(
        f"<div class='meta-line'>Confidence {confidence:.0%} • "
        f"Answerable {'✓' if answerable else '✗'}</div>",
        unsafe_allow_html=True,
    )

    render_sources(message.get("citations") or [])


def render_message(message: dict):
    """Render one stored turn using ONLY that message's own metadata."""

    with st.chat_message(message.get("role", "assistant")):
        render_message_body(message)


# ==================================================
# Authentication
# ==================================================


def render_auth_screen():
    st.markdown(
        "<div class='app-header'><h1>🔎 Support Knowledge Copilot</h1>"
        "<p>AI-powered answers from your verified documentation</p></div>",
        unsafe_allow_html=True,
    )

    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        email = st.text_input("Email", key="login_email")
        password = st.text_input(
            "Password", type="password", key="login_password"
        )

        if st.button("Login", type="primary", use_container_width=True):
            if not email.strip() or not password:
                st.error("Enter your email and password.")
            else:
                result, error = login(email.strip(), password)

                if error:
                    st.error(error)
                else:
                    st.session_state[TOKEN_KEY] = result["access_token"]
                    st.session_state[USER_KEY] = (
                        fetch_me(result["access_token"])
                        or {"email": email.strip(), "access_level": "public"}
                    )
                    st.rerun()

    with signup_tab:
        email = st.text_input("Email", key="signup_email")
        password = st.text_input(
            "Password", type="password", key="signup_password"
        )
        confirm_password = st.text_input(
            "Confirm password", type="password", key="signup_confirm"
        )

        st.caption("At least 8 characters. New accounts get public access.")

        if st.button("Sign Up", use_container_width=True):
            if not email.strip() or not password:
                st.error("Enter your email and password.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            else:
                result, error = signup(
                    email.strip(), password, confirm_password
                )

                if error:
                    st.error(error)
                elif result.get("status") == "confirmation_required":
                    st.success(result.get("message", "Check your email."))
                else:
                    st.session_state[TOKEN_KEY] = result["access_token"]
                    st.session_state[USER_KEY] = {
                        "email": result.get("email", email.strip()),
                        "access_level": result.get(
                            "access_level", "public"
                        ),
                    }
                    st.rerun()


init_chat_state(st.session_state)

if TOKEN_KEY not in st.session_state:
    render_auth_screen()
    st.stop()


# ==================================================
# Sidebar
# ==================================================

user = st.session_state.get(USER_KEY) or {}
user_email = user.get("email", "Signed in")
user_level = str(user.get("access_level") or "public").capitalize()

with st.sidebar:

    st.markdown("### 🔎 Support Copilot")

    if st.button("+ New Chat", use_container_width=True):
        new_chat(st.session_state)
        st.rerun()

    st.divider()

    st.markdown("**📚 Knowledge Base**")
    st.caption(
        "Upload documentation to add it to the knowledge base."
    )

    uploaded_file = st.file_uploader(
        "Upload document",
        type=["md", "txt", "pdf", "docx", "html", "htm"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:

        if st.button("Upload & Index", use_container_width=True):

            with st.spinner("Uploading and indexing..."):

                try:
                    response = requests.post(
                        UPLOAD_URL,
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                mimetypes.guess_type(
                                    uploaded_file.name
                                )[0]
                                or "application/octet-stream",
                            )
                        },
                        headers={
                            "Authorization": (
                                f"Bearer {st.session_state[TOKEN_KEY]}"
                            )
                        },
                        timeout=300,
                    )

                    response.raise_for_status()

                    data = response.json()

                    st.success(
                        f"✓ {data.get('filename', uploaded_file.name)} "
                        "indexed successfully"
                    )
                    st.caption(
                        f"Type: {format_meta(data.get('file_type'))['label']}"
                    )

                except requests.RequestException as error:
                    st.error(f"Upload failed: {error}")

    st.caption(f"Supported: {SUPPORTED_FORMATS}")

    st.divider()

    st.markdown("**📁 My Documents**")

    try:
        documents_response = requests.get(
            DOCS_LIST_URL,
            headers={
                "Authorization": f"Bearer {st.session_state[TOKEN_KEY]}"
            },
            timeout=30,
        )
        documents = (
            documents_response.json()
            if documents_response.status_code == 200
            else []
        )
    except requests.RequestException:
        documents = []

    if not documents:
        st.caption("No documents yet.")
    else:
        for document in documents:
            document_id = document.get("id")

            if not document_id:
                continue

            label = (
                f"{format_badge(document.get('file_type'))} · "
                f"{document.get('filename', '?')}"
            )

            row_columns = st.columns([0.8, 0.2])

            with row_columns[0]:
                st.caption(
                    f"{label}\n\nv{document.get('version', '?')} · "
                    f"{(document.get('size_bytes') or 0) // 1024} KB · "
                    f"{document.get('status', '?')}"
                )

            with row_columns[1]:
                if st.button(
                    "🗑",
                    key=f"delete-document-{document_id}",
                    help="Delete this document",
                ):
                    try:
                        delete_response = requests.delete(
                            f"{DOCS_LIST_URL}/{document_id}",
                            headers={
                                "Authorization": (
                                    f"Bearer {st.session_state[TOKEN_KEY]}"
                                )
                            },
                            timeout=30,
                        )
                        delete_response.raise_for_status()
                        st.rerun()
                    except requests.RequestException as error:
                        st.error(f"Delete failed: {error}")

    st.divider()

    st.markdown(
        "<div class='user-card'>"
        f"<div class='email'>👤 {user_email}</div>"
        f"<div class='level'>{user_level} access</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()


# ==================================================
# Main chat
# ==================================================

st.markdown(
    "<div class='app-header'><h1>Support Knowledge Copilot</h1>"
    "<p>AI-powered answers from your verified documentation</p></div>",
    unsafe_allow_html=True,
)

for message in get_messages(st.session_state):
    render_message(message)

query = st.chat_input("Ask a question about AcmeCloud...")

if query:

    add_user_message(st.session_state, query)

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):

        with st.status(
            "Searching documentation...",
            expanded=False,
        ) as status:

            data, error = ask_question(query)

            if error:
                status.update(
                    label="Request failed",
                    state="error",
                )
            else:
                status.update(
                    label="Verifying citations...",
                )
                status.update(
                    label="Answer ready",
                    state="complete",
                )

        if error:
            add_assistant_message(st.session_state, "", error=error)
            st.error(error)
            st.caption("Your previous answers are still shown above.")
        else:
            add_assistant_message(
                st.session_state,
                data.get("answer", "No answer was returned."),
                confidence=data.get("confidence"),
                answerable=data.get("answerable"),
                citations=data.get("citations", []),
            )

            render_message_body(get_messages(st.session_state)[-1])
