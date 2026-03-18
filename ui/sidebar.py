import streamlit as st
from config import LANGUAGES, DEFAULT_LANGUAGE, MODEL_ID
from ui.strings import SIDEBAR_STRINGS

def render_sidebar() -> dict:
	with st.sidebar:
		_init_session_state()
		s = SIDEBAR_STRINGS[st.session_state.language]
		s = _render_settings(s)
		st.divider()
		_render_cost_tracker(s)
		st.divider()
		_render_clear_chat(s)
		st.divider()
		_render_about(s)
	return {
		"language": st.session_state.language,
	}

def _init_session_state():
	defaults = {
		"total_input_tokens": 0,
		"total_output_tokens": 0,
		"total_cost_usd": 0.0,
		"chat_history": [],
		"chat_metadata": [],
		"language": DEFAULT_LANGUAGE,
	}
	for key, value in defaults.items():
		if key not in st.session_state:
			st.session_state[key] = value

def _render_settings(s: dict) -> dict:
	"""Render language and model selectors. Returns refreshed strings after language change."""
	st.header(s["settings_header"])
	selected_lang_label = st.selectbox(
		s["language_label"],
		options=list(LANGUAGES.keys()),
		index=list(LANGUAGES.values()).index(st.session_state.language),
	)
	st.session_state.language = LANGUAGES[selected_lang_label]
	s = SIDEBAR_STRINGS[st.session_state.language]
	st.caption(f"Modell: `{MODEL_ID}`")
	return s

def _render_cost_tracker(s: dict):
	"""Render token usage metrics and reset button."""
	st.header(s["cost_header"])
	col1, col2 = st.columns(2)
	with col1:
		st.metric(s["tokens_input"], f"{st.session_state.total_input_tokens:,}")
		st.metric(s["tokens_output"], f"{st.session_state.total_output_tokens:,}")
	with col2:
		total = st.session_state.total_input_tokens + st.session_state.total_output_tokens
		st.metric(s["tokens_total"], f"{total:,}")
		st.metric(s["cost_label"], f"${st.session_state.total_cost_usd:.4f}")
	if st.button(s["cost_reset"], use_container_width=True):
		st.session_state.total_input_tokens = 0
		st.session_state.total_output_tokens = 0
		st.session_state.total_cost_usd = 0.0
		st.rerun()

def _render_clear_chat(s: dict):
	"""Render the clear chat button."""
	if st.button(s["clear_chat"], use_container_width=True):
		st.session_state.chat_history = []
		st.session_state.chat_metadata = []
		st.rerun()

def _render_about(s: dict):
	"""Render the about section."""
	st.header(s["about_header"])
	st.markdown(s["about_text"])

def update_cost_tracker(token_usage: dict):
	"""Add token usage from a single exchange to the running session totals."""
	if not token_usage:
		return
	st.session_state.total_input_tokens += token_usage.get("input_tokens", 0)
	st.session_state.total_output_tokens += token_usage.get("output_tokens", 0)
	st.session_state.total_cost_usd += token_usage.get("estimated_cost_usd", 0.0)
