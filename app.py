import logging
import streamlit as st
 
from rag.embeddings import get_or_create_vector_store
from ui.sidebar import render_sidebar
from ui.components import render_welcome
from ui.chat import init_chat_state, render_chat_history, handle_user_input

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

st.set_page_config(
	page_title="Berlin Zoning Assistant",
	page_icon="🏗️",
	layout="wide",
	initial_sidebar_state="expanded",
)

@st.cache_resource(show_spinner=False)
def load_vector_store():
	with st.spinner("Loading knowledge base... (first run may take ~30 seconds)"):
		return get_or_create_vector_store()

def main():
	settings = render_sidebar()
	language = settings["language"]

	vector_store = load_vector_store()
	init_chat_state()

	if not st.session_state.chat_history:
		render_welcome(language)
	else:
		render_chat_history(language)
	
	handle_user_input(language, vector_store)

if __name__ == "__main__":
	main()
