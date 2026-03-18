import logging
from pathlib import Path
from langchain_chroma import Chroma
from langchain_voyageai import VoyageAIEmbeddings
from rag.loader import load_and_split
from config import (
	VOYAGE_API_KEY,
	EMBEDDING_MODEL,
	CHROMA_DB_PATH,
	CHROMA_COLLECTION_NAME,
)

logger = logging.getLogger(__name__)

def get_or_create_vector_store() -> Chroma:
	"""
	If ChromaDB already exists on disk, load it
	If not, build it from documents
	"""
	chroma_path = Path(CHROMA_DB_PATH)
	if chroma_path.exists() and any(chroma_path.iterdir()):
		logger.info("Vector store found on disk → loading...")
		return _load_vector_store()
	else:
		logger.info("No vector store found → building from documents...")
		return _build_vector_store()
	
def _load_vector_store() -> Chroma:
	"""
	Load an existing ChromaDB vector store from disk.
	"""
	logger.info(f"Loading existing vector store from {CHROMA_DB_PATH}")
	return Chroma(
		collection_name=CHROMA_COLLECTION_NAME,
		embedding_function=_get_embeddings(),
		persist_directory=CHROMA_DB_PATH,
	)

def _build_vector_store(docs_path: str = None) -> Chroma:
	"""
	Build the ChromaDB vector store from scratch.
	Loads documents, splits them, embeds and persists to disk.
	"""
	logger.info("Building vector store from documents...")
	chunks = load_and_split(docs_path) if docs_path else load_and_split()
	vector_store = Chroma.from_documents(
		documents=chunks,
		embedding=_get_embeddings(),
		collection_name=CHROMA_COLLECTION_NAME,
		persist_directory=CHROMA_DB_PATH,
	)
	logger.info(f"Vector store built with {len(chunks)} chunks → saved to {CHROMA_DB_PATH}")
	return vector_store

# Helper to avoid repeating embedding instantiation in load and build
def _get_embeddings() -> VoyageAIEmbeddings:
	return VoyageAIEmbeddings(
		voyage_api_key=VOYAGE_API_KEY,
		model=EMBEDDING_MODEL,       # "voyage-law-2" — set in config.py
	)