"""Streamlit résumé upload and job matching screen."""

from dataclasses import dataclass
from html import escape
from pathlib import Path

import streamlit as st
from pypdf.errors import PyPdfError

from documents import MAX_FILE_BYTES, scan_folder
from jobs import Match, Vacancy, cv_text, fetch_public_jobs, rank_jobs, role_evidence, skills_in, suggested_roles
from tailor_view import tailor_dialog

LOCATIONS = ("United Kingdom", "Bristol", "London", "Cambridge", "Manchester", "Edinburgh", "Remote (UK)")
LEVELS = ("Graduate & junior", "Include internships", "Any level")


@dataclass(frozen=True)
class SearchResult:
    label: str
    sample: bool
    text: str
    skills: frozenset[str]
    matches: list[Match]
    unavailable: tuple[str, ...]
    location: str
    level: str


@st.cache_data(ttl=600, show_spinner=False)
def public_jobs():
    return fetch_public_jobs()


def run_search(label, text, sample, location, level) -> SearchResult:
    skills = skills_in(text)
    matches, unavailable = [], ()
    if suggested_roles(skills):
        vacancies, unavailable = public_jobs()
        matches = rank_jobs(vacancies, skills, location, level)
    return SearchResult(label, sample, text, skills, matches, unavailable, location, level)


def show_results(result: SearchResult) -> None:
    if result.sample:
        st.info("These matches use a fictional CV. The vacancy links come from live employer boards.")
    roles = suggested_roles(result.skills)
    if not roles:
        st.warning("I couldn’t match this CV to an AI, data, or software role. Try a CV with more detail about your technical skills and projects.")
    else:
        st.header("Suggested roles")
        st.text(f"Based on {result.label} · {result.location} · {result.level}")
        for column, role in zip(st.columns(len(roles[:3])), roles[:3], strict=True):
            with column.container(border=True, key=f"role_{role.title.split()[0].lower()}_{roles.index(role)}"):
                st.subheader(role.title)
                st.caption(", ".join(role_evidence(role, result.skills)))

    st.header("Open vacancies")
    st.caption("Selected UK employer boards · ranked by title fit and skills mentioned in both your CV and the listing.")
    if result.unavailable:
        st.warning(f"Some employer boards were unavailable ({', '.join(result.unavailable)}).")
    if not result.matches:
        st.info("No matches from these boards for the current filters. Try United Kingdom or a wider experience level.")
    for position, match in enumerate(result.matches[:10]):
        vacancy = match.vacancy
        with st.container(border=True, key=f"vacancy_{position}"):
            st.html(f'<p class="rolematch-job-kicker">{escape(vacancy.company)}</p><h3 class="rolematch-role-title">{escape(vacancy.title)}</h3>')
            st.text(f"{vacancy.location} · {match.role}")
            st.markdown("**CV overlap**")
            st.text(", ".join(match.matched))
            if match.other_terms:
                st.caption("Other advertised skills · " + ", ".join(match.other_terms[:6]))
            actions, listing = st.columns((1, 2), gap="small")
            with actions:
                if st.button("Tailor my CV", type="primary", key=f"tailor_job_{position}"):
                    tailor_dialog(result.text, vacancy)
            with listing:
                st.link_button("View employer listing ↗", vacancy.url)
    with st.expander("Already have a job description?"):
        with st.form("tailor_manual"):
            job_title = st.text_input("Job title", max_chars=200)
            company = st.text_input("Employer", max_chars=140)
            description = st.text_area("Paste the advert", max_chars=32_000, height=135)
            open_manual = st.form_submit_button("Tailor for this job")
        if open_manual:
            if job_title.strip() and description.strip():
                tailor_dialog(result.text, Vacancy(company.strip(), job_title.strip(), result.location, "", description.strip()))
            else:
                st.warning("Add the job title and advert first.")


def job_finder(data: Path, sample_data: Path) -> None:
    st.html('''
        <section class="rolematch-hero" aria-label="RoleMatch Local job finder">
            <div class="rolematch-halo" aria-hidden="true"></div>
            <div class="rolematch-hero-copy">
                <h1>Your next move,<br><em>in focus.</em></h1>
                <p>Find roles that fit. Shape your CV for the one you want.</p>
                <ol class="rolematch-steps"><li>Find a role</li><li>Review your summary</li><li>Export to Overleaf</li></ol>
            </div>
        </section>
    ''')

    with st.container(border=True, key="cv_panel"):
        upload_column, filter_column = st.columns((1.5, 1), gap="large")
        with upload_column:
            st.subheader("Your CV")
            uploaded = st.file_uploader(
                "Drag in a CV or browse for a file", type=("pdf", "txt", "md"), max_upload_size=15,
                key="job_cv_upload",
            )
            saved_files = scan_folder(data).files
            saved = None
            if saved_files:
                saved = st.selectbox(
                    "Or use a CV from your data folder", saved_files, index=None,
                    format_func=lambda path: path.relative_to(data).as_posix(), key="job_cv_saved",
                )
            st.caption("Job matching runs on this Mac. Sending text to OpenAI is optional.")
        with filter_column:
            st.subheader("Where to look")
            location = st.selectbox("Location", LOCATIONS, key="job_location")
            level = st.selectbox("Experience level", LEVELS, key="job_level")
            search = st.button("Find my matches", type="primary", width="stretch")
            sample = st.button("Try a fictional CV", width="stretch")

    selected_key = uploaded.file_id if uploaded is not None else saved
    current_key = (selected_key, location, level)
    if search or sample:
        st.session_state.pop("job_result", None)
        if not sample and uploaded is None and saved is None:
            st.warning("Drop in a CV or choose a file from your data folder first.")
            return
        try:
            with st.spinner("Reading the CV and checking employer boards…", show_time=True):
                if sample:
                    label = "Maya Reed · fictional CV"
                    text = "\n".join(path.read_text() for path in sorted(sample_data.iterdir()) if path.is_file())
                    text = text.replace("# Fictional sample CV · Maya Reed", "Maya Reed", 1)
                elif uploaded is not None:
                    label = Path(uploaded.name).name
                    text = cv_text(label, uploaded.getvalue())
                else:
                    label = saved.name
                    if saved.stat().st_size > MAX_FILE_BYTES:
                        raise ValueError("Choose a file up to 15 MiB.")
                    text = cv_text(label, saved.read_bytes())
                result = run_search(label, text, sample, location, level)
            st.session_state.job_result = (current_key, result)
        except (OSError, ValueError, PyPdfError) as error:
            st.error(f"Could not read this CV. {error}")

    previous = st.session_state.get("job_result")
    if previous and previous[0] == current_key:
        show_results(previous[1])
