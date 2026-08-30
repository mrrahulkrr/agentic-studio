# Walkthrough: In-App Assistants (Client & Developer)

The two new in-app assistants (`client` and `developer`) have been successfully implemented following the approved plan. Here's a breakdown of the new architecture and features.

## 1. Knowledge Base Consolidation
To solve the issue of a distributed and bifurcated knowledge base, all documentation has been centralized:
- **`docs/client/`**: Contains the client-facing UI copy extracted into clean Markdown files (`tasks.md`, `planner.md`, `panels.md`).
- **`docs/developer/`**: Contains the consolidated developer documentation (`ARCHITECTURE.md`, `PROJECT_GUIDE.md`, `CLAUDE.md`, etc.).

## 2. Code-Aware Ingestion Pipeline
We implemented [ingest_docs.py](file:///d:/agentic-studio/backend/ingest_docs.py) which crawls the new `docs/` structure and the codebase to feed the RAG system:
- **Batch Embedding**: Modified `llm.py` to support `embed_batch`, allowing the pipeline to process 100 chunks per API call, significantly improving ingestion speed and avoiding rate limits.
- **Structural Chunking**: Instead of relying on word-count (which destroys functions), code files (`.py`, `.ts`, `.tsx`) are now chunked dynamically by blocks of lines with overlaps, preserving context.

## 3. Tuned Hybrid Search & API Endpoints
We added two new endpoints to [main.py](file:///d:/agentic-studio/backend/app/main.py):
- `POST /assist/client`: Queries the `client_help` collection for studio operation questions.
- `POST /assist/developer`: Queries both `dev_docs` and `dev_code`, gated by the developer role.
> [!TIP]
> The hybrid search weights in `retrieval.py` have been specially tuned for code. Code searches lean 80% on Dense vector matching and 20% on BM25 lexical matching to combat poor tokenization of code syntax.

## 4. Ask AI Interface
A new "Ask AI" button has been added to the main Navbar in both the client and admin apps. Clicking it opens the [HelpChat.tsx](file:///d:/agentic-studio/frontend/src/components/HelpChat.tsx) modal.
- The modal features a clean, centered command-palette layout mimicking the GetStream documentation design, but styled precisely to match the studio's dark theme.
- The UI automatically parses backend citations (e.g., `[backend/app/main.py:L150]`) and renders them as styled clickable badges.

## 5. Automated CI/CD
A new GitHub Actions workflow ([ingest_docs.yml](file:///.github/workflows/ingest_docs.yml)) has been configured. It runs strictly on `ubuntu-latest` and guarantees that the knowledge base remains 100% in sync with the codebase by running `ingest_docs.py` whenever documentation or code is pushed to the `main` branch.
