"""
ui/chat.py — Chat rendering and input handling for the Berlin Zoning Assistant.
"""

import streamlit as st

from chain.agent import run_agent
from config import MIN_INPUT_LENGTH, MAX_INPUT_LENGTH, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
from ui.rate_limiter import check_rate_limit
from ui.sidebar import update_cost_tracker
from ui.strings import COMPONENT_STRINGS
from ui.components import (
	render_chat_message,
	render_technical_details,
)

def init_chat_state():
	"""
	Initialise chat-related session state keys if they don't exist yet.
	Safe to call on every rerun, the 'not in' check prevents resetting.
	"""
	if "chat_history" not in st.session_state:
		st.session_state.chat_history = []
	if "chat_metadata" not in st.session_state:
		st.session_state.chat_metadata = []

def render_chat_history(language: str):
	"""
	Replay the full conversation from session state.
	Called on every Streamlit rerun to rebuild the chat UI from scratch,
	since Streamlit clears the screen on each rerun.
	meta_index only advances for assistant messages because chat_metadata
	only has one entry per assistant turn, not per message.
	"""
	meta_index = 0
	for msg in st.session_state.chat_history:
		render_chat_message(msg["role"], msg["content"])

		if msg["role"] == "assistant" and meta_index < len(st.session_state.chat_metadata):
			meta = st.session_state.chat_metadata[meta_index]
			render_technical_details(
				tool_calls=meta.get("tool_calls", []),
				source_chunks=meta.get("sources", []),
				token_usage=meta.get("token_usage"),
				language=language,
				map_index=meta_index,
			)
			meta_index += 1

def _validate_input(text: str, s: dict) -> tuple[bool, str]:
	stripped = text.strip()
	if not stripped:
		return False, ""
	if len(stripped) < MIN_INPUT_LENGTH:
		return False, s["input_too_short"].format(min=MIN_INPUT_LENGTH)
	if len(text) > MAX_INPUT_LENGTH:
		return False, s["input_too_long"].format(length=len(text), max=MAX_INPUT_LENGTH)
	return True, ""

def handle_user_input(language: str, vector_store):
	"""
	Render the chat input box and handle a new message end-to-end:
	1. Validate the input (length checks)
	2. Check rate limit (sliding window)
	3. Show the user's message immediately
	4. Run the agent
	5. Show the assistant's response + technical details
	6. Persist everything to session state
	7. Update the cost tracker
	"""
	s = COMPONENT_STRINGS[language]
 
	user_input = st.chat_input(
		"Frage zur Berliner Bebauungsordnung stellen..." if language == "de"
		else "Ask about Berlin zoning regulations..."
	)
 
	if not user_input:
		return
 
	# Step 1: Input validation
	valid, validation_error = _validate_input(user_input, s)
	if not valid:
		if validation_error:  # empty string = silently skip, non-empty = show error
			st.error(validation_error)
		return
 
	# Step 2: Rate limiting
	allowed, wait_seconds = check_rate_limit()
	if not allowed:
		st.error(s["rate_limit_exceeded"].format(
			limit=RATE_LIMIT_REQUESTS,
			window=RATE_LIMIT_WINDOW_SECONDS,
			wait=wait_seconds,
		))
		return
	
	# Step 3: Show user message immediately, don't wait for the agent
	render_chat_message("user", user_input)
	st.session_state.chat_history.append({"role": "user", "content": user_input})
 
	# Step 4: Run the agent
	with st.spinner(s["thinking"]):
		answer_stream, get_result = run_agent(
			user_input=user_input,
			language=language,
			chat_history=st.session_state.chat_history[:-1],
			vector_store=vector_store,
		)

	# Step 5: Show assistant response
	with st.chat_message("assistant"):
		streamed_text = st.write_stream(answer_stream)
	
	result = get_result()

	render_technical_details(
		tool_calls=result["tool_calls"],
		source_chunks=result["sources"],
		token_usage=result["token_usage"],
		language=language,
		map_index=len(st.session_state.chat_metadata),
	)
	# Step 6: Add assistant response to history
	st.session_state.chat_history.append({
		"role":		"assistant",
		"content":	streamed_text,
	})
	st.session_state.chat_metadata.append({
		"tool_calls":	result["tool_calls"],
		"sources":		result["sources"],
		"token_usage":	result["token_usage"],
	})
 
	update_cost_tracker(result["token_usage"])