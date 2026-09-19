import queue
import uuid
import streamlit as st

from chatbot_stm import (
    chatbot,
    retrieve_all_threads,
    register_thread,
    user_owns_thread,
    submit_async_task,
    ingest_pdf,
    thread_document_metadata
)

from auth import (
    get_google_login_url,
    exchange_code,
    get_current_user,
    logout
)

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    ToolMessage
)


# =========================================================
# THREAD FUNCTIONS
# =========================================================

def generate_thread_id():
    return str(uuid.uuid4())


def add_thread(thread_id):

    thread_id = str(thread_id)

    if thread_id not in st.session_state["chat_threads"]:

        st.session_state["chat_threads"].insert(
            0,
            thread_id
        )


def reset_chat():

    thread_id = generate_thread_id()

    user_id = st.session_state.get(
        "user_id"
    )

    if user_id:

        register_thread(
            user_id,
            thread_id
        )

    st.session_state["thread_id"] = thread_id

    st.session_state["message_history"] = []

    add_thread(thread_id)


# =========================================================
# LOAD CONVERSATION
# =========================================================

def load_conversation(thread_id):

    user_id = st.session_state.get(
        "user_id"
    )

    if not user_id:
        return []

    if not user_owns_thread(
        user_id,
        thread_id
    ):
        return []

    state = chatbot.get_state(
        config={
            "configurable": {
                "thread_id": str(thread_id),
                "user_id": user_id
            }
        }
    )

    return state.values.get(
        "messages",
        []
    )


# =========================================================
# CHAT NAME
# =========================================================

def get_chat_name(thread_id):

    messages = load_conversation(
        thread_id
    )

    for message in messages:

        if isinstance(
            message,
            HumanMessage
        ):

            content = message.content

            if isinstance(
                content,
                str
            ):

                content = (
                    content
                    .strip()
                    .replace(
                        "\n",
                        " "
                    )
                )

                if content:

                    return (
                        content[:40]
                        +
                        (
                            "..."
                            if len(content) > 40
                            else ""
                        )
                    )

    return "New Chat"


# =========================================================
# INITIAL SESSION STATE
# =========================================================

if "message_history" not in st.session_state:

    st.session_state["message_history"] = []


if "thread_id" not in st.session_state:

    st.session_state["thread_id"] = (
        generate_thread_id()
    )


if "thread_files" not in st.session_state:

    st.session_state["thread_files"] = {}


if "user_id" not in st.session_state:

    st.session_state["user_id"] = None


if "user_email" not in st.session_state:

    st.session_state["user_email"] = None


if "access_token" not in st.session_state:

    st.session_state["access_token"] = None


if "refresh_token" not in st.session_state:

    st.session_state["refresh_token"] = None


# =========================================================
# GOOGLE AUTHENTICATION
# =========================================================

# =========================================================
# HANDLE OAUTH CALLBACK
# =========================================================

if (
    "code" in st.query_params
    and not st.session_state.get("user_id")
):

    try:

        # -------------------------------------------------
        # GET AUTHORIZATION CODE
        # -------------------------------------------------

        code = st.query_params.get(
            "code"
        )

        if not code:

            st.error(
                "Authentication failed: "
                "OAuth authorization code is missing."
            )

            st.stop()


        # -------------------------------------------------
        # EXCHANGE CODE
        # -------------------------------------------------

        response = exchange_code(
            code
        )


        # -------------------------------------------------
        # ACCESS TOKEN
        # -------------------------------------------------

        access_token = response.get(
            "access_token"
        )

        if not access_token:

            st.error(
                "Authentication failed: "
                "access token was not returned."
            )

            st.stop()


        # -------------------------------------------------
        # GET USER
        # -------------------------------------------------

        user = get_current_user(
            access_token
        )

        if not user:

            st.error(
                "Authentication failed: "
                "could not retrieve user."
            )

            st.stop()


        # -------------------------------------------------
        # USER INFORMATION
        # -------------------------------------------------

        user_id = user.get(
            "id"
        )

        user_email = user.get(
            "email"
        )

        if not user_id:

            st.error(
                "Authentication failed: "
                "user ID was not returned."
            )

            st.stop()


        # -------------------------------------------------
        # SAVE USER SESSION
        # -------------------------------------------------

        st.session_state[
            "user_id"
        ] = user_id

        st.session_state[
            "user_email"
        ] = user_email

        st.session_state[
            "access_token"
        ] = access_token

        if response.get(
            "refresh_token"
        ):

            st.session_state[
                "refresh_token"
            ] = response.get(
                "refresh_token"
            )


        # -------------------------------------------------
        # REMOVE OAUTH PARAMETERS
        # -------------------------------------------------

        st.query_params.clear()


        # -------------------------------------------------
        # RELOAD APP
        # -------------------------------------------------

        st.rerun()


    except Exception as exc:

        st.error(
            f"Authentication failed: {exc}"
        )

        st.stop()


# =========================================================
# LOGIN PAGE
# =========================================================

if not st.session_state.get("user_id"):

    st.markdown(
        """
        <style>
        .login-page {
            min-height: 78vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 30px 15px;
        }
        .login-card {
            width: 100%;
            max-width: 520px;
            padding: 46px 42px;
            border: 1px solid rgba(128,128,128,.22);
            border-radius: 24px;
            background: rgba(255,255,255,.04);
            box-shadow: 0 18px 55px rgba(0,0,0,.12);
            text-align: center;
        }
        .login-icon {
            width: 72px;
            height: 72px;
            margin: 0 auto 20px auto;
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 34px;
            background: linear-gradient(135deg,#667eea,#764ba2);
        }
        .login-title {
            font-size: 32px;
            font-weight: 750;
            margin-bottom: 10px;
        }
        .login-subtitle {
            font-size: 16px;
            opacity: .72;
            line-height: 1.6;
            margin-bottom: 28px;
        }
        .login-badge {
            display: inline-block;
            padding: 7px 13px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 20px;
            border: 1px solid rgba(128,128,128,.25);
        }
        .login-footer {
            margin-top: 22px;
            font-size: 12px;
            opacity: .55;
        }
        </style>

        <div class="login-page">
            <div class="login-card">
                <div class="login-icon">🤖</div>
                <div class="login-badge">AI • RAG • MCP • LangGraph</div>
                <div class="login-title">LangGraph MCP Chatbot</div>
                <div class="login-subtitle">
                    Your intelligent AI workspace for conversations,
                    memory, documents, and powerful tools.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # -----------------------------------------------------
    # CREATE GOOGLE LOGIN URL
    # -----------------------------------------------------

    try:
        login_url = str(get_google_login_url())

    except Exception as exc:
        st.error(
            f"Could not create Google login URL: {exc}"
        )
        st.stop()

    # -----------------------------------------------------
    # GOOGLE LOGIN BUTTON
    # -----------------------------------------------------

    st.markdown(
        """
        <div style="
            max-width:520px;
            margin:-170px auto 0 auto;
            text-align:center;
        ">
        """,
        unsafe_allow_html=True
    )

    st.link_button(
        "🔵  Continue with Google",
        url=login_url,
        use_container_width=True
    )

    st.markdown(
        """
        <div style="
            text-align:center;
            margin-top:18px;
            font-size:12px;
            opacity:.55;
        ">
            🔒 Secure authentication with Google & Supabase
        </div>
        """,
        unsafe_allow_html=True
    )

    st.stop()

# =========================================================
# AUTHENTICATED USER
# =========================================================

user_id = st.session_state.get(
    "user_id"
)

if not user_id:

    st.error(
        "Authentication is incomplete. "
        "Please sign in again."
    )

    st.stop()


# =========================================================
# LOAD USER THREADS
# =========================================================

if "chat_threads" not in st.session_state:

    st.session_state[
        "chat_threads"
    ] = [

        str(thread_id)

        for thread_id in retrieve_all_threads(
            user_id
        )
    ]


# =========================================================
# REGISTER CURRENT THREAD
# =========================================================

current_thread_id = st.session_state[
    "thread_id"
]

register_thread(
    user_id,
    current_thread_id
)

add_thread(
    current_thread_id
)


# =========================================================
# SIDEBAR
# =========================================================

st.sidebar.title(
    "LangGraph Chatbot"
)


# =========================================================
# USER EMAIL
# =========================================================

if st.session_state.get(
    "user_email"
):

    st.sidebar.caption(
        f"👤 {st.session_state['user_email']}"
    )


# =========================================================
# LOGOUT
# =========================================================

if st.sidebar.button(
    "🚪 Logout"
):

    logout()

    for key in [
        "user_id",
        "user_email",
        "access_token",
        "refresh_token",
        "chat_threads",
        "message_history",
        "thread_id",
        "thread_files"
    ]:

        st.session_state.pop(
            key,
            None
        )

    st.query_params.clear()

    st.rerun()


# =========================================================
# NEW CHAT
# =========================================================

if st.sidebar.button(
    "➕ New Chat"
):

    reset_chat()

    st.rerun()


# =========================================================
# PDF
# =========================================================

st.sidebar.header(
    "📄 PDF"
)

thread_id = st.session_state[
    "thread_id"
]

uploaded_file = st.sidebar.file_uploader(
    "Upload a PDF",
    type=["pdf"],
    key=f"pdf_uploader_{thread_id}"
)


if (
    uploaded_file is not None
    and
    st.session_state[
        "thread_files"
    ].get(
        thread_id
    )
    != uploaded_file.name
):

    ingest_pdf(
        file_bytes=uploaded_file.getvalue(),
        thread_id=thread_id,
        filename=uploaded_file.name
    )

    st.session_state[
        "thread_files"
    ][
        thread_id
    ] = uploaded_file.name


document_metadata = thread_document_metadata(
    thread_id
)


if document_metadata:

    st.sidebar.info(
        f"📄 {document_metadata['filename']}"
    )

    st.sidebar.write(
        f"Pages: {document_metadata['documents']}"
    )

    st.sidebar.write(
        f"Chunks: {document_metadata['chunks']}"
    )


# =========================================================
# USER CONVERSATIONS
# =========================================================

st.sidebar.header(
    "My Conversations"
)


for thread_id in st.session_state[
    "chat_threads"
]:

    thread_id = str(
        thread_id
    )

    chat_name = get_chat_name(
        thread_id
    )

    if st.sidebar.button(
        chat_name,
        key=f"thread_{thread_id}"
    ):

        st.session_state[
            "thread_id"
        ] = thread_id

        messages = load_conversation(
            thread_id
        )

        temp_messages = []

        for msg in messages:

            # -------------------------------------------------
            # USER MESSAGE
            # -------------------------------------------------

            if isinstance(
                msg,
                HumanMessage
            ):

                temp_messages.append({
                    "role": "user",
                    "content": msg.content
                })


            # -------------------------------------------------
            # ASSISTANT MESSAGE
            # -------------------------------------------------

            elif isinstance(
                msg,
                (
                    AIMessage,
                    AIMessageChunk
                )
            ):

                if getattr(
                    msg,
                    "tool_calls",
                    None
                ):

                    continue

                content = msg.content


                # -------------------------------------------------
                # STRING CONTENT
                # -------------------------------------------------

                if (
                    isinstance(
                        content,
                        str
                    )
                    and content
                ):

                    temp_messages.append({
                        "role": "assistant",
                        "content": content
                    })


                # -------------------------------------------------
                # LIST CONTENT
                # -------------------------------------------------

                elif isinstance(
                    content,
                    list
                ):

                    text = ""

                    for block in content:

                        if isinstance(
                            block,
                            dict
                        ):

                            block_text = block.get(
                                "text"
                            )

                            if block_text:

                                text += block_text

                    if text:

                        temp_messages.append({
                            "role": "assistant",
                            "content": text
                        })


        st.session_state[
            "message_history"
        ] = temp_messages

        st.rerun()


# =========================================================
# MAIN CHAT
# =========================================================

st.title(
    "LangGraph MCP Chatbot"
)


# =========================================================
# DISPLAY CHAT HISTORY
# =========================================================

for message in st.session_state[
    "message_history"
]:

    with st.chat_message(
        message["role"]
    ):

        st.write(
            message["content"]
        )


# =========================================================
# USER INPUT
# =========================================================

user_input = st.chat_input(
    "Type here"
)


if user_input:

    # -----------------------------------------------------
    # USER MESSAGE
    # -----------------------------------------------------

    st.session_state[
        "message_history"
    ].append({
        "role": "user",
        "content": user_input
    })


    with st.chat_message(
        "user"
    ):

        st.write(
            user_input
        )


    thread_id = st.session_state[
        "thread_id"
    ]


    # -----------------------------------------------------
    # REGISTER THREAD
    # -----------------------------------------------------

    register_thread(
        user_id,
        thread_id
    )


    # =====================================================
    # LANGGRAPH CONFIG
    # =====================================================

    CONFIG = {

        "configurable": {

            "thread_id": thread_id,

            "user_id": user_id

        },

        "metadata": {

            "thread_id": thread_id,

            "user_id": user_id

        },

        "run_name": "chat_turn"
    }


    # =====================================================
    # ASSISTANT RESPONSE
    # =====================================================

    with st.chat_message(
        "assistant"
    ):

        status_holder = {
            "box": None
        }


        # -------------------------------------------------
        # STREAM FUNCTION
        # -------------------------------------------------

        def ai_only_stream():

            event_queue = queue.Queue()


            async def run_stream():

                try:

                    async for (
                        message_chunk,
                        metadata
                    ) in chatbot.astream(

                        {
                            "messages": [
                                HumanMessage(
                                    content=user_input
                                )
                            ]
                        },

                        config=CONFIG,

                        stream_mode="messages"

                    ):

                        event_queue.put(
                            (
                                message_chunk,
                                metadata
                            )
                        )


                except Exception as exc:

                    event_queue.put(
                        (
                            "error",
                            exc
                        )
                    )


                finally:

                    event_queue.put(
                        None
                    )


            submit_async_task(
                run_stream()
            )


            # -------------------------------------------------
            # READ STREAM
            # -------------------------------------------------

            while True:

                item = event_queue.get()


                if item is None:

                    break


                message_chunk, metadata = item


                if message_chunk == "error":

                    raise metadata


                node_name = metadata.get(
                    "langgraph_node"
                )


                print(
                    "[STREAM] NODE:",
                    node_name,
                    "| TYPE:",
                    type(
                        message_chunk
                    ).__name__
                )


                # =================================================
                # TOOL MESSAGE
                # =================================================

                if isinstance(
                    message_chunk,
                    ToolMessage
                ):

                    tool_name = getattr(
                        message_chunk,
                        "name",
                        "tool"
                    )


                    if status_holder[
                        "box"
                    ] is None:

                        status_holder[
                            "box"
                        ] = st.status(
                            f"🔧 Using `{tool_name}`...",
                            expanded=True
                        )


                    else:

                        status_holder[
                            "box"
                        ].update(
                            label=(
                                f"🔧 Using "
                                f"`{tool_name}`..."
                            ),
                            state="running",
                            expanded=True
                        )


                    continue


                # =================================================
                # ONLY CHAT NODE
                # =================================================

                if node_name != "chat_node":

                    continue


                if isinstance(
                    message_chunk,
                    (
                        AIMessage,
                        AIMessageChunk
                    )
                ):

                    if getattr(
                        message_chunk,
                        "tool_calls",
                        None
                    ):

                        continue


                    content = message_chunk.content


                    # -------------------------------------------------
                    # STRING
                    # -------------------------------------------------

                    if isinstance(
                        content,
                        str
                    ):

                        if content:

                            yield content


                    # -------------------------------------------------
                    # LIST
                    # -------------------------------------------------

                    elif isinstance(
                        content,
                        list
                    ):

                        for block in content:

                            if isinstance(
                                block,
                                dict
                            ):

                                text = block.get(
                                    "text"
                                )

                                if text:

                                    yield text


        # =================================================
        # DISPLAY RESPONSE
        # =================================================

        ai_message = st.write_stream(
            ai_only_stream()
        )


        # =================================================
        # TOOL COMPLETE
        # =================================================

        if status_holder[
            "box"
        ] is not None:

            status_holder[
                "box"
            ].update(
                label="✅ Tool finished",
                state="complete",
                expanded=False
            )


    # =====================================================
    # SAVE ASSISTANT RESPONSE
    # =====================================================

    st.session_state[
        "message_history"
    ].append({
        "role": "assistant",
        "content": ai_message
    })