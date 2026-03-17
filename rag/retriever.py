import logging
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI  # ✅ ADDED
from rag.embeddings import get_or_create_vector_store
from config import TOP_K_RESULTS, OPENAI_API_KEY  # ✅ ADDED OPENAI_API_KEY
from ui.strings import RETRIEVER_STRINGS

logger = logging.getLogger(__name__)

# Translate English queries to German before embedding
def _translate_to_german(query: str) -> str:
	"""
	Translate an English query to German before embedding.

	The knowledge base documents are in German, so translating the query
	improves retrieval quality for English-language users — German-to-German
	matching produces significantly lower L2 distances than English-to-German.

	Uses a minimal GPT-4.1-mini call with temperature=0.
	Falls back to the original query if translation fails so it never breaks the app.
	"""
	try:
		llm = ChatOpenAI(
			model="gpt-4.1-mini",
			openai_api_key=OPENAI_API_KEY,
			temperature=0,
			max_tokens=200,
		)
		response = llm.invoke(
			f"Translate the following query into German legal and regulatory language, "
			f"as it would appear in a German building code or zoning ordinance. "
			f"Use formal legal phrasing (e.g. 'gelten', 'sind einzuhalten', 'vorgeschrieben'). "
			f"Return only the translated text, nothing else.\n\n{query}"
		)
		translated = response.content.strip()
		logger.info(f"Query translated for retrieval: '{query[:60]}' → '{translated[:60]}'")
		return translated
	except Exception as e:
		logger.warning(f"Query translation failed, using original: {e}")
		return query

def retrieve_and_format(query: str, vector_store: Chroma = None, language: str = "en") -> tuple[str, list[Document]]:
	"""Retrieve chunks and return both the formatted context string and raw chunks."""
	retrieval_query = _translate_to_german(query) if language == "en" else query
	chunks = retrieve_relevant_chunks(retrieval_query, vector_store)
	context = format_retrieved_context(chunks, language)
	return context, chunks

def retrieve_relevant_chunks(query: str, vector_store: Chroma = None) -> list[Document]:
	"""Retrieve the top-k most relevant chunks for a query."""
	if vector_store is None:
		vector_store = get_or_create_vector_store()
	
	logger.info(f"Retrieving chunks for query: '{query[:80]}'")
	results = vector_store.similarity_search_with_score(query, k=TOP_K_RESULTS)
	chunks = []
	for doc, score in results:
		doc.metadata["retrieval_score"] = round(float(score), 4)
		chunks.append(doc)
	logger.info(f"Retrieved {len(chunks)} chunks")
	return chunks

def format_retrieved_context(chunks: list[Document], language: str = "en") -> str:
	"""Format retrieved chunks into a single context string for the LLM prompt."""
	s = RETRIEVER_STRINGS.get(language, RETRIEVER_STRINGS["en"])
	
	if not chunks:
		return s["no_results"]

	context_parts = []
	for i, chunk in enumerate(chunks, 1):
		source = chunk.metadata.get("source", s["unknown_src"])
		page = chunk.metadata.get("page", "")
		page_info = f", {s['page_label']} {page + 1}" if page != "" else ""
		context_parts.append(
			f"[{s['source_label']} {i}: {source}{page_info}]\n{chunk.page_content}"
		)
	
	return "\n\n---\n\n".join(context_parts)
