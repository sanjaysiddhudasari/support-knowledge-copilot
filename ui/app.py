import mimetypes
import os
import uuid

import requests
import streamlit as st

try:  # `streamlit run ui/app.py` (script dir on sys.path) vs running from repo root
    from ui.chat_state import (
        CONVERSATIONS_KEY,
        CURRENT_CONVERSATION_KEY,
        MESSAGES_KEY,
        TOKEN_KEY,
        USER_KEY,
        add_assistant_message,
        add_user_message,
        citation_page,
        citation_source_name,
        conversation_title,
        format_badge,
        format_line,
        format_meta,
        get_messages,
        init_chat_state,
        messages_from_rows,
        new_chat,
        strip_citations,
    )
    from ui.conversation_api import ConversationAPI
except ImportError:  # pragma: no cover - depends on how Streamlit is launched
    from chat_state import (
        CONVERSATIONS_KEY,
        CURRENT_CONVERSATION_KEY,
        MESSAGES_KEY,
        TOKEN_KEY,
        USER_KEY,
        add_assistant_message,
        add_user_message,
        citation_page,
        citation_source_name,
        conversation_title,
        format_badge,
        format_line,
        format_meta,
        get_messages,
        init_chat_state,
        messages_from_rows,
        new_chat,
        strip_citations,
    )
    from conversation_api import ConversationAPI


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


def ask_question(query: str, query_id: str | None = None):
    """Return ``(data, error)``. Never raises.

    ``query_id`` is forwarded so the RAG trace and the persisted conversation
    messages share one correlation id.
    """

    payload = {"query": query}

    if query_id:
        payload["query_id"] = query_id

    try:
        response = requests.post(
            QUERY_URL,
            json=payload,
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

    persistence_error = message.get("persistence_error")

    if persistence_error:
        st.caption(persistence_error)

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


# ==================================================
# Conversation state (database-backed)
# ==================================================


def load_conversation(api: ConversationAPI, conversation_id: str):
    """Select a conversation and restore its messages from storage."""

    st.session_state[CURRENT_CONVERSATION_KEY] = conversation_id
    st.session_state[MESSAGES_KEY] = messages_from_rows(
        api.messages(conversation_id)
    )


def refresh_conversation_list(api: ConversationAPI):
    st.session_state[CONVERSATIONS_KEY] = api.list()


def start_new_conversation(api: ConversationAPI):
    """Create an empty conversation; degrade to a session-only chat on failure."""

    created = api.create()

    if created:
        load_conversation(api, created["id"])
    else:
        new_chat(st.session_state)
        st.session_state[CURRENT_CONVERSATION_KEY] = None

    refresh_conversation_list(api)


def bootstrap_conversations(api: ConversationAPI):
    """On login/refresh: list conversations and restore the most recent one."""

    conversations = api.list()

    st.session_state[CONVERSATIONS_KEY] = conversations

    if conversations:
        load_conversation(api, conversations[0]["id"])
    else:
        st.session_state[CURRENT_CONVERSATION_KEY] = None
        new_chat(st.session_state)


init_chat_state(st.session_state)

if TOKEN_KEY not in st.session_state:
    render_auth_screen()
    st.stop()


conversation_api = ConversationAPI(API_BASE_URL, st.session_state[TOKEN_KEY])

# UI state only. History itself always comes from the database, so a page
# refresh re-reads it rather than replaying session state.
if CURRENT_CONVERSATION_KEY not in st.session_state:
    bootstrap_conversations(conversation_api)


# ==================================================
# Sidebar
# ==================================================

user = st.session_state.get(USER_KEY) or {}
user_email = user.get("email", "Signed in")
user_level = str(user.get("access_level") or "public").capitalize()

with st.sidebar:

    st.markdown("### 🔎 Support Copilot")

    if st.button("+ New Chat", use_container_width=True):
        start_new_conversation(conversation_api)
        st.rerun()

    st.divider()

    st.markdown("**💬 Conversations**")

    conversations = st.session_state.get(CONVERSATIONS_KEY) or []
    current_conversation_id = st.session_state.get(CURRENT_CONVERSATION_KEY)

    if not conversations:
        st.caption("No conversations yet — ask a question to start one.")
    else:
        for conversation in conversations:
            conversation_id = conversation.get("id")

            if not conversation_id:
                continue

            label = conversation_title(conversation)

            if conversation_id == current_conversation_id:
                label = f"▶ {label}"

            select_column, delete_column = st.columns([0.82, 0.18])

            if select_column.button(
                label,
                key=f"conversation-{conversation_id}",
                use_container_width=True,
            ):
                load_conversation(conversation_api, conversation_id)
                st.rerun()

            if delete_column.button(
                "🗑",
                key=f"delete-{conversation_id}",
                help="Delete this conversation",
            ):
                if conversation_api.delete(conversation_id) and (
                    conversation_id == current_conversation_id
                ):
                    st.session_state[CURRENT_CONVERSATION_KEY] = None
                    new_chat(st.session_state)

                refresh_conversation_list(conversation_api)
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

    # One correlation id per submission: stored on both turns and attached to
    # the RAG trace, so a stored message maps to exactly one LangSmith run.
    query_id = uuid.uuid4().hex

    conversation_id = st.session_state.get(CURRENT_CONVERSATION_KEY)

    # A question always belongs to a conversation.
    if not conversation_id:
        created = conversation_api.create()

        if created:
            conversation_id = created["id"]
            st.session_state[CURRENT_CONVERSATION_KEY] = conversation_id

    # Persist the question before running RAG: if retrieval fails, the user's
    # message is still stored (and never replaced by an invented answer).
    if conversation_id:
        conversation_api.add_message(
            conversation_id,
            role="user",
            content=query,
            query_id=query_id,
        )

    add_user_message(st.session_state, query)

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):

        with st.status(
            "Searching documentation...",
            expanded=False,
        ) as status:

            data, error = ask_question(query, query_id)

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
            add_assistant_message(
                st.session_state, "", error=error, query_id=query_id
            )
            st.error(error)
            st.caption("Your previous answers are still shown above.")
        else:
            answer = data.get("answer", "No answer was returned.")
            citations = data.get("citations") or []

            message = add_assistant_message(
                st.session_state,
                answer,
                confidence=data.get("confidence"),
                answerable=data.get("answerable"),
                citations=citations,
                query_id=query_id,
            )

            if conversation_id:
                stored = conversation_api.add_message(
                    conversation_id,
                    role="assistant",
                    content=answer,
                    query_id=query_id,
                    confidence=data.get("confidence"),
                    answerable=data.get("answerable"),
                    citations=citations,
                )

                # A successful answer is never hidden by a storage failure.
                # The notice rides on the message so it survives the rerun.
                if stored is None:
                    message["persistence_error"] = (
                        "⚠️ The answer is shown, but it could not be saved "
                        "to your history."
                    )

            render_message_body(message)

    # Keep the sidebar's titles/order in step with the database.
    refresh_conversation_list(conversation_api)

    st.rerun()
