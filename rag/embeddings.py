import logging
from pathlib import Path
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from rag.loader import load_and_split
from config import (
	OPENAI_API_KEY,
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
	# Check if vector store already exists and has data
	if chroma_path.exists() and any(chroma_path.iterdir()):
		logger.info("Vector store found on disk → loading...")
		return load_vector_store()
	else:
		logger.info("No vector store found → building from documents...")
		return build_vector_store()
	
def load_vector_store() -> Chroma:
	"""
	Load an existing ChromaDB vector store from disk.
	"""
	logger.info(f"Loading existing vector store from {CHROMA_DB_PATH}")
	embeddings = OpenAIEmbeddings(
		model=EMBEDDING_MODEL,
		openai_api_key=OPENAI_API_KEY
	)

	vector_store = Chroma(
		collection_name=CHROMA_COLLECTION_NAME,
		embedding_function=embeddings,
		persist_directory=CHROMA_DB_PATH
	)
	return vector_store

def build_vector_store(docs_path: str = None) -> Chroma:
	"""
	Build the ChromaDB vector store from scratch.
	Loads documents, splits them, embeds and persists to disk.
	"""
	logger.info("Building vector store from documents...")

	chunks = load_and_split(docs_path) if docs_path else load_and_split()
	embeddings = OpenAIEmbeddings(
		model=EMBEDDING_MODEL,
		openai_api_key=OPENAI_API_KEY
	)
	vector_store = Chroma.from_documents(
		documents=chunks,
		embedding=embeddings,
		collection_name=CHROMA_COLLECTION_NAME,
		persist_directory=CHROMA_DB_PATH,
	)

	logger.info(f"Vector store built with {len(chunks)} chunks → saved to {CHROMA_DB_PATH}")
	return vector_store
