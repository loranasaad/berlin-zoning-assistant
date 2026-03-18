import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Makes the same config.py work locally and on share.streamlit.io
def _get_secret(key: str) -> str | None:
	try:
		return st.secrets[key]
	except Exception:
		return os.getenv(key)

# API Keys
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
VOYAGE_API_KEY    = _get_secret("VOYAGE_API_KEY")

# Language options
LANGUAGES = {
	"Deutsch": "de",
	"English": "en",
}

DEFAULT_LANGUAGE = "de"

# Models
MODEL_ID = "claude-sonnet-4-6"

EMBEDDING_MODEL = "voyage-law-2"


# ChromaDB
CHROMA_DB_PATH			= "./chroma_db"
CHROMA_COLLECTION_NAME	= "berlin_zoning"

# RAG settings
CHUNK_SIZE		= 2000
CHUNK_OVERLAP	= 200
TOP_K_RESULTS	= 6   # Number of chunks to retrieve per query

# Pricing (USD per 1K tokens) for cost tracker
TOKEN_COSTS = {
	"input":  0.003,
	"output": 0.015,
}

# Data paths
DOCS_PATH = "./data/docs"

# Input validation
MIN_INPUT_LENGTH = 3      # characters
MAX_INPUT_LENGTH = 2000   # characters
 
# Rate limiting
RATE_LIMITING_ENABLED    = True  # Set to False to disable during development
RATE_LIMIT_REQUESTS      = 5     # Max requests allowed within the window
RATE_LIMIT_WINDOW_SECONDS = 60   # Sliding window size in seconds
