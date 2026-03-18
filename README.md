# 🏗️ Berliner Bebauungsassistent

An AI agent that helps architects, engineers, and planners navigate Berlin's building codes, zoning regulations, and planning requirements. Enter any Berlin address to get a complete zoning report — zone type, buildable area, parking requirements, construction cost estimate, and district demographics — all grounded in official regulation text via RAG.

**[→ Live Demo](https://berlin-zoning-assistant-ahtnktgz7gympcspnrquct.streamlit.app)**  — password protected, available on request

---

## What it does

Type any Berlin address into the chat. The agent:

1. Geocodes the address and fetches live parcel data from GDI Berlin (ALKIS cadastre, B-Plan, FNP 2025)
2. Determines zone type (WA, MI, MK, GE, etc.) and official plot area
3. Calculates buildable area (GRZ/GFZ ratios per BauNVO §17–19), parking requirements (AV Stellplätze 2021), and construction cost estimates (BKI Baukosten 2024)
4. Retrieves relevant regulation excerpts from BauNVO and BauO Berlin via semantic search to ground its answers
5. Streams the response live — no waiting for the full answer to generate

For regulation questions without an address ("What are the setback rules in a MI zone?"), the agent answers directly from the knowledge base without calling any tools.

---

## Why this domain

Berlin's planning regulations are dense, multi-layered, and split across federal law (BauNVO), state law (BauO Berlin), and district-level Bebauungspläne. The same question — "what can I build here?" — requires cross-referencing live geodata, zone-specific parameters, and up-to-date regulation text simultaneously. That's exactly the kind of workflow AI agents are well suited to automate, and exactly the kind of problem that only makes sense to build if you already understand what architects actually need from a zoning lookup.

---

## Stack

| Layer | Technology |
|---|---|
| LLM | Claude Sonnet 4.6 (Anthropic) |
| Agent framework | LangGraph `create_react_agent` (ReAct loop) |
| Embeddings | Voyage AI `voyage-law-2` (legal domain model) |
| Vector store | ChromaDB |
| RAG | LangChain — chunking, retrieval, context injection |
| Geodata | GDI Berlin WFS API (B-Plan, FNP, ALKIS, Adressen) |
| UI | Streamlit with streaming output |

---

## Agent tools

| Tool | What it does |
|---|---|
| `get_full_zoning_report` | Master tool — geocodes address, fetches zone type and plot area from GDI Berlin, delegates to all calculation tools, returns a structured report |
| `calculate_buildable_area` | GRZ/GFZ-based footprint and floor area calculations (BauNVO §17–19) |
| `calculate_parking_requirements` | Mandatory bicycle spaces and accessible car spaces by use type (AV Stellplätze 2021, Anlage 1+2). Berlin abolished the general car parking minimum in 2021 (§49 BauO Bln) |
| `get_demographics` | District demographics from Amt für Statistik Berlin-Brandenburg (31.12.2024) |
| `estimate_construction_cost` | €/m² cost estimate by building type (BKI Baukosten 2024, Berlin market) |
| `get_construction_price_index` | Official quarterly construction price index (Destatis + Amt für Statistik, Nov 2025) |

---

## Knowledge base

| Document | Content |
|---|---|
| `baunvo.txt` | Baunutzungsverordnung — federal land use ordinance, zone types, GRZ/GFZ limits (July 2023) |
| `bao_berlin.txt` | Berliner Bauordnung — setbacks, heights, fire protection, structural requirements (post-7th amendment, Jan 2026) |
| `av_stellplaetze.pdf` | AV Stellplätze — mandatory bicycle parking ratios by use type (Anlage 2) and accessible car spaces (Anlage 1), valid until 30.06.2026 |

Construction cost data and district statistics are stored as structured Python dicts (`data/construction_cost_data.py`, `data/berlin_districts.py`) rather than RAG documents — tabular data chunks poorly for embedding-based retrieval.

English queries are automatically translated to German before embedding, since the knowledge base documents are in German. This reduces L2 retrieval distances significantly and improves chunk relevance.

---

## Data sources

**Geodata & cadastre:** GDI Berlin WFS API (B-Plan, FNP 2025), ALKIS, Adressen Berlin WFS, Nominatim / OpenStreetMap

**Regulations:** BauNVO (July 2023), BauO Bln (January 2026), AV Stellplätze (16.06.2021, ABl. S. 2326)

**Statistics:** Amt für Statistik Berlin-Brandenburg (Einwohnerregisterstatistik 31.12.2024, Baupreisindex Januar 2026), Destatis (09.01.2026), BKI Baukosten Gebäude 2024, IBB Wohnungsmarktbericht 2023

---

## Setup

### Prerequisites

Python 3.11.15 is recommended — Python 3.12+ breaks some dependencies.

```bash
pyenv install 3.11.15
pyenv local 3.11.15
```

### Install

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### API keys

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
VOYAGE_API_KEY=pa-...
APP_PASSWORD=your-password
```

Voyage AI offers a free tier (50M tokens/month) at [dash.voyageai.com](https://dash.voyageai.com).

### Knowledge base documents

Add the following to `data/docs/`:

- `baunvo.txt` — Baunutzungsverordnung (July 2023)
- `bao_berlin.txt` — Berliner Bauordnung (post-7th amendment, January 2026)
- `av_stellplaetze.pdf` — AV Stellplätze (16.06.2021, ABl. S. 2326)

### Run

```bash
python -m streamlit run app.py
```

On first run the app builds the ChromaDB vector store from the documents in `data/docs/`. This takes ~30 seconds and only happens once — subsequent runs load it from disk instantly.

> **Rebuilding the vector store:** delete `chroma_db/` and restart. Required if you change the embedding model or add new documents.

---

## Deploying to Streamlit Cloud

The app is ready for [share.streamlit.io](https://share.streamlit.io). Add your API keys under **Settings → Secrets**:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
VOYAGE_API_KEY = "pa-..."
APP_PASSWORD = "your-password"
```

Note: Streamlit Cloud has an ephemeral filesystem. The vector store is rebuilt on each cold start (~30 seconds on first query per session).

---

## Project structure

```
berlin-zoning-assistant/
├── app.py                        # Streamlit entry point
├── config.py                     # API keys, model, RAG settings
├── requirements.txt
│
├── data/
│   ├── docs/                     # Knowledge base documents (RAG source files)
│   ├── berlin_districts.py       # District demographics (static reference data)
│   ├── construction_cost_data.py # BKI cost ranges and official price index data
│   └── zoning_rules.py           # Zone parameters, setback rules, parking ratios
│
├── rag/
│   ├── loader.py                 # Document loading and chunking
│   ├── embeddings.py             # ChromaDB vector store (build / load)
│   └── retriever.py              # Similarity search, query translation, context formatting
│
├── tools/
│   ├── zoning_report.py          # get_full_zoning_report (main address tool)
│   ├── buildable_area.py         # calculate_buildable_area
│   ├── parking.py                # calculate_parking_requirements
│   ├── demographics.py           # get_demographics
│   ├── fisbroker.py              # GDI Berlin WFS API calls (B-Plan, FNP, ALKIS)
│   └── construction_cost.py      # estimate_construction_cost, get_construction_price_index
│
├── chain/
│   ├── agent.py                  # LangGraph ReAct agent, streaming, message building
│   └── prompts.py                # System prompts (DE + EN) and tool list
│
├── ui/
│   ├── sidebar.py                # Language selector, cost tracker, clear chat
│   ├── chat.py                   # Input handling, streaming output, history
│   ├── components.py             # Expander, tabs, RAG process visualisation, debug view
│   ├── cards.py                  # Report cards (map, buildable area, parking, cost, demographics)
│   ├── rate_limiter.py           # Sliding window rate limiter (5 req / 60s)
│   └── strings.py                # All UI strings in DE and EN
│
└── chroma_db/                    # Vector store (auto-generated, not committed)
```

---

⚠️ For informational purposes only. Always verify planning decisions with the relevant Berlin authorities (Bauaufsichtsbehörde, Stadtplanungsamt).