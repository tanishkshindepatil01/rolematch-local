"""Offer a reviewable, consent-gated CV tailoring and export flow."""

import hashlib
import os
from html import escape
from pathlib import Path

import streamlit as st

from jobs import Vacancy
from overleaf import available_sources, export_overleaf
from tailor import OPENAI_MODEL, SUMMARY_LIMIT, draft_with_openai, local_summary, relevant_evidence, split_resume


@st.dialog("Tailor your CV", width="large")
def tailor_dialog(cv_text: str, vacancy: Vacancy) -> None:
    context = hashlib.sha256(f"{cv_text}\0{vacancy.url}\0{vacancy.title}\0{vacancy.description}".encode()).hexdigest()[:20]
    prefix = f"tailor_{context}_"
    resume = split_resume(cv_text)
    evidence = relevant_evidence(resume, vacancy)
    draft_key = prefix + "draft"
    approval_key = prefix + "approved"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = local_summary(resume, vacancy, evidence)

    st.html(f'<p class="rolematch-job-kicker">{escape(vacancy.company or "Selected job")}</p><h3 class="rolematch-role-title">{escape(vacancy.title)}</h3>')
    if vacancy.url:
        st.link_button("View original advert ↗", vacancy.url)

    st.markdown("#### 1 · Check the evidence")
    with st.expander("Job description", expanded=False):
        st.text_area("Advert text", vacancy.description or "This advert has no description. Paste one in the OpenAI panel if needed.",
                     height=160, disabled=True, label_visibility="collapsed")
    with st.expander("Relevant CV evidence", expanded=False):
        if not evidence:
            st.caption("No detailed excerpts matched the advert. Review the source text and write a summary you can support.")
        for line in evidence:
            st.text(line)

    with st.expander("Draft with OpenAI", expanded=False):
        st.caption(f"Optional · {OPENAI_MODEL}. API usage is billed separately. Review the exact text below before sending it to OpenAI.")
        with st.form(prefix + "cloud"):
            sent_evidence = st.text_area("CV excerpts to send", "\n\n".join(evidence), max_chars=6_000, height=140)
            sent_description = st.text_area("Job description to send", vacancy.description[:16_000], max_chars=16_000, height=120)
            key = st.text_input("OpenAI API key", type="password", placeholder="Use your key or configure OPENAI_API_KEY")
            consent = st.checkbox("I approve sending the displayed excerpts and job description to OpenAI.")
            send = st.form_submit_button("Send approved text and draft")
        if send:
            if not consent:
                st.warning("Approve the text above before sending it to OpenAI.")
            else:
                try:
                    with st.spinner("Drafting from your approved excerpts…"):
                        st.session_state[draft_key] = draft_with_openai(key or os.getenv("OPENAI_API_KEY", ""), sent_evidence, sent_description)
                    st.session_state.pop(approval_key, None)
                    st.success("Draft updated. Check it before exporting.")
                except (ValueError, RuntimeError) as error:
                    st.error(str(error))

    st.markdown("#### 2 · Add your Overleaf source")
    st.caption("In Overleaf, choose File → Download as source (.zip). You can also use the individual .tex file.")
    source = st.file_uploader("Overleaf source", type=("zip", "tex"), max_upload_size=15, key=prefix + "source")
    target, original, source_bytes = None, None, None
    if source is not None:
        source_bytes = source.getvalue()
        try:
            candidates = available_sources(Path(source.name).name, source_bytes)
            target = st.selectbox("File containing Professional Summary", list(candidates), key=prefix + "target")
            original = candidates[target].original
        except ValueError as error:
            st.error(str(error))

    st.markdown("#### 3 · Review the summary")
    current, proposed = st.columns(2)
    with current:
        st.text_area("Current summary", original or resume.old_summary or "No separate summary was detected.", height=155, disabled=True)
    with proposed:
        final_text = st.text_area("Proposed summary · editable", key=draft_key, max_chars=SUMMARY_LIMIT, height=155)
    st.caption("The starting draft uses skills and wording found on this Mac. Check every claim before approving it.")
    if original is not None:
        st.caption(f"Original summary: {len(original)} characters. A longer replacement can affect page breaks, so check the compiled PDF in Overleaf.")

    st.markdown("#### 4 · Approve and download")
    st.caption("Only the selected summary paragraph changes. Open the downloaded source in Overleaf, recompile, and download the PDF there.")
    digest = hashlib.sha256(source_bytes).hexdigest() if target else None
    snapshot = (digest, target, final_text.strip())
    checked = st.checkbox("I’ve checked the draft against my CV and the selected job.", key=prefix + "checked")
    ready = checked and bool(target and final_text.strip())
    if st.button("Approve & prepare Overleaf export", type="primary", key=prefix + "approve", disabled=not ready):
        try:
            filename = Path(source.name).name
            updated = export_overleaf(filename, source_bytes, target, final_text)
            st.session_state[approval_key] = (snapshot, updated, filename)
        except (ValueError, OSError) as error:
            st.error(f"Could not prepare the source export. {error}")
    approved = st.session_state.get(approval_key)
    if ready and approved and approved[0] == snapshot:
        original_path = Path(approved[2])
        extension = original_path.suffix.lower()
        mime = "application/zip" if extension == ".zip" else "application/x-tex"
        st.download_button("Download updated Overleaf source", approved[1], file_name=f"{original_path.stem}-tailored{extension}",
                           mime=mime, type="primary", key=prefix + "download", on_click="ignore")
    elif approved:
        st.caption("Approve the current draft to update the download.")
