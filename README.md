# LangGraph MCP Chatbot

A production-oriented AI chatbot built with **LangGraph, Streamlit, PostgreSQL, Google Gemini, MCP tools, and RAG**.

The application supports **Google authentication, user-specific authorization, short-term memory, long-term memory, persistent conversation threads, PDF-based RAG, web search, MCP tools, and automatic conversation summarization**.

---

## Features

- LangGraph-based conversational workflow
- Google authentication using Supabase Auth
- Google OAuth login
- User-specific authorization
- User-specific conversation isolation
- Short-Term Memory (STM) using PostgreSQL checkpoints
- Long-Term Memory (LTM) using PostgreSQL Store
- Persistent user-specific memories
- Persistent conversation threads
- Automatic conversation summarization
- MCP tool integration
- Remote MCP server support
- Local MCP server support
- DuckDuckGo web search
- PDF ingestion and RAG using FAISS
- Google Gemini LLM
- Streamlit chat interface
- PostgreSQL persistence
- Asynchronous PostgreSQL checkpointing
- User/thread ownership management
- Railway deployment support
- Environment-based MCP configuration

---

# Architecture

```text
                         +----------------------+
                         |     Google OAuth     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |    Supabase Auth     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |     Streamlit UI     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |      LangGraph       |
                         |       Workflow       |
                         +----------+-----------+
                                    |
              +---------------------+---------------------+
              |                     |                     |
              v                     v                     v
       +-------------+       +-------------+       +-------------+
       | Short-Term  |       | Long-Term   |       | MCP Tools  |
       |   Memory    |       |   Memory    |       |            |
       +------+------+       +------+------+       +------+------+
              |                     |                     |
              +---------------------+---------------------+
                                    |
                                    v
                         +----------------------+
                         |    Google Gemini     |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         |     PostgreSQL       |
                         |                      |
                         | STM Checkpoints     |
                         | LTM Memory Store    |
                         | User Thread Mapping |
                         +----------------------+
```

---

# Authentication & Authorization

The application uses **Google OAuth through Supabase Auth**.

Users must authenticate before accessing the chatbot.

## Authentication Flow

```text
User
 |
 v
Streamlit Login Page
 |
 v
Continue with Google
 |
 v
Google OAuth
 |
 v
Supabase Auth
 |
 v
Authenticated User
 |
 v
LangGraph Chatbot
```

After authentication, the application retrieves the authenticated user's Supabase `user_id`.

The `user_id` is used to associate the user with:

- Conversation threads
- Long-term memories
- User-specific application data

---

# User Authorization

Conversation threads are isolated between users.

The application maintains a PostgreSQL table called:

```text
user_threads
```

The table maps authenticated users to the conversation threads they own.

```text
User A
 |
 +-- Thread 1
 +-- Thread 2
 +-- Thread 3


User B
 |
 +-- Thread 4
 +-- Thread 5
```

User A can only access threads associated with User A.

User B can only access threads associated with User B.

Before loading a conversation, the application checks whether the authenticated user owns the requested `thread_id`.

This prevents users from accessing conversation threads belonging to another account.

## User Thread Ownership Table

```sql
CREATE TABLE IF NOT EXISTS user_threads (
    user_id TEXT NOT NULL,
    thread_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_threads_user_id
ON user_threads(user_id);
```

The table stores:

```text
user_id
thread_id
created_at
```

---

# LangGraph Workflow

The chatbot uses a stateful LangGraph workflow.

```text
START
 |
 v
check_context_before_chat
 |
 +-- summarize --> summarize_conversation
 |                       |
 |                       v
 |                  remember_node
 |                       |
 |                       v
 |                    chat_node
 |
 +-- continue --> remember_node
                       |
                       v
                    chat_node
                       |
             +---------+---------+
             |                   |
           tools                END
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

The workflow allows the chatbot to:

1. Inspect conversation context.
2. Summarize older messages when required.
3. Extract long-term memories.
4. Generate an LLM response.
5. Invoke tools when required.
6. Process tool results.
7. Continue the conversation.
8. Preserve state using PostgreSQL.

---

# Memory System

The chatbot implements two types of memory:

```text
Short-Term Memory
        +
Long-Term Memory
```

---

## Short-Term Memory

Short-term memory maintains the conversation history for an individual conversation thread.

It uses:

```text
AsyncPostgresSaver
```

Conversation checkpoints are stored in PostgreSQL.

Each conversation is identified using:

```text
thread_id
```

Example:

```text
User
 |
 +-- thread_001
 |      |
 |      +-- Message
 |      +-- Message
 |      +-- Message
 |
 +-- thread_002
        |
        +-- Message
        +-- Message
```

Each thread maintains its own conversation state.

---

# Long-Term Memory

Long-term memory stores useful information about a user across different conversations.

It uses:

```text
PostgresStore
```

Memories are stored using a user-specific namespace:

```text
("user", user_id, "data")
```

This ensures that memories are associated with the correct authenticated user.

## Memory Extraction Flow

```text
User Message
     |
     v
Memory Extraction
     |
     v
Existing Memory Search
     |
     v
Structured LLM Decision
     |
     v
Check Whether Memory Is New
     |
     v
Store New Memory
```

The memory extraction process:

1. Reads the latest user message.
2. Retrieves existing memories.
3. Uses structured LLM output.
4. Determines whether useful memory exists.
5. Checks whether the memory is new.
6. Stores the new memory.
7. Makes the memory available in future conversations.

Example:

```text
User:

I like badminton.

Stored Memory:

Abhinay likes badminton.
```

A future conversation belonging to the same authenticated user can use this information.

Different users have separate memory namespaces.

---

# Conversation Summarization

The chatbot automatically summarizes older conversation messages when the active context becomes too large.

Current configuration:

```text
MAX_CONTEXT_TOKENS = 20000

RECENT_CONTEXT_TOKENS = 4000
```

When the context exceeds the configured limit:

```text
Large Conversation
       |
       v
Identify Older Messages
       |
       v
Preserve Recent Messages
       |
       v
Summarize Older Messages
       |
       v
Remove Older Messages
       |
       v
Keep Summary in State
```

This keeps the active context manageable while preserving important information from previous messages.

---

# MCP Tools

The application supports **Model Context Protocol (MCP)** tools using:

```text
langchain-mcp-adapters
```

MCP allows the LangGraph agent to communicate with external tools and services.

Tools can be invoked by the agent when required by the conversation.

The application supports different MCP configurations for different environments.

## Local Environment

Local MCP servers can be configured using local commands and paths.

```text
Local Application
       |
       +-- Local MCP Server
       |
       +-- Local MCP Server
       |
       +-- Remote MCP Server
```

## Railway Environment

Railway cannot directly execute Windows-specific local MCP server paths.

Therefore, deployed environments can use remote MCP servers.

```text
Railway
   |
   +-- Remote MCP Server
```

The application uses an environment variable to distinguish deployment environments.

Example:

```env
DEPLOYMENT_ENV=railway
```

---

# DuckDuckGo Web Search

The chatbot supports web search through DuckDuckGo integration.

The application can use the search tool when the agent determines that external web information is required.

Relevant dependencies include:

```text
ddgs
duckduckgo-search
```

---

# RAG and PDF Support

The project supports PDF ingestion and Retrieval-Augmented Generation (RAG).

The pipeline is:

```text
PDF
 |
 v
PyPDFLoader
 |
 v
RecursiveCharacterTextSplitter
 |
 v
Document Chunks
 |
 v
FAISS
 |
 v
Similarity Retrieval
 |
 v
Google Gemini
 |
 v
Response
```

PDF documents can be uploaded and processed into chunks.

The chunks are stored in a FAISS vector store.

Relevant information is retrieved from the vector store when answering questions about the uploaded document.

---

# Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application development |
| LangGraph | Agent workflow and state management |
| LangChain | LLM and tool integration |
| Google Gemini | Large language model |
| Google OAuth | User authentication |
| Supabase Auth | Authentication and user management |
| PostgreSQL | Persistent memory, checkpoints, and authorization |
| Streamlit | Web interface |
| MCP | External tool integration |
| FAISS | Vector similarity search |
| PyPDF | PDF processing |
| uv | Python dependency management |
| Docker | PostgreSQL container |
| Railway | Cloud deployment |

---

# Project Structure

```text
campus_x_langgraph/
|
+-- chatbot_stm.py
+-- streamlit_frontend_stm.py
+-- auth.py
|
+-- docker-compose.yml
+-- pyproject.toml
+-- requirements.txt
+-- uv.lock
|
+-- README.md
+-- .env.example
+-- .gitignore
+-- .python-version
+-- railway.toml
```

---

# Requirements

Before running the application, install:

- Python 3.13+
- Docker
- uv
- PostgreSQL
- Google Gemini API key
- Supabase project
- Google OAuth credentials

---

# Installation

## 1. Clone the Repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>

cd campus_x_langgraph
```

---

## 2. Install Dependencies

The project uses `uv` for Python dependency management.

Run:

```bash
uv sync
```

This creates/synchronizes the project's Python environment and installs the required dependencies.

---

# Environment Variables

Create a `.env` file in the project root.

Example:

```env
GOOGLE_API_KEY=your_google_api_key

DATABASE_URL=postgresql://postgres:postgres@localhost:5442/postgres

SUPABASE_URL=your_supabase_project_url

SUPABASE_ANON_KEY=your_supabase_anon_key

APP_URL=http://localhost:8501
```

For local MCP configuration, the application can use the default local environment.

For Railway deployment:

```env
DEPLOYMENT_ENV=railway
```

Production example:

```env
GOOGLE_API_KEY=your_google_api_key

DATABASE_URL=your_production_database_url

SUPABASE_URL=your_supabase_project_url

SUPABASE_ANON_KEY=your_supabase_anon_key

APP_URL=https://your-production-domain

DEPLOYMENT_ENV=railway
```

Never commit `.env` to GitHub.

A template is provided:

```text
.env.example
```

---

# Google Authentication Setup

The application uses Google OAuth with Supabase.

The general setup is:

```text
Google Cloud
      |
      v
OAuth Client
      |
      v
Supabase Google Provider
      |
      v
Streamlit Application
```

Required configuration includes:

- Google Cloud OAuth application
- Google OAuth client
- Supabase Google provider
- Supabase redirect URL
- Application redirect URL

The Google OAuth callback is handled through Supabase.

The application then receives the authenticated Supabase user.

---

# PostgreSQL

PostgreSQL is used for:

- Short-term memory checkpoints
- Long-term memory
- User/thread ownership
- Persistent conversation data

For local development, PostgreSQL runs using Docker.

Start PostgreSQL:

```bash
docker compose up -d
```

The development configuration exposes PostgreSQL on:

```text
localhost:5442
```

The default local connection string is:

```text
postgresql://postgres:postgres@localhost:5442/postgres
```

---

# Check PostgreSQL

Check running containers:

```bash
docker ps
```

Stop PostgreSQL:

```bash
docker compose down
```

---

# User Thread Database Setup

Create the user ownership table:

```sql
CREATE TABLE IF NOT EXISTS user_threads (
    user_id TEXT NOT NULL,
    thread_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_threads_user_id
ON user_threads(user_id);
```

Verify:

```sql
SELECT * FROM user_threads;
```

Initially the table may be empty.

New conversation threads are registered when users create/use conversations.

---

# Run the Application

Start the Streamlit application:

```bash
uv run streamlit run streamlit_frontend_stm.py
```

The application will normally be available at:

```text
http://localhost:8501
```

Users will first see the authentication page.

```text
Login
  |
  v
Continue with Google
  |
  v
Authenticated Chatbot
```

---

# Authentication Flow

The complete flow is:

```text
1. User opens application
        |
        v
2. Login page
        |
        v
3. Continue with Google
        |
        v
4. Google OAuth
        |
        v
5. Supabase authentication
        |
        v
6. Authenticated user
        |
        v
7. User-specific thread list
        |
        v
8. LangGraph chatbot
```

---

# Conversation Management

Each conversation receives a unique:

```text
thread_id
```

The application stores thread ownership using:

```text
user_threads
```

Example:

```text
Authenticated User
        |
        +-- Thread A
        |
        +-- Thread B
        |
        +-- Thread C
```

When the user returns to the application, their previous conversations can be displayed and restored.

---

# User Isolation

User isolation is implemented at the database level.

Example:

```text
User A
 |
 +-- thread_1
 +-- thread_2


User B
 |
 +-- thread_3
 +-- thread_4
```

When User A requests `thread_3`, the application checks:

```text
Does User A own thread_3?
```

If the ownership check fails, the conversation is not loaded.

This provides user-specific conversation isolation.

---

# Memory Persistence

The application maintains three types of persistent information:

```text
1. Conversation Checkpoints
2. Long-Term User Memories
3. User/Thread Ownership
```

They are associated with:

```text
thread_id
user_id
```

Conceptually:

```text
                    PostgreSQL
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
  STM Checkpoints   LTM Memories   user_threads
        |               |               |
   thread_id          user_id       user_id
```

---

# Development Commands

## Synchronize Dependencies

```bash
uv sync
```

## Update Lock File

After changing dependencies:

```bash
uv lock
```

## Compile Check

Run:

```bash
uv run python -m py_compile chatbot_stm.py streamlit_frontend_stm.py auth.py
```

## Run Streamlit

```bash
uv run streamlit run streamlit_frontend_stm.py
```

---

# Docker Deployment

For local development:

```text
Docker
 |
 +-- PostgreSQL
```

while Streamlit runs directly on the host.

For a fully containerized deployment, the Streamlit container should connect to PostgreSQL using the Docker service name.

For example:

```text
postgres:5432
```

rather than:

```text
localhost:5442
```

A persistent Docker volume should be used for PostgreSQL data in production.

---

# Railway Deployment

The application can be deployed to Railway.

Production architecture:

```text
                         Railway
                            |
             +--------------+--------------+
             |                             |
             v                             v
      Streamlit App                  PostgreSQL
             |
     +-------+-------+
     |       |       |
     v       v       v
  Gemini  Supabase  MCP
            Auth    Servers
```

The Streamlit application uses Railway's dynamic:

```text
$PORT
```

environment variable.

The deployment command is configured through:

```text
railway.toml
```

Example:

```toml
[deploy]
startCommand = "streamlit run streamlit_frontend_stm.py --server.address 0.0.0.0 --server.port $PORT"
```

---

# Railway Environment Variables

Configure the following variables in Railway:

```text
DATABASE_URL
GOOGLE_API_KEY
SUPABASE_URL
SUPABASE_ANON_KEY
APP_URL
DEPLOYMENT_ENV
```

Example:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}

DEPLOYMENT_ENV=railway
```

The Google Gemini API key and Supabase credentials should be stored as Railway variables and not committed to GitHub.

---

# Production Authentication

For production deployment, the application URL should be configured as the production `APP_URL`.

Example:

```text
https://your-production-domain
```

The same production URL must be configured appropriately in the authentication provider settings.

Local development can continue using:

```text
http://localhost:8501
```

---

# Security

Do not commit:

```text
.env
```

or any:

- API keys
- OAuth secrets
- Database passwords
- Access tokens
- Authentication credentials

Use environment variables or the deployment platform's secret-management system.

The PostgreSQL credentials included in the local Docker configuration are intended only for local development.

Production databases should use secure credentials.

Authentication should be performed using the authenticated user's identity.

Authorization should be validated server-side rather than relying only on frontend state.

---

# Git Workflow

After making changes:

```bash
git status
```

Add files:

```bash
git add .
```

Commit:

```bash
git commit -m "Update LangGraph chatbot"
```

Push:

```bash
git push origin main
```

Railway can then deploy the latest commit when automatic deployment is enabled.

---

# Current Application Capabilities

The application currently combines:

```text
Google Authentication
        |
        v
Supabase User Identity
        |
        v
User Authorization
        |
        v
User-Specific Conversations
        |
        v
LangGraph Agent
        |
   +----+----+----------------+
   |         |                |
   v         v                v
  STM       LTM             MCP
   |         |                |
   +---------+----------------+
             |
             v
        Google Gemini
             |
       +-----+-----+
       |           |
       v           v
      RAG       Web Search
       |
       v
      FAISS
```

---

# Future Improvements

- Production-grade session management
- Improved memory deduplication
- Memory editing and deletion
- Better RAG document management
- Multiple document collections
- Advanced retrieval and reranking
- Role-based authorization
- Admin dashboard
- Observability and tracing
- Automated testing
- Improved MCP management
- Containerized Streamlit deployment
- Production database optimization
- Conversation search
- File/document management
- Streaming responses
- Advanced agent planning

---

# Author

**Abhinay Makkena**

---

# License

This project is intended for educational and development purposes.