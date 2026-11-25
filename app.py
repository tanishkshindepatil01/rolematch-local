"""RoleMatch Local's local Streamlit interface."""

import json
import os
import subprocess
from pathlib import Path

import streamlit as st
from chromadb.errors import ChromaError

from documents import scan_folder
from job_view import job_finder
from rag import Answer, LocalModelError, MAX_QUESTION_LENGTH, PortfolioIndex

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUNTIME = Path(os.environ.get("ROLEMATCH_RUNTIME", ROOT / ".local"))
ERRORS = (ChromaError, OSError, RuntimeError, ValueError)
LABELS = {"personal": "My documents", "sample": "Fictional sample"}
EXAMPLES = (
    ("Work experience", "What did Maya build at Northbank Labs?"),
    ("Project stack", "List every technology Maya used to build TrailNotes."),
    ("Missing fact", "What salary did Maya earn at Northbank Labs?"),
)


@st.cache_resource
def open_index(directory: Path) -> PortfolioIndex:
    return PortfolioIndex(directory / "chroma")


def show_answer(answer: Answer) -> None:
    with st.chat_message("assistant"):
        st.text(answer.text)
        if answer.sources:
            with st.expander("View cited excerpts"):
                for source in answer.sources:
                    st.text(source.label)
                    st.text(source.excerpt)


def portfolio_chat() -> None:
    st.title("Portfolio chat")
    st.caption("Ask about your experience and see the source behind each answer.")
    personal = scan_folder(DATA)
    with st.sidebar:
        st.header("Documents")
        mode = st.radio(
            "Collection", list(LABELS), index=0 if personal.files else 1,
            format_func=LABELS.get, key="collection",
        )
        corpus = personal if mode == "personal" else scan_folder(ROOT / "sample_data")
        st.caption(f"{len(corpus.files)} supported files found · PDF, TXT, or MD")
        if st.button("Open data folder"):
            try:
                DATA.mkdir(parents=True, exist_ok=True)
                subprocess.run(["/usr/bin/open", str(DATA)], check=True, capture_output=True)
            except (OSError, subprocess.CalledProcessError):
                st.warning("Open the data folder inside RoleMatch Local in Finder.")
        for warning in corpus.warnings:
            st.warning(warning)

    if mode == "sample":
        st.info("Fictional demo · Maya Reed’s sample CV and TrailNotes project.")
    if not corpus.files:
        st.info("Use **Open data folder** to add your files, then refresh the page.")
        st.stop()

    try:
        index = open_index(RUNTIME)
        collection = index.ready_collection(mode, corpus)
        create_index = mode == "sample" and collection is None
        if mode == "personal":
            create_index = st.sidebar.button("Index documents", type="primary", disabled=collection is not None)
        if create_index:
            with st.spinner("Preparing your local search index…"):
                collection = index.build(mode, corpus)
        if collection is None:
            st.info("Select **Index documents** in the sidebar to prepare your files.")
            st.stop()
        count = collection.count()
        st.sidebar.success(f"{count} passages indexed")
        for warning in json.loads(collection.metadata.get("warnings", "[]")):
            st.sidebar.warning(warning)
    except LocalModelError as error:
        st.error(str(error))
        st.stop()
    except ERRORS as error:
        st.error(f"Could not prepare the local index. {error}")
        st.stop()

    if not count:
        st.warning("No text could be indexed. Check the file messages in the sidebar.")
        st.stop()

    snapshot = (mode, corpus.fingerprint)
    if st.session_state.get("chat_snapshot") != snapshot:
        st.session_state.chat_snapshot = snapshot
        st.session_state.history = []
    if st.sidebar.button("Clear chat"):
        st.session_state.history = []

    suggested = None
    if not st.session_state.history:
        if mode == "sample":
            for column, (label, example) in zip(st.columns(3), EXAMPLES, strict=True):
                if column.button(label):
                    suggested = example
        else:
            st.caption("Try asking about a named role, skill, or project from your files.")

    for question, answer in st.session_state.history:
        with st.chat_message("user"):
            st.text(question)
        show_answer(answer)

    typed = st.chat_input("Ask a standalone question", max_chars=MAX_QUESTION_LENGTH)
    question = (typed or suggested or "").strip()
    if question:
        with st.chat_message("user"):
            st.text(question)
        try:
            with st.spinner("Searching your documents and composing an answer…"):
                answer = index.answer(mode, corpus, question)
        except LocalModelError as error:
            st.error(str(error))
        except ERRORS as error:
            st.error(f"Could not answer this question. {error}")
        else:
            show_answer(answer)
            st.session_state.history = (st.session_state.history + [(question, answer)])[-20:]
            if suggested:
                st.rerun()


def main() -> None:
    st.set_page_config(page_title="RoleMatch Local · CV and job finder", page_icon="◼", layout="wide")
    st.html(ROOT / "interface.css")
    st.html('<div class="rolematch-wordmark">RoleMatch Local<span>.</span></div>')
    if os.environ.get("ROLEMATCH_VIEW") == "portfolio":
        portfolio_chat()
    else:
        job_finder(DATA, ROOT / "sample_data")


if __name__ == "__main__":
    main()
