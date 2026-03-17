import os
from dotenv import load_dotenv

load_dotenv()

# API Keys (loaded from .env, never hardcoded)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")

# Language options
LANGUAGES = {
    "English": "en",
    "Deutsch": "de",
}

# Model options
MODELS = {
    "GPT-4.1 mini (OpenAI)": "gpt-4.1-mini",
	"Claude Sonnet 4.6 (Anthropic)":  "claude-sonnet-4-6",
}

# Default model
DEFAULT_MODEL = "GPT-4.1 mini (OpenAI)"

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"

# ChromaDB
CHROMA_DB_PATH = "./chroma_db"
CHROMA_COLLECTION_NAME = "berlin_zoning"

# RAG settings
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200
TOP_K_RESULTS = 6   # Number of chunks to retrieve per query

# Pricing (USD per 1K tokens) for cost tracker
TOKEN_COSTS = {
    "gpt-4.1-mini": {"input": 0.0004, "output": 0.0016},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
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
