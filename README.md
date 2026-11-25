# RoleMatch Local

RoleMatch Local suggests job roles from your CV, ranks open vacancies from selected UK employers, and helps you tailor the professional summary in your Overleaf CV. A separate portfolio demo answers questions using cited excerpts from your files.

```text
CV → rank public vacancies → review a tailored summary → approve → export Overleaf source → recompile PDF
```

## Run on macOS

Install Python 3.12, then open the extracted source folder or clone this repository. Run the launcher from the project folder.

```bash
brew install python@3.12
git clone https://github.com/tanishkshindepatil01/rolematch-local.git
cd rolematch-local
bash launcher/server.sh
```

The first run installs Python dependencies and needs an internet connection. Open
`http://127.0.0.1:8501` if the browser does not open automatically. Press **Control+C**
in Terminal to stop the server. Job Finder runs without downloading an AI model.

To try it without uploading a personal document, select **Try a fictional CV**. The source package includes the fictional documents used by both demos.

## Find jobs from a CV

1. Open **Job finder**. Drag and drop a PDF, TXT, or Markdown CV, browse for one, or pick a file already in `data/`. You can use **Try a fictional CV** to see the workflow.
2. Choose a location and experience level, then select **Find my matches**. RoleMatch Local shows role suggestions and up to 10 matching vacancies. The graduate filter looks for early-career wording in the job title. If you see few matches, try **United Kingdom** or **Any level**.
3. Open **View employer listing** for the original advert. **CV overlap** lists recognized terms present in both documents. **Other advertised skills** shows terms RoleMatch Local found in the advert and did not match in your CV. Read the full advert to check requirements.

The job finder analyses the CV locally in memory and fetches public listings from a fixed selection of Greenhouse and Ashby employer boards. The listing requests contain no CV text, filename, or CV-derived keywords. Search covers AI, data, and software roles from those employers. It needs internet access for vacancies and caches public listings for up to 10 minutes. Role suggestions still work when employer boards are unavailable. [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html) · [Ashby public job postings API](https://developers.ashbyhq.com/docs/public-job-posting-api)

## Tailor your CV and keep its Overleaf layout

1. Choose **Tailor my CV** on a vacancy. You can also paste an advert you found elsewhere under **Already have a job description?** after loading your CV.
2. Review the advert and CV evidence. RoleMatch Local prepares an editable starting summary locally from wording and skills it finds in the CV.
3. To draft with an OpenAI model, open **Draft with OpenAI**. Review and edit the exact CV excerpts and job description shown. Enter an OpenAI API key, or set `OPENAI_API_KEY` for the launcher. Approve the displayed text and click **Send approved text and draft**. API usage is billed separately from ChatGPT. [Billing details](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)
4. In Overleaf choose **File → Download as source (.zip)**, or download the individual `.tex` file. Add it under **Overleaf source**, choose the file containing **Professional Summary**, and compare the current and proposed wording. Make sure the Overleaf source and the CV used for matching are the same version. [Overleaf download instructions](https://docs.overleaf.com/managing-projects-and-files/downloading-a-project)
5. Confirm the draft, click **Approve & prepare Overleaf export**, then **Download updated Overleaf source**. Your browser downloads a new file. Upload the ZIP as a new Overleaf project or replace the corresponding file in a copy of your project. Recompile and download the PDF. [Overleaf upload instructions](https://docs.overleaf.com/managing-projects-and-files/uploading-a-project)

RoleMatch Local changes only the summary text span. Formatting commands, other sections, and project assets stay intact. It accepts a single summary paragraph, including common LaTeX list wrappers. For complex inline formatting or multiple summary items, it asks you to edit directly in Overleaf. A longer or shorter summary can change line wraps and page breaks. The app exports source locally without editing your live Overleaf project.

## Separate portfolio demo

Run the portfolio demo on its own port or stop the job finder first. Press **Control+C** to stop the local server and Ollama instance. The first launch downloads about 2.8 GB of models.

```bash
brew install ollama
ROLEMATCH_VIEW=portfolio ROLEMATCH_APP_PORT=8502 bash launcher/server.sh
```
 [Qwen3 4B Instruct](https://ollama.com/library/qwen3:4b-instruct) · [Nomic Embed Text v1.5](https://ollama.com/library/nomic-embed-text:v1.5)

1. In the demo’s sidebar, select **Open data folder**. If the sidebar is collapsed, open it with the arrow at the top left. In Finder, this is the `data` folder inside `RoleMatch Local`.
2. Copy in a CV and project write-ups as PDF, TXT, or Markdown. Use PDFs with selectable text, or export scanned pages to text locally. Individual files can be up to 15 MiB.
3. Refresh the browser, select **My documents**, and click **Index documents**. Repeat this after adding, editing, or deleting files. RoleMatch Local reuses the index when files are unchanged.
4. Ask a standalone question that includes the project or employer name. Open **View cited excerpts** and verify the answer against the source.

The fictional sample is separate from your own documents. Its questions cover work experience, project tools, and a missing fact.

## Learn the code

| File | What it does |
| --- | --- |
| `documents.py` | Loads files, preserves PDF page numbers, and splits text into overlapping passages. |
| `rag.py` | Calls Ollama on localhost, stores embeddings in Chroma, retrieves passages, and checks citation numbers. |
| `jobs.py` | Reads the uploaded CV in memory, matches role categories, fetches public listings, and ranks them locally. |
| `app.py` and `job_view.py` | Provide the job finder, role and vacancy cards, and portfolio chat. |
| `tailor.py`, `tailor_view.py`, and `overleaf.py` | Prepare drafts, require approval, and replace only the summary in the LaTeX source. |
| `launcher/` | Contains the local server script and Swift source for the Mac app and its icon. |

## Privacy and memory

- The launcher binds the app and the portfolio demo model to `127.0.0.1` and disables Ollama cloud features. Job matching, the starting summary, and Overleaf source export run on the Mac without a paid API or account. Optional OpenAI drafting sends the text you approve and uses `store: false`. [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data)
- The standalone project stores models, logs, and the Chroma index inside `.local/`. The index contains source excerpts. Stop the app and remove `.local/chroma/` if you want to discard the index. `data/` and `.local/` are excluded from Git.
- RoleMatch Local processes embeddings in batches of 16 passages, retrieves up to four, and uses a 4,096-token context with the quantized chat model. These settings are intended for running the app and models with a small portfolio on a laptop. Actual memory use depends on the workload.
- RoleMatch Local checks whether citation numbers match retrieved passages. Read the excerpts to check for unsupported claims or omitted details.

## Demo walkthrough

1. **Introduce the problem.** “I built RoleMatch Local so someone can ask questions about my experience and see the original evidence behind each answer. It runs locally on my Mac.”
2. **Find and tailor for a real vacancy.** Drop in a CV, select **Graduate & junior**, and open **Tailor my CV**. Show the evidence, approve the summary, and export the source to recompile in Overleaf. The job finder fetches public vacancies, while matching happens locally.
3. **Show the RAG workflow if asked.** Open the separate **Portfolio Demo** from `Extras`, then ask what you built in a named project. Open the citation and check the passage. Ask about an absent certification to demonstrate how it handles missing evidence.
4. **Explain a design choice.** The smaller model and short context reduce memory usage. Rehearse with your own files, prepare two questions with known answers, and ask one question before screen sharing to warm the models.
