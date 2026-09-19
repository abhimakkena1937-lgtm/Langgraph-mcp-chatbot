from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import os,threading,requests,selectors,asyncio,tempfile
from typing import TypedDict,Annotated,Any,Optional,List
from dotenv import load_dotenv
from langgraph.graph import StateGraph,START,END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode,tools_condition
from langchain_core.messages import BaseMessage,SystemMessage,HumanMessage,RemoveMessage,AIMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI,GoogleGenerativeAIEmbeddings
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.messages.utils import count_tokens_approximately,trim_messages

#ltm
from langgraph.store.postgres import PostgresStore
from pydantic import BaseModel,Field
import uuid

load_dotenv()


# CONTEXT CONFIG


MAX_CONTEXT_TOKENS=20000
RECENT_CONTEXT_TOKENS=4000
SAFETY_MARGIN=1000

def count_context_tokens(messages):
    return count_tokens_approximately(messages)


# ASYNC EVENT LOOP


_ASYNC_LOOP=asyncio.SelectorEventLoop(selectors.SelectSelector())
_ASYNC_THREAD=threading.Thread(
    target=_ASYNC_LOOP.run_forever,
    
    daemon=True
)
_ASYNC_THREAD.start()

def _submit_async(coro):
    return asyncio.run_coroutine_threadsafe(coro,_ASYNC_LOOP)

def run_async(coro):
    return _submit_async(coro).result()

def submit_async_task(coro):
    return _submit_async(coro)

# LLM / EMBEDDINGS


llm=ChatGoogleGenerativeAI(
    model="gemini-3.1-flash-lite",
    temperature=0
)

embeddings=GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001"
)


# THREAD RETRIEVERS


_THREAD_RETRIEVERS:dict[str,Any]={}
_THREAD_METADATA:dict[str,dict]={}

def _get_retriever(thread_id:Optional[str]):
    return _THREAD_RETRIEVERS.get(thread_id) if thread_id else None


# PDF INGESTION


def ingest_pdf(
    file_bytes:bytes,
    thread_id:str,
    filename:Optional[str]=None
)->dict:

    if not file_bytes:
        raise ValueError("No bytes received for PDF")

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp_file:
        temp_file.write(file_bytes)
        temp_path=temp_file.name

    try:
        docs=PyPDFLoader(temp_path).load()

        splitter=RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n","\n"," ",""]
        )

        chunks=splitter.split_documents(docs)

        vector_store=FAISS.from_documents(
            chunks,
            embeddings
        )

        retriever=vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k":4}
        )

        thread_id=str(thread_id)
        file_name=filename or os.path.basename(temp_path)

        _THREAD_RETRIEVERS[thread_id]=retriever

        _THREAD_METADATA[thread_id]={
            "filename":file_name,
            "documents":len(docs),
            "chunks":len(chunks)
        }

        return {
            "filename":file_name,
            "documents":len(docs),
            "chunks":len(chunks)
        }

    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass

# ============================================================
# NORMAL TOOLS
# ============================================================

search_tool=DuckDuckGoSearchRun(region="us-en")

@tool
def get_stock_price(symbol:str)->dict:
    """Fetch the latest stock price for a stock symbol."""

    url=(
        f"https://www.alphavantage.co/query"
        f"?function=GLOBAL_QUOTE"
        f"&symbol={symbol}"
        f"&apikey=C9PE94QUEW9VWGFM"
    )

    return requests.get(url).json()

# ============================================================
# RAG TOOL
# ============================================================

@tool
def rag_tool(
    query:str,
    thread_id:Optional[str]
)->dict:
    """Retrieve relevant context from uploaded PDFs."""

    retriever=_get_retriever(thread_id)

    if retriever is None:
        return {
            "error":"No document found for this chat. Please upload a document first",
            "query":query
        }

    result=retriever.invoke(query)

    print("\n"+"="*60)
    print("RAG DEBUG")
    print("THREAD ID:",thread_id)
    print("QUERY:",query)
    print("NUMBER OF CHUNKS:",len(result))

    for i,doc in enumerate(result,1):
        print(f"\n--- CHUNK {i} ---")
        print("METADATA:",doc.metadata)
        print("CONTENT:",doc.page_content[:300])

    print("="*60+"\n")

    return {
        "query":query,
        "context":[doc.page_content for doc in result],
        "metadata":[doc.metadata for doc in result],
        "source_file":_THREAD_METADATA.get(
            str(thread_id),{}
        ).get("filename")
    }

# ============================================================
# MCP SERVERS
# ============================================================


import os

IS_RAILWAY = os.getenv("DEPLOYMENT_ENV") == "railway"
HORIZON_API_KEY=os.getenv("HORIZON_API_KEY")

SERVERS = {}

if not IS_RAILWAY:
    SERVERS = {
        "Text Utility Server": {
            "transport": "stdio",
            "command": r"C:\Users\abhim\.local\bin\uv.exe",
            "args": [
                "run",
                "--directory",
                r"C:\Users\abhim\AppData\Roaming\Claude\demo_local_server",
                "fastmcp",
                "run",
                r"C:\Users\abhim\AppData\Roaming\Claude\demo_local_server\main.py"
            ]
        },
        "Utility Server": {
            "transport": "stdio",
            "command": r"C:\Users\abhim\.local\bin\uv.exe",
            "args": [
                "run",
                "--directory",
                r"C:\fast_mcp_demo_server",
                "fastmcp",
                "run",
                r"C:\fast_mcp_demo_server\demo.py"
            ]
        },
        "manim-server": {
            "transport": "stdio",
            "command": r"C:\Users\abhim\manim-project\.venv\Scripts\python.exe",
            "args": [
                r"C:\Users\abhim\manim-project\manim-mcp-server\src\manim_server.py"
            ],
            "env": {
                "MANIM_EXECUTABLE":
                    r"C:\Users\abhim\manim-project\.venv\Scripts\manim.exe"
            }
        }
    }

if HORIZON_API_KEY:
    SERVERS["Expense Tracker"]={
        "transport":"streamable_http",
        "url":"https://dramatic-crimson-minnow.fastmcp.app/mcp",
        "headers":{
            "Authorization":f"Bearer {HORIZON_API_KEY}"
        }
    }


# MCP CLIENT


client=MultiServerMCPClient(SERVERS)

async def load_mcp_tools():

    print("="*60)
    print("CONNECTING TO MCP SERVERS")
    print("="*60)

    tools=await client.get_tools()

    print("\nMCP CONNECTION SUCCESSFUL")
    print(f"Total MCP tools loaded: {len(tools)}\n")
    print("MCP TOOLS:")

    for tool_item in tools:
        print(f"  - {tool_item.name}")

    print("="*60)

    return tools

mcp_tools=run_async(load_mcp_tools())

# ALL TOOLS


tools=[
    search_tool,
    get_stock_price,
    rag_tool,
    *mcp_tools
]

print("\n"+"="*60)
print("ALL TOOLS AVAILABLE TO GEMINI")
print("="*60)

for tool_item in tools:
    print(f"NAME: {tool_item.name}")

print("="*60)

llm_with_tools=llm.bind_tools(tools)


# long term memory schema

class MemoryItem(BaseModel):
    text:str=Field(description="atomic user specific memory")
    is_new:bool=Field(description="checking if  the memory new or already present in memory store")
class MemoryDecision(BaseModel):
    should_write:bool
    memories:List[MemoryItem]


memory_extractor=llm.with_structured_output(MemoryDecision)

# ============================================================
# MEMORY EXTRACTION PROMPT
# ============================================================

MEMORY_PROMPT = """
You manage long-term user memories.

Existing memories:
{user_memories}

Review the latest user message.

Rules:
- Extract only explicitly stated user-specific facts.
- Do not speculate.
- Keep memories atomic.
- Do not save temporary conversation details.
- is_new=True only if the memory is not already present.
- should_write=True if at least one useful new memory exists.
- If there are no useful new memories, set should_write=False.
- Do not invent information.
"""


# STATE


class ChatState(TypedDict):
    messages:Annotated[list[BaseMessage],add_messages]
    summary:Optional[str]


# remember node decides memory to store if it is new and worth to store
def remember_node(state:ChatState,config=None):
    user_id=config["configurable"]["user_id"]
    namespace=("user",user_id,"data")
    user_memories=memory_store.search(namespace)
    exsisting_memories=(
        "\n".join( mem.value["data"] for mem in user_memories)
        if user_memories else "(empty)"
    )
    last_user_message=None
    for msg in reversed(state["messages"]):
        if isinstance(msg,HumanMessage):
            last_user_message=msg.content
            break
    if not last_user_message:
        return {}
    decision:MemoryDecision=memory_extractor.invoke([
        SystemMessage(content=MEMORY_PROMPT.format(user_memories=exsisting_memories)),
        HumanMessage(content=last_user_message)
    ])

    print("\n========== MEMORY EXTRACTOR ==========")
    print("DECISION TYPE:", type(decision))
    print("DECISION:", decision)
    print("======================================\n")
    if decision.should_write:
        for memory in decision.memories:
            if memory.is_new and memory.text.strip():
               memory_store.put(namespace,uuid.uuid4(),{"data":memory.text.strip()})
               print("saved",memory.text)
    else:
        print("Nothing Saved")
    return {}

# CONTEXT HELPERS


def get_recent_messages(messages,max_tokens):

    return trim_messages(
        messages,
        max_tokens=max_tokens,
        strategy="last",
        token_counter=count_context_tokens,
        include_system=False,
        start_on="human",
        allow_partial=False
    )

def build_model_messages(state:ChatState,thread_id:str,user_id:str):
    namespace=("user",user_id,"data")
    memories=memory_store.search(namespace)
    user_memories=(
        "\n".join(mem.value["data"] for mem in memories)
        if memories else "(empty)"
    )
    system_prompt=SystemMessage(
        content=(
            "You are a helpful assistant. "

            "For questions about the uploaded PDF, "
            "use the rag_tool. "

            f"The current thread_id is {thread_id}. "

            "Whenever you call rag_tool, always provide "
            "this thread_id.\n\n"

            "Long-term user memories:\n"
            f"{user_memories}\n\n"

            "Use these memories when relevant. "
            "Do not speculate about the user."
        )
        )

    messages=[system_prompt]

    summary=state.get("summary","")

    if summary:
        messages.append(
            SystemMessage(
                content=f"Conversation summary:\n{summary}"
            )
        )

    messages.extend(state["messages"])

    return messages

# CHECK SUMMARIZATION


def check_summarization(state:ChatState,config=None):

    thread_id=config["configurable"]["thread_id"]
    user_id=config["configurable"]["user_id"]

    messages=build_model_messages(
        state,
        thread_id,
        user_id
    )

    context_tokens=count_context_tokens(messages)

    print("\n========== SUMMARY CHECK ==========")
    print("APPROX CONTEXT TOKENS:",context_tokens)
    print("MAX CONTEXT TOKENS:",MAX_CONTEXT_TOKENS)

    if context_tokens>MAX_CONTEXT_TOKENS:

        print("RESULT: SUMMARIZE")
        print("===================================\n")

        return "summarize"

    print("RESULT: CONTINUE")
    print("===================================\n")

    return "continue"

# ============================================================
# SUMMARIZE CONVERSATION
# ============================================================

def summarize_conversation(state:ChatState):

    existing_summary=state.get("summary","")

    # Preserve the most recent conversation
    recent_messages=get_recent_messages(
        state["messages"],
        RECENT_CONTEXT_TOKENS
    )

    recent_message_ids={
        message.id
        for message in recent_messages
    }

    # Everything outside recent context becomes summary material
    older_messages=[
        message
        for message in state["messages"]
        if message.id not in recent_message_ids
    ]
    if not older_messages:
        return {}

    print("\n========== SUMMARIZATION ==========")
    print("OLDER MESSAGE COUNT:",len(older_messages))
    print("RECENT MESSAGE COUNT:",len(recent_messages))
    print(
        "OLDER TOKEN COUNT:",
        count_context_tokens(older_messages)
    )
    print(
        "RECENT TOKEN COUNT:",
        count_context_tokens(recent_messages)
    )

    if existing_summary:

        prompt=f"""Existing conversation summary:

{existing_summary}

Update this summary using the older conversation below.

Preserve:
- important facts
- important technical details
- user requirements
- decisions already made
- unfinished tasks
- important context needed for future questions

Remove:
- repetition
- small talk
- unnecessary details

Do not invent information."""

    else:

        prompt="""Summarize the older conversation below.

Preserve:
- important facts
- important technical details
- user requirements
- decisions already made
- unfinished tasks
- important context needed for future questions

Remove:
- repetition
- small talk
- unnecessary details

Do not invent information."""

    summary_messages=[
        SystemMessage(content=prompt),
        *older_messages
    ]

    response=llm.invoke(summary_messages)

    return {
        "summary":response.content,
        "messages":[
            RemoveMessage(id=message.id)
            for message in older_messages
        ]
    }


# CHAT NODE


async def chat_node(state:ChatState,config=None):

    thread_id=config["configurable"]["thread_id"]
    user_id=config["configurable"]["user_id"]

    messages=build_model_messages(
        state,
        thread_id,
        user_id
    )

    context_tokens=count_context_tokens(messages)

    print("\n========== MODEL INPUT ==========")
    print("APPROX CONTEXT TOKENS:",context_tokens)

    for message in messages:
        print(
            type(message).__name__,
            ":",
            getattr(message,"content","")
        )

    print("=================================\n")

    response=await llm_with_tools.ainvoke(messages)

    return {"messages":[response]}


# TOOL NODE


tool_node=ToolNode(tools)


# POSTGRES CHECKPOINTER


POSTGRES_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5442/postgres"
)

async def init_checkpointer():

    checkpointer_cm=AsyncPostgresSaver.from_conn_string(
        POSTGRES_URL
    )

    checkpointer=await checkpointer_cm.__aenter__()

    await checkpointer.setup()

    return checkpointer,checkpointer_cm

checkpointer,checkpointer_cm=run_async(
    init_checkpointer()
)


memory_store_cm = PostgresStore.from_conn_string(POSTGRES_URL)
memory_store = memory_store_cm.__enter__()
memory_store.setup()
print("memory store ready")

# GRAPH


graph=StateGraph(ChatState)

graph.add_node("chat_node",chat_node)
graph.add_node("remember_node",remember_node)
graph.add_node("tools",tool_node)
graph.add_node("summarize",summarize_conversation)

# Dummy nodes (return state unchanged)
graph.add_node("check_context_before_chat",lambda state:{})
graph.add_node("check_context_after_tools",lambda state:{})

# START → Check context before first LLM call
graph.add_edge(START,"check_context_before_chat")

# Route: summarize or chat
graph.add_conditional_edges(
    "check_context_before_chat",
    check_summarization,
    {
        "summarize":"summarize",
        "continue":"remember_node"
    }
)

# After summarization → Chat
graph.add_edge("summarize","remember_node")
graph.add_edge("remember_node","chat_node")

# Chat → Tools or END
graph.add_conditional_edges(
    "chat_node",
    tools_condition,
    {
        "tools":"tools",
        "__end__":END
    }
)

# After tools → Check context again
graph.add_edge("tools","check_context_after_tools")

# Route again: summarize if tool output increased context

# in this case after summarization it routs again to remember node so we create another
#summarization node and route to chatnode 

graph.add_node("summarize_after_tools",summarize_conversation)

graph.add_conditional_edges(
    "check_context_after_tools",
    check_summarization,
    {
        "summarize":"summarize_after_tools",
        "continue":"chat_node"
    }
)
graph.add_edge("summarize_after_tools","chat_node")

# COMPILE

chatbot=graph.compile(
    checkpointer=checkpointer,
    store=memory_store
)


# THREADS


async def _alist_threads():

    all_threads=[]
    seen_threads=set()

    async for checkpoint in checkpointer.alist(None):

        thread_id=(
            checkpoint.config
            .get("configurable",{})
            .get("thread_id")
        )

        if thread_id and thread_id not in seen_threads:

            seen_threads.add(thread_id)
            all_threads.append(thread_id)

    return all_threads

def retrieve_all_threads():
    return run_async(_alist_threads())


# DOCUMENT METADATA


def thread_document_metadata(thread_id:str)->dict:
    return _THREAD_METADATA.get(
        str(thread_id),
        {}
    )

def thread_has_document(thread_id:str)->bool:
    return str(thread_id) in _THREAD_RETRIEVERS