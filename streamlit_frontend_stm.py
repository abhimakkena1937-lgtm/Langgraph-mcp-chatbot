import queue
import uuid
import streamlit as st
from chatbot_stm import chatbot,retrieve_all_threads,submit_async_task,ingest_pdf,thread_document_metadata
from langchain_core.messages import AIMessage,AIMessageChunk,HumanMessage,ToolMessage

def generate_thread_id(): return str(uuid.uuid4())

def add_thread(thread_id):
    thread_id=str(thread_id)
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)

def reset_chat():
    thread_id=generate_thread_id()
    st.session_state["thread_id"]=thread_id
    st.session_state["message_history"]=[]
    add_thread(thread_id)

def load_conversation(thread_id):
    state=chatbot.get_state(config={"configurable":{"thread_id":str(thread_id)}})
    return state.values.get("messages",[])

def get_chat_name(thread_id):
    messages=load_conversation(thread_id)
    for message in messages:
        if isinstance(message,HumanMessage):
            content=message.content
            if isinstance(content,str):
                content=content.strip().replace("\n"," ")
                if content: return content[:40]+("..." if len(content)>40 else "")
    return "New Chat"

if "message_history" not in st.session_state: st.session_state["message_history"]=[]
if "thread_id" not in st.session_state: st.session_state["thread_id"]=generate_thread_id()
if "user_id" not in st.session_state: st.session_state["user_id"]="u1"
if "thread_files" not in st.session_state: st.session_state["thread_files"]={}
if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"]=[str(thread_id) for thread_id in retrieve_all_threads()]

user_id=st.session_state["user_id"]
add_thread(st.session_state["thread_id"])
st.sidebar.title("LangGraph MCP Chatbot")

if st.sidebar.button("➕ New Chat"):
    reset_chat()
    st.rerun()

st.sidebar.header("📄 PDF")
thread_id=st.session_state["thread_id"]
uploaded_file=st.sidebar.file_uploader("Upload a PDF",type=["pdf"],key=f"pdf_uploader_{thread_id}")

if uploaded_file is not None and st.session_state["thread_files"].get(thread_id)!=uploaded_file.name:
    ingest_pdf(file_bytes=uploaded_file.getvalue(),thread_id=thread_id,filename=uploaded_file.name)
    st.session_state["thread_files"][thread_id]=uploaded_file.name

document_metadata=thread_document_metadata(thread_id)

if document_metadata:
    st.sidebar.info(f"📄 {document_metadata['filename']}")
    st.sidebar.write(f"Pages: {document_metadata['documents']}")
    st.sidebar.write(f"Chunks: {document_metadata['chunks']}")

st.sidebar.header("My Conversations")

for thread_id in reversed(st.session_state["chat_threads"]):
    thread_id=str(thread_id)
    chat_name=get_chat_name(thread_id)
    if st.sidebar.button(chat_name,key=f"thread_{thread_id}"):
        st.session_state["thread_id"]=thread_id
        messages=load_conversation(thread_id)
        temp_messages=[]
        for msg in messages:
            if isinstance(msg,HumanMessage):
                temp_messages.append({"role":"user","content":msg.content})
            elif isinstance(msg,(AIMessage,AIMessageChunk)):
                if getattr(msg,"tool_calls",None): continue
                content=msg.content
                if isinstance(content,str) and content:
                    temp_messages.append({"role":"assistant","content":content})
                elif isinstance(content,list):
                    text=""
                    for block in content:
                        if isinstance(block,dict):
                            block_text=block.get("text")
                            if block_text: text+=block_text
                    if text: temp_messages.append({"role":"assistant","content":text})
        st.session_state["message_history"]=temp_messages
        st.rerun()

st.title("LangGraph MCP Chatbot")

for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_input=st.chat_input("Type here")

if user_input:
    st.session_state["message_history"].append({"role":"user","content":user_input})
    with st.chat_message("user"): st.write(user_input)

    thread_id=st.session_state["thread_id"]
    CONFIG={"configurable":{"thread_id":thread_id,"user_id":user_id},"metadata":{"thread_id":thread_id},"run_name":"chat_turn"}

    with st.chat_message("assistant"):
        status_holder={"box":None}

        def ai_only_stream():
            event_queue=queue.Queue()

            async def run_stream():
                try:
                    async for message_chunk,metadata in chatbot.astream(
                        {"messages":[HumanMessage(content=user_input)]},
                        config=CONFIG,
                        stream_mode="messages"
                    ):
                        event_queue.put((message_chunk,metadata))
                except Exception as exc:
                    event_queue.put(("error",exc))
                finally:
                    event_queue.put(None)

            submit_async_task(run_stream())

            while True:
                item=event_queue.get()
                if item is None: break
                message_chunk,metadata=item
                if message_chunk=="error": raise metadata

                node_name=metadata.get("langgraph_node")
                print("[STREAM] NODE:",node_name,"| TYPE:",type(message_chunk).__name__)

                if isinstance(message_chunk,ToolMessage):
                    tool_name=getattr(message_chunk,"name","tool")
                    if status_holder["box"] is None:
                        status_holder["box"]=st.status(f"🔧 Using `{tool_name}`...",expanded=True)
                    else:
                        status_holder["box"].update(label=f"🔧 Using `{tool_name}`...",state="running",expanded=True)
                    continue

                if node_name!="chat_node": continue

                if isinstance(message_chunk,(AIMessage,AIMessageChunk)):
                    if getattr(message_chunk,"tool_calls",None): continue
                    content=message_chunk.content
                    if isinstance(content,str):
                        if content: yield content
                    elif isinstance(content,list):
                        for block in content:
                            if isinstance(block,dict):
                                text=block.get("text")
                                if text: yield text

        ai_message=st.write_stream(ai_only_stream())

        if status_holder["box"] is not None:
            status_holder["box"].update(label="✅ Tool finished",state="complete",expanded=False)

    st.session_state["message_history"].append({"role":"assistant","content":ai_message})