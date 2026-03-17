# 🏗️ Berlin Building & Zoning Assistant

An AI-powered chatbot that helps architects, engineers, and developers navigate Berlin's building codes, zoning regulations, and planning requirements. Enter any Berlin address to get a full zoning report — including buildable area, parking requirements, construction cost estimates, and district demographics — grounded in official regulation text.

## Features

- **Address lookup** — geocodes any Berlin address and fetches live parcel data from GDI Berlin (ALKIS, B-Plan, FNP 2025)
- **Interactive map** — Folium map with parcel marker and full cadastral data panel
- **Zoning report** — zone type, GRZ/GFZ ratios, max floors, setback rules, special requirements
- **Calculations** — buildable area, mandatory bike parking & accessible car spaces (AV Stellplätze 2021), construction cost estimate
- **Construction price index** — official quarterly YoY data from Amt für Statistik Berlin-Brandenburg and Destatis (Nov 2025)
- **Demographics** — population, avg age, rent, apartment size per district (Amt für Statistik, 31.12.2024)
- **RAG** — answers grounded in BauNVO (July 2023), BauO Berlin (post-7th amendment, Jan 2026), and AV Stellplätze (June 2021)
- **Multi-model** — switch between GPT-4.1 mini and Claude Sonnet 4.6
- **Bilingual** — full English and German UI and responses
- **Cost tracker** — token usage and estimated cost per session

## Setup

1. **Ensure you are using Python 3.11.15** — Python 3.12+ breaks some dependencies:
   ```bash
   python --version   # should show Python 3.11.15
   ```
   If you use pyenv:
   ```bash
   pyenv install 3.11.15
   pyenv local 3.11.15   # creates a .python-version file in the project root
   ```

2. **Clone the repo and create a virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Set up your API keys** — create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

4. **Add knowledge base documents** to `data/docs/`:
   - `baunvo.txt` — Baunutzungsverordnung (federal land use regulation, July 2023)
   - `bao_berlin.txt` — Berliner Bauordnung (post-7th amendment, January 2026)
   - `av_stellplaetze.pdf` — AV Stellplätze (16.06.2021, ABl. S. 2326) — mandatory bicycle parking and accessible car space requirements per §49 BauO Bln (valid until 30.06.2026)

5. **Run the app:**
   ```bash
   python -m streamlit run app.py
   ```

   > **Why `python -m streamlit`?** On Mac, a globally installed streamlit may shadow the venv one even when the venv is active. Using `python -m streamlit` forces the venv's Python to find and run its own streamlit, avoiding the conflict.

On first run the app builds the ChromaDB vector store from the documents in `data/docs/`. This takes ~30 seconds and only happens once. Subsequent runs load it instantly from disk.

> **Rebuilding the vector store:** delete the `chroma_db/` folder and restart the app.

## Project Structure

```
berlin-zoning-assistant/
├── app.py                        # Streamlit entry point
├── config.py                     # API keys, model names, RAG settings
├── requirements.txt
├── .env                          # API keys (never committed)
├── .gitignore
│
├── data/
│   ├── docs/                     # Knowledge base documents (RAG source files)
│   ├── berlin_districts.py       # Static district demographics data
│   ├── construction_cost_data.py # BKI cost ranges + official price index data
│   └── zoning_rules.py           # Zone→building type mappings, setback rules, parking ratios
│
├── rag/
│   ├── loader.py                 # Document loading and chunking
│   ├── embeddings.py             # ChromaDB vector store (build / load)
│   └── retriever.py              # Similarity search + context formatting
│
├── tools/                        # LangChain tool functions (called by the agent)
│   ├── zoning_report.py          # get_full_zoning_report (main address tool)
│   ├── buildable_area.py         # calculate_buildable_area
│   ├── parking.py                # calculate_parking_requirements
│   ├── demographics.py           # get_demographics
│   ├── fisbroker.py              # GDI Berlin WFS API calls (B-Plan, FNP, ALKIS)
│   └── construction_cost.py      # estimate_construction_cost, get_construction_price_index
│
├── chain/
│   ├── agent.py                  # LangGraph ReAct agent, LLM setup, message building
│   └── prompts.py                # System prompts (EN + DE) and TOOLS list
│
├── ui/
│   ├── sidebar.py                # Settings, cost tracker, clear chat
│   ├── chat.py                   # Chat input handling and history rendering
│   ├── components.py             # Expander, tabs, RAG process, sources, debug view
│   ├── cards.py                  # Report cards (map, buildable area, parking, cost, demographics)
│   ├── rate_limiter.py           # Sliding window rate limiter
│   └── strings.py                # All UI strings in EN and DE
│
├── eval/
│   ├── questions.py              # RAGAs test dataset (15 questions, document-based ground truths)
│   ├── run_eval.py               # RAGAs evaluation runner (faithfulness, relevancy, precision, recall)
│   ├── tool_questions.py         # Tool calling test dataset (15 cases, 4 difficulty levels)
│   ├── run_tool_eval.py          # Tool calling evaluation runner (deterministic + LLM judge)
│   ├── results.json              # Latest RAGAs results (auto-generated)
│   └── tool_results.json         # Latest tool calling results (auto-generated)
│
└── chroma_db/                    # Vector store (auto-generated on first run, not committed)
```

## Tools

| Tool | Description |
|------|-------------|
| `get_full_zoning_report` | Main address tool — geocodes, fetches zone type and plot area from GDI Berlin, then delegates to all calculation tools |
| `calculate_buildable_area` | GRZ/GFZ-based footprint and floor area calculations (BauNVO §17–19) |
| `calculate_parking_requirements` | Mandatory bicycle spaces and accessible car spaces by use type (AV Stellplätze 16.06.2021, Anlage 1 + 2). Note: Berlin abolished the general car parking minimum (Stellplatzpflicht) in 2021 (§49 BauO Bln). |
| `get_demographics` | District demographics from Amt für Statistik Berlin-Brandenburg |
| `estimate_construction_cost` | €/m² cost estimate by building type (BKI Baukosten 2024, Berlin market) |
| `get_construction_price_index` | Official quarterly construction price index data (Destatis + Amt für Statistik, Nov 2025) |

## Knowledge Base

| File | Content |
|------|---------|
| `baunvo.txt` | Baunutzungsverordnung — federal land use ordinance governing zone types, GRZ/GFZ limits, permitted uses (last amended July 2023) |
| `bao_berlin.txt` | Berliner Bauordnung — Berlin state building code covering setbacks, heights, structural requirements, fire protection (post-7th amendment, January 2026) |
| `av_stellplaetze.pdf` | AV Stellplätze — executive regulation implementing §49 BauO Bln: mandatory bicycle parking ratios by use type (Anlage 2) and accessible car spaces for disabled users (Anlage 1). Published 16.06.2021, valid until 30.06.2026. |

> Construction cost data and district statistics are embedded directly as structured Python dicts (`data/construction_cost_data.py`, `data/berlin_districts.py`) rather than RAG documents, as tabular data chunks poorly for retrieval.

## Data Sources

**Geodata & cadastre**
- GDI Berlin WFS API — Bebauungsplan (B-Plan), Flächennutzungsplan 2025 (FNP)
- ALKIS (Amtliches Liegenschaftskatasterinformationssystem) — official parcel boundaries and attributes
- Adressen Berlin WFS (GDI Berlin) — official Hauskoordinaten for plot-level geocoding
- Nominatim / OpenStreetMap — initial address geocoding and display_name parsing

**Regulations**
- BauNVO (Baunutzungsverordnung, July 2023) — federal land use ordinance
- BauO Bln (Berliner Bauordnung, post-7th amendment, January 2026) — Berlin state building code
- AV Stellplätze (16.06.2021, ABl. S. 2326) — mandatory bicycle and accessible car space requirements per §49 BauO Bln (valid until 30.06.2026)

**Statistics**
- Amt für Statistik Berlin-Brandenburg — Einwohnerregisterstatistik (31.12.2024), Baupreisindex M I 4 – vj (Januar 2026)
- Statistisches Bundesamt (Destatis) — national construction price index (Pressemitteilung 09.01.2026)
- BKI Baukosten Gebäude 2024 — construction cost reference values
- IBB Wohnungsmarktbericht 2023 — Berlin rental market data

---

## Running the Evaluation

The `eval/` folder contains two independent evaluation pipelines. Both are run from the project root.

### Check your versions first

Before running, verify the exact versions installed in your environment:
```bash
pip show langgraph ragas
```

This tells you the installed version so you can pin them in `requirements.txt` if needed.

### RAG Evaluation (RAGAs)

Evaluates retrieval quality and answer faithfulness across 15 test questions.

```bash
# Full evaluation — all 15 questions (makes LLM API calls, ~$0.05)
python -m eval.run_eval

# Filter to one category only
python -m eval.run_eval --category REGULATION
python -m eval.run_eval --category HALLUCINATION_TRAP
python -m eval.run_eval --category CALCULATION

# Dry run — retrieval only, no agent or RAGAs calls (free, fast)
python -m eval.run_eval --dry-run

# Use a specific model
python -m eval.run_eval --model "Claude Sonnet 4.6 (Anthropic)"
```

Results are saved to `eval/results.json` and printed to stdout.

### Tool Calling Evaluation

Evaluates whether the agent calls the right tools with the right parameters across 15 test cases at four difficulty levels.

```bash
# Full evaluation — deterministic checks + LLM judge
python -m eval.run_tool_eval

# Deterministic only — no LLM judge (free, instant)
python -m eval.run_tool_eval --no-judge

# Filter by difficulty level
python -m eval.run_tool_eval --difficulty EASY
python -m eval.run_tool_eval --difficulty MEDIUM
python -m eval.run_tool_eval --difficulty HARD
python -m eval.run_tool_eval --difficulty EDGE_CASE
```

Results are saved to `eval/tool_results.json` and printed to stdout.

---

## Course Requirements

### Core Requirements ✅

| Requirement | Implementation |
|-------------|----------------|
| **RAG with embeddings, chunking, similarity search** | ChromaDB vector store built from BauNVO, BauO Berlin, and AV Stellplätze source documents. Documents are split with `RecursiveCharacterTextSplitter` (chunk size 2000, overlap 200) and embedded with `text-embedding-3-small`. Retrieval uses L2 similarity search returning the top 4 chunks, which are injected into the agent's system prompt as context. English queries are translated to German before embedding to improve retrieval quality against the German-language knowledge base. |
| **At least 3 tool calls** | 6 tools implemented: `get_full_zoning_report`, `calculate_buildable_area`, `calculate_parking_requirements`, `get_demographics`, `estimate_construction_cost`, `get_construction_price_index`. |
| **Domain-specific prompts** | Separate system prompts in English and German with explicit tool usage rules, field naming conventions, and domain-specific instructions (e.g. how to interpret GRZ/GFZ, which parking use_type values are valid, why no general car minimum exists). |
| **LangChain + LangGraph** | LangGraph `create_react_agent` drives the tool-calling loop. LangChain tool decorators, message types, and LLM wrappers used throughout. |
| **Error handling** | Structured error returns from all tools (with `error_code` and `error_params` for localised display). Try/except blocks in the agent, geocoder, and all WFS API calls. |
| **Logging** | Python `logging` module used throughout all layers (`fisbroker.py`, `retriever.py`, `embeddings.py`, `agent.py`). Configured in `app.py` with timestamp and level formatting. |
| **User input validation** | Input is checked for minimum length (3 chars) and maximum length (2000 chars) before being passed to the agent. Validation errors are shown inline in the chat in the selected language. |
| **Rate limiting** | Sliding window rate limiter (`ui/rate_limiter.py`) — max 5 requests per 60 seconds per session. Can be disabled via `RATE_LIMITING_ENABLED = False` in `config.py` for development. Wait time shown to the user is calculated from the oldest request in the window, not a fixed cooldown. |
| **API key management** | All keys loaded from `.env` via `python-dotenv`. Never hardcoded. Separate keys for OpenAI and Anthropic. |
| **Streamlit UI** | Full Streamlit app with sidebar settings, chat interface, expander panels, tabs, maps, and metric cards. |
| **Show sources** | Every assistant response includes a Sources tab showing the retrieved RAG chunks with source file name and page number. |
| **Display tool call results** | Debug tab shows raw tool inputs and outputs for every tool called in a response. |
| **Progress indicators** | `st.spinner` shown while the agent is running. |

### Optional Tasks

#### Easy
| Task | Status | Implementation |
|------|--------|----------------|
| Conversation history | ✅ | Full chat history stored in `st.session_state` and replayed on every Streamlit rerun. Passed to the agent as prior context so it can answer follow-up questions. |
| Source citations | ✅ | Sources tab in the analysis expander shows each retrieved chunk in a collapsible expander with the full text, source document name, and page number. |

#### Medium
| Task | Status | Implementation |
|------|--------|----------------|
| Multi-model support | ✅ | GPT-4.1 mini (OpenAI) and Claude Sonnet 4.6 (Anthropic) selectable from the sidebar. `agent.py` detects the provider from the model ID string and instantiates the correct LangChain LLM class. |
| Token usage and cost display | ✅ | Session cost tracker in the sidebar shows cumulative input tokens, output tokens, and estimated USD cost. Per-message token counts estimated from character length (÷4). Pricing per model defined in `config.py`. |
| Visualisation of tool call results | ✅ | Address lookup responses render four structured cards: buildable area metrics, parking card showing mandatory bike spaces (AV Stellplätze 2021) and accessible car spaces with step-by-step calculation, construction cost min/avg/max, and district demographics. |
| Visualisation of RAG process | ✅ | Dedicated "🔍 RAG Process" tab shows the full retrieval pipeline: embedding model used → each retrieved chunk with a colour-coded L2 distance bar (green < 0.8, amber < 1.2, red ≥ 1.2) → total context size in characters and estimated tokens injected into the prompt. |

#### Hard
| Task | Status | Implementation |
|------|--------|----------------|
| Multi-language support | ✅ | Full English and German support throughout: UI labels, system prompts, tool error messages, and agent responses. All strings centralised in `ui/strings.py`. Language switchable at runtime from the sidebar without restarting the app. |
| RAG evaluation (RAGAs) | ✅ | Full evaluation pipeline in `eval/` using RAGAs. Evaluates faithfulness, answer relevancy, context precision, and context recall across 15 test questions split into three categories (REGULATION, HALLUCINATION_TRAP, CALCULATION). Ground truths derived directly from BauNVO and BauO Berlin source documents. Judge uses GPT-4o-mini at temperature=0 for deterministic results. Final REGULATION scores: faithfulness 0.822, context precision 0.967, context recall 0.975. Results saved to `eval/results.json` with per-category breakdown. |
| Tool calling evaluation | ✅ | Deterministic tool selection and parameter accuracy checks across 15 cases at four difficulty levels (EASY/MEDIUM/HARD/EDGE_CASE), combined with LLM-as-judge via RAGAs `DiscreteMetric`. Results saved to `eval/tool_results.json`. Final results: 100% tool selection accuracy, 93.3% parameter accuracy, 100% LLM judge accuracy. |

---

## Evaluation Results

### RAG Evaluation (RAGAs)

Evaluated with RAGAs using GPT-4o-mini at `temperature=0` as the judge for deterministic results. 15 test questions split into three categories. Ground truths derived directly from the BauNVO and BauO Berlin source documents.

**Final scores (chunk size 2000, overlap 200):**

| Metric | REGULATION (n=10) | HALLUCINATION_TRAP (n=3) | CALCULATION (n=2) | Overall |
|--------|-------------------|--------------------------|-------------------|---------|
| Faithfulness | 0.822 ✅ | 0.328 | 0.333 | 0.658 |
| Answer relevancy | 0.941 ✅ | 0.0 | 0.972 ✅ | 0.757 |
| Context precision | 0.967 ✅ | — | — | 0.967 ✅ |
| Context recall | 0.975 ✅ | — | — | 0.975 ✅ |

**Interpretation notes:**

- **REGULATION** is the primary signal — these questions have document-based ground truths and test the core RAG pipeline directly. Scores of 0.73–0.88 indicate reliable retrieval and grounded generation.
- **HALLUCINATION_TRAP answer relevancy = 0.0** is expected and correct behaviour. The model correctly says "this information is not in my knowledge base" for questions about energy efficiency requirements and permit fees (topics not covered in BauNVO or BauO Berlin). RAGAs interprets a hedged "I don't know" answer as irrelevant, creating an inherent tension between faithfulness and answer relevancy for out-of-scope questions.
- **CALCULATION faithfulness** is always near 0 — a known measurement artefact. These answers come from tool results (e.g. `calculate_parking_requirements`), not from the retrieved context chunks. RAGAs finds no overlap between the numerical tool output and the legal text chunks, scoring it as unfaithful even though the answer is correct. This is not a hallucination problem.
- **Faithfulness on REGULATION** is moderate (0.73) partly due to the "strong model" problem described in the RAGAs documentation: the model adds true, helpful explanations that go beyond what is literally in the retrieved chunks. This lowers the faithfulness score even when the answer is accurate and useful.

**Key improvements made during evaluation:**
- Chunk size increased from 1000/150 to 2000/200: faithfulness on REGULATION improved from 0.66 to 0.82, context precision from 0.91 to 0.97 — larger chunks keep complete legal paragraphs together, producing better embeddings
- Query translation: English queries are translated to German before embedding, reducing L2 retrieval distances by ~0.3–0.5 across all questions
- Hallucination guard added to system prompts: model now explicitly declines to answer questions outside the knowledge base
- Ground truths rewritten from actual document text (not general knowledge) to make context recall a meaningful signal
- RAGAs judge uses GPT-4o-mini at temperature=0 for deterministic, reproducible results

### Tool Calling Evaluation

Deterministic evaluation across 15 cases at four difficulty levels, combined with LLM-as-judge via RAGAs `DiscreteMetric`.

| Difficulty | N | Tool selection | Params | LLM judge |
|------------|---|----------------|--------|-----------|
| EASY | 4 | 100% | 75% | 100% |
| MEDIUM | 4 | 100% | 100% | 100% |
| HARD | 4 | 100% | 100% | 100% |
| EDGE_CASE | 3 | 100% | 100% | 100% |
| **OVERALL** | **15** | **100%** | **93.3%** | **100%** |

Tool selection is perfect across all difficulty levels and edge cases. The one parameter accuracy miss (EASY, 93.3%) is a test design issue: the agent passes `"Prenzlauer Berg, Berlin"` to `get_demographics` instead of `"Prenzlauer Berg"` — both work correctly. The LLM judge correctly rates this as correct.

---

⚠️ For informational purposes only. Always verify with the relevant Berlin authorities (Bauaufsichtsbehörde, Stadtplanungsamt) before making planning or investment decisions.