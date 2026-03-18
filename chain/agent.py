import logging
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk, SystemMessage
from langgraph.prebuilt import create_react_agent

from rag.retriever import retrieve_and_format
from config import ANTHROPIC_API_KEY, MODEL_ID, TOKEN_COSTS
from chain.prompts import SYSTEM_PROMPTS, TOOLS

logger = logging.getLogger(__name__)

def run_agent(
		user_input: str,
		language: str = "de",
		chat_history: list[dict] = None,
		vector_store=None,
):
	"""
	Run the ReAct agent with streaming for the final answer.

	Returns:
		(stream_generator, get_result_fn)

		- stream_generator: yields final answer text chunks — pass directly to
		  st.write_stream(). Tool calls and token usage are collected as side
		  effects while the stream is consumed.
		- get_result_fn: call AFTER the stream is fully consumed to get
		  { answer, sources, tool_calls, token_usage }.
		  token_usage reflects ALL Claude calls: classifier + translation + agent.
	"""
	if chat_history is None:
		chat_history = []
	
	context, source_chunks, retriever_usage = retrieve_and_format(user_input, vector_store, language)
	messages = _build_messages(user_input, context, chat_history, language)

	llm = ChatAnthropic(
		model=MODEL_ID,
		anthropic_api_key=ANTHROPIC_API_KEY,
		temperature=0.2,
	)
	agent = create_react_agent(llm, TOOLS)
	
	tool_calls_map: dict[str, dict] = {}
	full_answer_parts: list[str] = []
	stream_error: list[str] = []
	agent_usage: dict = {"input_tokens": 0, "output_tokens": 0}

	def answer_stream():
		try:
			for chunk, _ in agent.stream(
				{"messages": messages},
				stream_mode="messages"
			):
				# Accumulate actual token counts across all ReAct loop iterations
				usage = getattr(chunk, "usage_metadata", None)
				if usage:
					agent_usage["input_tokens"]  += usage.get("input_tokens",  0)
					agent_usage["output_tokens"] += usage.get("output_tokens", 0)

				# Tool call request
				if isinstance(chunk, AIMessageChunk) and chunk.tool_calls:
					for tc in chunk.tool_calls:
						if tc.get("name"):
							tool_calls_map[tc["id"]] = {
								"tool":   tc["name"],
								"input":  tc["args"],
								"output": None,
							}
				# Tool result
				elif hasattr(chunk, "tool_call_id") and chunk.tool_call_id:
					tid = chunk.tool_call_id
					if tid in tool_calls_map:
						tool_calls_map[tid]["output"] = chunk.content

				# Final answer chunk — streamed text
				elif (
					isinstance(chunk, AIMessageChunk)
					and not getattr(chunk, "tool_calls", None)
				):
					text = _extract_text(chunk.content)
					if text:
						full_answer_parts.append(text)
						yield text
		except Exception as e:
			logger.error(f"Agent streaming error: {e}")
			error_msg = f"Ein Fehler ist aufgetreten: {str(e)}"
			stream_error.append(error_msg)
			yield error_msg
		
	def get_result() -> dict:
		full_answer = "".join(full_answer_parts) or (stream_error[0] if stream_error else "")
		tool_calls  = list(tool_calls_map.values())

		total_input  = retriever_usage["input_tokens"]  + agent_usage["input_tokens"]
		total_output = retriever_usage["output_tokens"] + agent_usage["output_tokens"]

		input_cost  = (total_input  / 1000) * TOKEN_COSTS["input"]
		output_cost = (total_output / 1000) * TOKEN_COSTS["output"]

		logger.info(
			f"Total tokens — input: {total_input} "
			f"(retriever: {retriever_usage['input_tokens']} + "
			f"agent: {agent_usage['input_tokens']}), "
			f"output: {total_output} "
			f"(retriever: {retriever_usage['output_tokens']} + "
			f"agent: {agent_usage['output_tokens']})"
		)

		token_usage = {
			"input_tokens":       total_input,
			"output_tokens":      total_output,
			"total_tokens":       total_input + total_output,
			"estimated_cost_usd": round(input_cost + output_cost, 5),
		}
		return {
			"answer":      full_answer,
			"sources":     source_chunks,
			"tool_calls":  tool_calls,
			"token_usage": token_usage,
		}

	return answer_stream(), get_result

# Handles Anthropic's streaming content format — plain string or list of blocks
def _extract_text(content) -> str:
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		return "".join(
			block.get("text", "") for block in content
			if isinstance(block, dict) and block.get("type") == "text"
		)
	return ""

def _build_messages(
		user_input: str,
		context: str,
		chat_history: list,
		language: str,
) -> list:
	"""Build the full messages list: system prompt + chat history + current user message."""
	system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["de"])
	system_with_context = system_prompt.replace("{context}", context)
	messages = [SystemMessage(content=system_with_context)]
	messages += _format_chat_history(chat_history)
	messages.append(HumanMessage(content=user_input))
	return messages

def _format_chat_history(history: list[dict]) -> list:
	"""Convert chat history dicts into LangChain message objects."""
	messages = []
	for msg in history:
		if msg["role"] == "user":
			messages.append(HumanMessage(content=msg["content"]))
		elif msg["role"] == "assistant":
			messages.append(AIMessage(content=msg["content"]))
	return messages
