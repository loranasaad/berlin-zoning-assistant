import logging
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from rag.retriever import retrieve_and_format
from config import OPENAI_API_KEY, ANTHROPIC_API_KEY, MODELS, TOKEN_COSTS
from chain.prompts import SYSTEM_PROMPTS, TOOLS

logger = logging.getLogger(__name__)

def run_agent(
		user_input: str,
		model_name: str,
		language: str = "en",
		chat_history: list[dict] = None,
		vector_store=None,
) -> dict:
	if chat_history is None:
		chat_history = []
	
	context, source_chunks = retrieve_and_format(user_input, vector_store, language)
	messages = _build_messages(user_input, context, chat_history, language)

	llm = get_llm(model_name)
	agent = create_react_agent(llm, TOOLS)

	try:
		result = agent.invoke({"messages": messages})
	except Exception as e:
		logger.error(f"Agent error: {e}")
		return {
			"answer": f"An error occurred: {str(e)}",
			"sources": [],
			"tool_calls": [],
			"token_usage": None,
		}
	
	answer, tool_calls = _parse_agent_result(result)

	token_usage = estimate_token_usage(
		messages=messages,
		answer=answer,
		model_name=MODELS.get(model_name, ""),
	)

	return {
		"answer": answer,
		"sources": source_chunks,
		"tool_calls": tool_calls,
		"token_usage": token_usage,
	}

def _build_messages(
		user_input: str,
		context: str,
		chat_history: list,
		language: str,
) -> list:
	"""Build the full messages list: system prompt + chat history + current user message."""
	system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS["en"])
	system_with_context = system_prompt.replace("{context}", context)
	messages = [SystemMessage(content=system_with_context)]
	messages += format_chat_history(chat_history)
	messages.append(HumanMessage(content=user_input))
	return messages

def get_llm(model_name: str):
	"""Return the correct LLM instance based on the model name."""
	model_id = MODELS.get(model_name)
	if not model_id:
		raise ValueError(f"Unknown model: {model_name}")
	if "gpt" in model_id:
		return ChatOpenAI(
			model=model_id,
			openai_api_key=OPENAI_API_KEY,
			temperature=0.2,
		)
	elif "claude" in model_id:
		return ChatAnthropic(
			model=model_id,
			anthropic_api_key=ANTHROPIC_API_KEY,
			temperature=0.2,
		)
	else:
		raise ValueError(f"No matching provider for model: {model_id}")

def format_chat_history(history: list[dict]) -> list:
	"""Convert chat history dicts into LangChain message objects."""
	messages = []
	for msg in history:
		if msg["role"] == "user":
			messages.append(HumanMessage(content=msg["content"]))
		elif msg["role"] == "assistant":
			messages.append(AIMessage(content=msg["content"]))
	return messages

def _parse_agent_result(result: dict) -> tuple[str, list]:
	"""Extract the final answer and tool calls from the agent's raw message list."""
	answer = ""
	tool_calls = []

	for msg in result["messages"]:
		# This is an AIMessage where the model decided to call a tool.
		# It contains the tool name and arguments but no output yet — the tool hasn't run yet
		if hasattr(msg, "tool_calls") and msg.tool_calls:
			for tc in msg.tool_calls:
				tool_calls.append({
					"tool": tc["name"],
					"input": tc["args"],
					"output": None,
					"_id": tc.get("id"),
				})
		# This is a ToolMessage — the result that came back after the tool ran.
		# We match it to its corresponding tool call using tool_call_id and fill in the output.
		elif hasattr(msg, "name") and msg.name:
			tool_call_id = getattr(msg, "tool_call_id", None)
			if tool_call_id:
				for tc in tool_calls:
					if tc.get("_id") == tool_call_id:
						tc["output"] = msg.content
						break
			# Fallback for older LangChain version.	Fill in the first tool call that still has output = None
			else:
				for tc in tool_calls:
					if tc["output"] is None:
						tc["output"] = msg.content
						break
		# This is the final AIMessage — the model's actual text response to the user after all tools have run. 
		# We know it's the final answer because it's an AIMessage with no tool calls attached.
		elif isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
			answer = msg.content

	for tc in tool_calls:
		tc.pop("_id", None)
	
	return answer, tool_calls

def estimate_token_usage(
		messages: list,
		answer: str,
		model_name: str,
) -> dict:
	"""Estimate token usage and cost for a single exchange."""
	all_input_text = "".join(
		msg.content if isinstance(msg.content, str) else ""
		for msg in messages
	)
	input_tokens = len(all_input_text) // 4
	output_tokens = len(answer) // 4
	costs = TOKEN_COSTS.get(model_name, {"input": 0.0004, "output": 0.0016})
	input_cost = (input_tokens / 1000) * costs["input"]
	output_cost = (output_tokens / 1000) * costs["output"]
	return {
		"input_tokens": input_tokens,
		"output_tokens": output_tokens,
		"total_tokens": input_tokens + output_tokens,
		"estimated_cost_usd": round(input_cost + output_cost, 5),
	}