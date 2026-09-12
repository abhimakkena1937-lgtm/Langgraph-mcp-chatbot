# LangGraph MCP Chatbot

A production-oriented chatbot built with LangGraph, Streamlit, and PostgreSQL, featuring short-term conversation memory, long-term user memory, MCP tools, RAG/PDF support, and automatic conversation summarization.

## Features

- LangGraph-based conversational workflow
- Short-Term Memory (STM) using PostgreSQL checkpoints
- Long-Term Memory (LTM) using PostgreSQL Store
- Automatic conversation summarization when context becomes large
- MCP tool integration
- DuckDuckGo web search
- PDF ingestion and RAG using FAISS
- Google Gemini LLM
- Streamlit chat interface
- Persistent conversation threads
- Persistent user-specific memories
- Asynchronous PostgreSQL checkpointing

## Architecture

```text
                    +---------------------+
                    |     Streamlit UI    |
                    +----------+----------+
                               |
                               v
                    +---------------------+
                    |     LangGraph       |
                    |      Workflow       |
                    +----------+----------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
       +-------------+  +-------------+  +-------------+
       | Short-Term  |  | Long-Term   |  | MCP Tools  |
       |   Memory    |  |   Memory    |  |            |
       +------+------+  +------+------+  +------+------+
              |                |                |
              +----------------+----------------+
                               |
                               v
                    +---------------------+
                    |    Google Gemini    |
                    +---------------------+

                    +---------------------+
                    |     PostgreSQL      |
                    |                     |
                    | STM Checkpoints     |
                    | LTM Memory Store    |
                    +---------------------+
```

## LangGraph Workflow

The chatbot uses a stateful LangGraph workflow:

```text
START
  |
  v
check_context_before_chat
  |
  +-- summarize --> summarize_conversation
  |                       |
  |                       v
  |                 remember_node
  |                       |
  |                       v
  |                    chat_node
  |
  +-- continue --> remember_node
                       |
                       v
                    chat_node
                       |
              +--------+--------+
              |                 |
            tools              END
              |
              v
           ToolNode
              |
              v
   check_context_after_tools
              |
        +-----+-----+
        |           |
    summarize    continue
        |           |
        v           |
summarize_after_tools
        |
        v
     chat_node
```

## Memory System

### Short-Term Memory

Short-term memory maintains the conversation history for each conversation thread.

It uses:

```text
AsyncPostgresSaver
```

Conversation checkpoints are stored in PostgreSQL and identified using a `thread_id`.

The chatbot also monitors the conversation context and automatically summarizes older messages when the context becomes too large.

### Long-Term Memory

Long-term memory stores useful user-specific information across different conversations.

It uses:

```text
PostgresStore
```

Memories are stored under a user-specific namespace:

```text
("user", user_id, "data")
```

The memory extraction process:

1. Reads the latest user message.
2. Retrieves existing memories.
3. Uses structured LLM output to identify useful memories.
4. Checks whether a memory is new.
5. Saves only new useful memories.
6. Makes stored memories available to future conversations.

Example:

```text
User:
I like badminton.

Long-Term Memory:
Abhinay likes badminton.
```

A future conversation can then use this information.

## Conversation Summarization

The chatbot monitors the approximate token count of the conversation context.

Current configuration:

```text
MAX_CONTEXT_TOKENS = 20000
RECENT_CONTEXT_TOKENS = 4000
```

When the context exceeds the configured limit:

1. Older conversation messages are identified.
2. Recent messages are preserved.
3. Older messages are summarized.
4. Older messages are removed from active state.
5. The summary is retained as part of the conversation state.

This keeps the active context manageable while preserving important conversation information.

## MCP Tools

The chatbot supports MCP-based tools through:

```text
langchain-mcp-adapters
```

MCP tools can be connected to the LangGraph agent and invoked when required by the conversation.

The frontend also provides tool execution status while the agent is using tools.

## RAG and PDF Support

The project supports PDF ingestion and retrieval.

The pipeline uses:

```text
PyPDFLoader
      |
      v
RecursiveCharacterTextSplitter
      |
      v
FAISS
      |
      v
Retrieval
      |
      v
LLM
```

PDF documents can be processed into chunks and stored in a FAISS vector store for retrieval-augmented responses.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application development |
| LangGraph | Agent workflow and state management |
| LangChain | LLM and tool integration |
| Google Gemini | Large language model |
| PostgreSQL | Persistent memory and checkpoints |
| Streamlit | Web interface |
| MCP | External tool integration |
| FAISS | Vector similarity search |
| PyPDF | PDF processing |
| uv | Python dependency management |
| Docker | PostgreSQL container |

## Project Structure

```text
campus_x_langgraph/
|
+-- chatbot_stm.py
+-- streamlit_frontend_stm.py
+-- docker-compose.yml
+-- pyproject.toml
+-- requirements.txt
+-- uv.lock
+-- README.md
+-- .env.example
+-- .gitignore
+-- .python-version
```

## Requirements

- Python 3.13+
- Docker
- uv
- Google Gemini API key

## Installation

Clone the repository:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd campus_x_langgraph
```

Create the environment and install dependencies:

```bash
uv sync
```

## Environment Variables

Create a `.env` file:

```env
GOOGLE_API_KEY=your_google_api_key
```

Never commit `.env` to GitHub.

A template is provided as:

```text
.env.example
```

## PostgreSQL

The project uses PostgreSQL for both short-term and long-term memory.

Start PostgreSQL using Docker Compose:

```bash
docker compose up -d
```

The development configuration exposes PostgreSQL on:

```text
localhost:5442
```

The application connects to:

```text
postgresql://postgres:postgres@localhost:5442/postgres
```

Check the container:

```bash
docker ps
```

Stop PostgreSQL:

```bash
docker compose down
```

## Run the Application

Start the Streamlit frontend:

```bash
uv run streamlit run streamlit_frontend_stm.py
```

Streamlit will provide the local application URL in the terminal.

## Memory Persistence

Conversation memory is associated with a conversation `thread_id`.

Long-term user memories are associated with a `user_id`.

This allows the application to maintain:

```text
Thread-specific conversation history
+
User-specific long-term memories
```

across conversations.

## Development

Compile-check the main Python files:

```bash
uv run python -m py_compile chatbot_stm.py streamlit_frontend_stm.py
```

Synchronize dependencies:

```bash
uv sync
```

Update the lock file after dependency changes:

```bash
uv lock
```

## Docker Deployment

For local development, PostgreSQL runs as a Docker container while the Streamlit application runs directly on the host.

For a fully containerized deployment, the Streamlit container should connect to the PostgreSQL service using the Docker service name rather than `localhost`.

For example:

```text
postgres:5432
```

rather than:

```text
localhost:5442
```

A persistent Docker volume should be used for PostgreSQL data in production deployments.

## Security

Do not commit:

```text
.env
```

or any API keys, passwords, credentials, or other secrets.

Use environment variables or the deployment platform's secret-management system for production credentials.

The PostgreSQL credentials included in the development Docker configuration are intended for local development and should be changed for production.

## Future Improvements

- Production-grade authentication
- Improved memory deduplication
- Memory editing and deletion
- Better RAG document management
- Production database configuration
- Containerized Streamlit deployment
- Observability and tracing
- Automated testing
- Deployment to a cloud platform

## Author

Abhinay Makkena

## License

This project is intended for educational and development purposes.