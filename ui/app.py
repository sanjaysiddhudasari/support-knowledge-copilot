import requests
import streamlit as st
import re
import os



API_URL = os.getenv(
    "API_URL",
    "http://127.0.0.1:8000/api/query",
)

UPLOAD_URL = os.getenv(
    "UPLOAD_URL",
    "http://127.0.0.1:8000/api/documents",
)


st.set_page_config(
    page_title="Support Knowledge Copilot",
    page_icon="🔎",
    layout="wide",
)


# ==================================================
# Sidebar - Knowledge Base
# ==================================================

with st.sidebar:

    st.header("📚 Knowledge Base")

    st.caption(
        "Upload Markdown documentation "
        "to add it to the knowledge base."
    )

    uploaded_file = st.file_uploader(
        "Upload Markdown",
        type=["md"],
    )

    if uploaded_file is not None:

        if st.button(
            "Upload & Index",
            use_container_width=True,
        ):

            with st.spinner(
                "Uploading and indexing..."
            ):

                try:

                    response = requests.post(
                        UPLOAD_URL,
                        files={
                            "file": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                "text/markdown",
                            )
                        },
                        timeout=300,
                    )

                    response.raise_for_status()

                    data = response.json()

                    st.success(
                        f"✓ {data.get('filename', uploaded_file.name)} "
                        "indexed successfully."
                    )

                except requests.RequestException as error:

                    st.error(
                        f"Upload failed: {error}"
                    )


# ==================================================
# Main UI
# ==================================================

st.title("🔎 Support Knowledge Copilot")

st.caption(
    "Ask questions about AcmeCloud documentation "
    "and get answers with verified citations."
)


# ==================================================
# Conversation State
# ==================================================

if "messages" not in st.session_state:

    st.session_state.messages = []


# ==================================================
# Display Previous Conversation
# ==================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


# ==================================================
# Query
# ==================================================

query = st.chat_input(
    "Ask a question about AcmeCloud..."
)


if query:

    # --------------------------------------------------
    # User message
    # --------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": query,
        }
    )

    with st.chat_message("user"):

        st.markdown(query)

    # --------------------------------------------------
    # Assistant
    # --------------------------------------------------

    with st.chat_message("assistant"):

        with st.spinner(
            "Searching the knowledge base..."
        ):

            try:

                response = requests.post(
                    API_URL,
                    json={
                        "query": query
                    },
                    timeout=120,
                )

                response.raise_for_status()

                data = response.json()

            except requests.RequestException as error:

                st.error(
                    f"Could not reach the API: {error}"
                )

                st.stop()

        # --------------------------------------------------
        # Answer
        # --------------------------------------------------

        answer = data.get(
            "answer",
            "No answer was returned.",
        )

        # Remove raw citation markers such as:
        # [account-recovery.md_chunk_2]
        # [new_test.md_chunk_5]
        display_answer = re.sub(
            r"\[[\w.-]+_chunk_\d+\]",
            "",
            answer,
        )

        # Clean up accidental extra whitespace.
        display_answer = re.sub(
            r"[ \t]+\n",
            "\n",
            display_answer,
        ).strip()

        st.markdown(display_answer)

        # --------------------------------------------------
        # Confidence
        # --------------------------------------------------

        confidence = data.get(
            "confidence"
        )

        if isinstance(
            confidence,
            dict,
        ):

            confidence_value = confidence.get(
                "confidence",
                0,
            )

        else:

            confidence_value = (
                confidence or 0
            )

        # Make sure it is numeric
        try:

            confidence_value = float(
                confidence_value
            )

        except (
            TypeError,
            ValueError,
        ):

            confidence_value = 0.0

        # --------------------------------------------------
        # Answerability
        # --------------------------------------------------

        answerability = data.get(
            "answerable",
            False,
        )

        # Some API responses may expose answerability
        # as a nested object.
        if isinstance(
            answerability,
            dict,
        ):

            answerability = answerability.get(
                "answerable",
                False,
            )

        # --------------------------------------------------
        # Metrics
        # --------------------------------------------------

        st.divider()

        col1, col2 = st.columns(2)

        with col1:

            st.metric(
                "Confidence",
                f"{confidence_value:.0%}",
            )

        with col2:

            st.metric(
                "Answerable",
                "Yes"
                if answerability
                else "No",
            )

        # --------------------------------------------------
        # Citations
        # --------------------------------------------------

        citations = data.get(
            "citations",
            [],
        )

        if citations:

            st.subheader("Sources")

            for citation in citations:

                # Handle both Pydantic-style serialized
                # dictionaries and normal dictionaries.
                chunk_id = citation.get(
                    "chunk_id",
                    "Unknown",
                )

                supported = citation.get(
                    "supported",
                    False,
                )

                claim = citation.get(
                    "claim",
                    "",
                )

                explanation = citation.get(
                    "explanation",
                    "",
                )

                icon = (
                    "✅"
                    if supported
                    else "⚠️"
                )

                # Extract filename and chunk number
                # from IDs such as:
                #
                # account-recovery.md_chunk_2

                source_name = chunk_id

                if "_chunk_" in chunk_id:

                    source_name = chunk_id.split(
                        "_chunk_"
                    )[0]
                status = (
                    "Verified"
                    if supported
                    else "Not verified"
                )   
                with st.expander(
                    f"{icon} {source_name} . {status}"
                ):

                    st.caption(
                        f"Chunk: {chunk_id}"
                    )

                    if claim:

                        st.write(
                            claim
                        )

                    if explanation:

                        st.caption(
                            explanation
                        )

        else:

            st.info(
                "No verified sources were returned."
            )

    # --------------------------------------------------
    # Save Assistant Response
    # --------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer,
        }
    )