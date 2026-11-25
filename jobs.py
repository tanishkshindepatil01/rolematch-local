"""Match a CV locally against role families and public UK tech vacancies."""

import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html import unescape
from io import BytesIO
from itertools import islice
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from documents import MAX_FILE_BYTES, SUPPORTED_TYPES, read_pdf

SKILL_ALIASES = {
    "Python": ("python",), "SQL": ("sql", "postgresql", "mysql", "sqlite"),
    "R": ("r programming", "rstudio", "tidyverse", "ggplot2"),
    "C++": ("c++",), "Java": ("java",), "JavaScript": ("javascript", "typescript", "node.js"),
    "APIs": ("api", "apis", "restful", "fastapi", "flask"),
    "PyTorch": ("pytorch", "torchvision"), "TensorFlow": ("tensorflow", "keras", "tflite"),
    "scikit-learn": ("scikit-learn", "scikit learn", "sklearn"),
    "Machine learning": ("machine learning",), "Deep learning": ("deep learning", "neural networks", "cnns", "cnn"),
    "Computer vision": ("computer vision", "object detection", "image classification", "image segmentation"),
    "YOLO": ("yolo", "yolov5", "yolov8", "yolov11", "yolo11"), "OpenCV": ("opencv",),
    "Edge deployment": ("edge deployment", "raspberry pi", "onnx", "tensorrt", "ncnn"),
    "LLMs": ("large language model", "large language models", "llm", "llms", "ollama", "generative ai", "genai"),
    "RAG": ("rag", "retrieval augmented generation", "retrieval-augmented generation", "vector search"),
    "NLP": ("nlp", "natural language processing", "text classification"),
    "Statistics": ("statistics", "statistical modelling", "statistical modeling", "hypothesis testing", "a/b testing"),
    "pandas": ("pandas",), "NumPy": ("numpy",), "Excel": ("excel",),
    "Tableau": ("tableau",), "Power BI": ("power bi", "powerbi"),
    "Data pipelines": ("etl", "elt", "data pipeline", "data pipelines", "data engineering", "data warehouse"),
    "Spark": ("spark", "pyspark", "databricks"), "Airflow": ("airflow",),
    "Cloud": ("aws", "azure", "gcp", "google cloud", "amazon web services", "ec2", "s3"),
    "Docker": ("docker", "containers", "containerization", "containerisation"),
    "Kubernetes": ("kubernetes", "k8s"), "CI/CD": ("ci/cd", "continuous integration", "github actions"),
    "Git": ("git", "github", "gitlab"), "Testing": ("pytest", "unit testing", "test automation", "unit tests"),
}


def alternation(values):
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(value) for value in values) + r")(?!\w)", re.I)


SKILL_PATTERNS = {skill: alternation(aliases) for skill, aliases in SKILL_ALIASES.items()}


@dataclass(frozen=True)
class Role:
    title: str
    job_titles: re.Pattern
    core: tuple[str, ...]
    supporting: tuple[str, ...]


ROLES = (
    Role("Computer Vision Engineer", alternation(("computer vision", "perception", "imaging")),
         ("Computer vision", "YOLO", "OpenCV", "Edge deployment"), ("Python", "PyTorch", "TensorFlow", "C++")),
    Role("Applied AI Engineer", alternation(("ai engineer", "artificial intelligence", "applied ai", "genai", "llm", "ai/ml", "ai/ ml", "ai compute", "ai software")),
         ("LLMs", "RAG", "Deep learning", "Computer vision", "NLP"), ("Python", "APIs", "PyTorch", "Cloud")),
    Role("Machine Learning Engineer", alternation(("machine learning", "ml engineer", "mlops", "machine intelligence")),
         ("Machine learning", "Deep learning", "PyTorch", "TensorFlow", "scikit-learn"), ("Python", "Docker", "Cloud", "Edge deployment")),
    Role("Data Scientist", alternation(("data scientist", "data science", "decision scientist", "quantitative researcher")),
         ("Statistics", "Machine learning", "scikit-learn", "pandas", "R"), ("Python", "SQL", "NumPy", "Tableau")),
    Role("Data Analyst", alternation(("data analyst", "business intelligence", "analytics analyst", "bi analyst", "data analytics")),
         ("Tableau", "Power BI", "Excel", "Statistics", "SQL"), ("Python", "R", "pandas")),
    Role("Data Engineer", alternation(("data engineer", "data engineering", "data platform", "analytics engineer")),
         ("Data pipelines", "Spark", "Airflow", "SQL"), ("Python", "Cloud", "Docker", "Kubernetes")),
    Role("Software Engineer", alternation(("software engineer", "software developer", "backend engineer", "platform engineer")),
         ("Python", "C++", "Java", "JavaScript", "APIs"), ("Git", "Testing", "Docker", "CI/CD", "Cloud")),
)

GREENHOUSE = {
    "graphcore": "Graphcore", "ocadogroup": "Ocado Group", "monzo": "Monzo",
    "deliveroo": "Deliveroo", "cleo": "Cleo", "canonical": "Canonical", "anthropic": "Anthropic",
}
ASHBY = {"wayve": "Wayve", "synthesia": "Synthesia", "multiverse": "Multiverse"}
UK_PLACES = ("United Kingdom", "UK", "GB", "England", "Scotland", "Wales", "Northern Ireland",
             "London", "Bristol", "Bath", "Cambridge", "Oxford", "Manchester", "Edinburgh", "Leeds",
             "Cardiff", "Belfast", "Glasgow", "Birmingham", "Newcastle", "Hatfield", "Sheffield", "Liverpool")
UK_LOCATION = alternation(UK_PLACES)
EARLY = alternation(("graduate", "new grad", "junior", "entry-level", "entry level", "early careers", "engineer i", "analyst i"))
INTERN = alternation(("intern", "internship", "placement", "apprentice", "apprenticeship"))
SENIOR = alternation(("senior", "staff", "principal", "lead", "director", "manager", "head", "distinguished", "phd"))
MAX_JOB_RESPONSE = 14 * 1024 * 1024


@dataclass(frozen=True)
class Vacancy:
    company: str
    title: str
    location: str
    url: str
    description: str


@dataclass(frozen=True)
class Match:
    vacancy: Vacancy
    role: str
    matched: tuple[str, ...]
    other_terms: tuple[str, ...]
    score: int


def cv_text(filename: str, data: bytes) -> str:
    """Read an uploaded file in memory without adding it to the portfolio index."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_TYPES or not 0 < len(data) <= MAX_FILE_BYTES:
        raise ValueError("Choose a PDF, TXT, or MD file up to 15 MiB.")
    if suffix == ".pdf":
        text = "\n".join(page for _, page in islice(read_pdf(BytesIO(data)), 12))
    else:
        text = data.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("No selectable text found. Export the CV as text or use a searchable PDF.")
    return text[:120_000]


def skills_in(text: str) -> frozenset[str]:
    normalized = " ".join(unicodedata.normalize("NFKC", text).split())
    return frozenset(skill for skill, pattern in SKILL_PATTERNS.items() if pattern.search(normalized))


def role_evidence(role: Role, skills: frozenset[str]) -> tuple[str, ...]:
    return tuple(skill for skill in (*role.core, *role.supporting) if skill in skills)


def suggested_roles(skills: frozenset[str]) -> list[Role]:
    scores = [(3 * len(skills.intersection(role.core)) + len(skills.intersection(role.supporting)), role)
              for role in ROLES if skills.intersection(role.core)]
    return [role for _, role in sorted(scores, key=lambda row: row[0], reverse=True)]


def within_location(location: str, target: str) -> bool:
    if not UK_LOCATION.search(location):
        return False
    if target == "United Kingdom":
        return True
    if target == "Remote (UK)":
        return bool(alternation(("remote", "home based", "home-based")).search(location))
    return bool(alternation((target,)).search(location))


def rank_jobs(vacancies, skills, target, level) -> list[Match]:
    roles = suggested_roles(skills)
    role_priority = {role.title: len(roles) - position for position, role in enumerate(roles)}
    matches = []
    for vacancy in vacancies:
        if not within_location(vacancy.location, target):
            continue
        if level != "Any level" and (SENIOR.search(vacancy.title) or not (
            EARLY.search(vacancy.title) or (level == "Include internships" and INTERN.search(vacancy.title))
        )):
            continue
        role = next((role for role in roles if role.job_titles.search(vacancy.title)), None)
        if role is None:
            continue
        terms = skills_in(f"{vacancy.title} {vacancy.description}")
        evidence = role_evidence(role, terms & skills)
        if not evidence:
            continue
        overlap = terms & skills
        score = 4 * len(evidence) + len(overlap) + 3 * role_priority[role.title]
        matches.append(Match(vacancy, role.title, evidence, tuple(sorted(terms - skills)), score))
    return sorted(matches, key=lambda match: (-match.score, match.vacancy.company, match.vacancy.title))


def read_board(provider: str, token: str, company: str) -> list[Vacancy]:
    greenhouse = provider == "greenhouse"
    url = (f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true" if greenhouse
           else f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    headers = {"Accept": "application/json", "User-Agent": "RoleMatch-Local/2.0 public-job-board-reader"}
    with urlopen(Request(url, headers=headers), timeout=7) as response:
        body = response.read(MAX_JOB_RESPONSE + 1)
    if len(body) > MAX_JOB_RESPONSE:
        raise ValueError("Job board response exceeded the size limit.")
    listings = json.loads(body)["jobs"]
    vacancies = []
    for item in listings:
        if not greenhouse and item.get("isListed") is False:
            continue
        title = item["title"].strip()
        location = item.get("location") or ""
        if greenhouse:
            location = location.get("name", "") if isinstance(location, dict) else ""
            offices = [office.get("location", "") for office in (item.get("offices") or [])]
            location = "; ".join(dict.fromkeys(part for part in [location, *offices] if part))
        else:
            places = [place.get("location", "") for place in (item.get("secondaryLocations") or [])]
            location = "; ".join(dict.fromkeys(part for part in [location, *places] if part))
        if not UK_LOCATION.search(location) or not any(role.job_titles.search(title) for role in ROLES):
            continue
        listing_url = item["absolute_url" if greenhouse else "jobUrl"]
        parsed = urlsplit(listing_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            continue
        plain = item.get("descriptionPlain", "") if not greenhouse else ""
        if not plain:
            markup = item.get("content" if greenhouse else "descriptionHtml") or ""
            decoded = unescape(unescape(markup))
            decoded = re.sub(r"<(?:br\s*/?|/p|/li|/div|/h[1-6])\s*>", "\n", decoded, flags=re.I)
            plain = re.sub(r"<[^>]*>", " ", decoded)
        description = "\n".join(" ".join(line.split()) for line in plain.splitlines() if line.strip())
        vacancies.append(Vacancy(company, title, location, listing_url, description[:32_000]))
    return vacancies


def fetch_public_jobs() -> tuple[list[Vacancy], tuple[str, ...]]:
    boards = [("greenhouse", token, name) for token, name in GREENHOUSE.items()]
    boards += [("ashby", token, name) for token, name in ASHBY.items()]
    vacancies, unavailable = {}, []
    with ThreadPoolExecutor(max_workers=5) as pool:
        pending = [(company, pool.submit(read_board, provider, token, company))
                   for provider, token, company in boards]
        for company, future in pending:
            try:
                for vacancy in future.result():
                    vacancies[vacancy.url] = vacancy
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                unavailable.append(company)
    return list(vacancies.values()), tuple(unavailable)
