# Perish or Publish Linux (`pop-linux`)

`pop-linux` (**Perish or Publish Linux**) is a native Python CLI application for Linux. It provides multi-source academic paper harvesting, bibliometric calculations ($h$, $g$, $e$, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$), multi-provider data deduplication, SQLite search snapshot tracking, and a Playwright browser bridge for interactive Google Scholar challenge handling.

---

## ❓ Why It Was Created & Comparison with Original Software

### Motivation & Background
The original **Publish or Perish** desktop software was created by **Professor Anne-Wil Harzing** ([harzing.com](https://www.harzing.com)) and has long been the gold standard for scholars evaluating academic impact across literature databases. The original application is a lightweight, highly efficient Windows desktop executable (~3.1 MB download).

However, because the original software is natively available only for Microsoft Windows (and macOS via Wine/Crossover), Linux users traditionally had to rely on compatibility workarounds like Wine, Proton, WinPodx, or Virtual Machines to run it.

`pop-linux` was created specifically to give Linux scholars a **100% native Linux CLI alternative**—ensuring users do not need Microsoft Windows or any emulation workarounds (Wine/WinPodx/Proton/VMs) at all, while enabling direct integration into Linux terminal workflows, shell scripts, Cron jobs, and automated data pipelines.

---

### 📊 Feature Comparison Matrix

| Feature Dimension | Original Desktop Software (Harzing PoP) | `pop-linux` (Linux Native CLI) |
|---|---|---|
| **Target Platform** | Microsoft Windows GUI (~3.1 MB) & macOS | Native Linux CLI (Python 3.11+) |
| **Windows Dependency** | Requires Windows (or Wine/WinPodx/Proton wrappers on Linux) | **Zero Windows dependency** — 100% native Linux CLI |
| **Interface & Workflow** | Interactive Desktop GUI | Rich terminal output + scriptable CLI |
| **Supported Data Sources** | Google Scholar, GS Profiles, OpenAlex, Crossref, PubMed, Semantic Scholar, Scopus*, Web of Science* (*Subscription/Key required) | OpenAlex (Default), Semantic Scholar, Crossref, PubMed, Google Scholar, Google Scholar Profiles, plus `--provider all` multi-source search |
| **Google Scholar CAPTCHA Bridge** | Manual browser popup / proxy configuration when blocked | Playwright Chromium browser bridge that opens when blocked, allows interactive challenge solving, and saves session cookies (`~/.config/pop_linux/cookies.json`) for reuse |
| **Multi-Provider Search** | Single-provider queries (manual inspection per database) | `--provider all` parallel multi-source harvesting with automated DOI & fuzzy title ($\ge 0.92$) deduplication |
| **Bibliometrics Suite** | Standard Harzing metrics ($h, g, e, hI_{\text{annual}}, hL_{\text{norm}}, \text{AWCR}, \text{AW-index}, i10$) | Implements the listed bibliometric metrics over the returned dataset + `--show-h-core` CLI filter |
| **Search History & Trajectory** | Saved search files (`.pop` / XML) | Native SQLite database (`~/.config/pop_linux/history.sqlite3`) auto-saving all search snapshots with `pop-linux history` and `pop-linux diff <snap1> <snap2>` citation growth tracking |
| **File Merging** | Manual GUI row management | `pop-linux merge file1.json file2.json` CLI command |
| **Export Formats** | CSV, EndNote, PDF, BibTeX, Copy-to-clipboard | BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), RIS (`.ris`) |

---

## ⭐ Implemented Capabilities and Linux-Oriented Extensions

> [!IMPORTANT]
> **Summary**: `pop-linux` implements the listed bibliometric metrics and adds parallel multi-provider search, interactive Google Scholar challenge handling with cookie reuse, and native SQLite citation trajectory diffing.

### 🎯 Bibliometrics Engine
Calculates the following bibliometric metrics over the papers returned by the current search or loaded dataset:
- **Impact Indices**: $h$-index, $g$-index, $e$-index (excess citations), $hI_{\text{annual}}$ (individual annual h-index).
- **Normalized & Age-Weighted Indices**: $hL_{\text{norm}}$ (author-count normalized h-index), $\text{AWCR}$ (Age-Weighted Citation Rate), and $\text{AW-index}$.
- **Summary Statistics**: $i10$-index, total citations, average citations per paper, citations per author, papers per author, citations per year.
- 💡 **`pop-linux` Bonus**: Includes a `--show-h-core` CLI flag to isolate and display only the $h$-core paper subset.

### 🔀 Multi-Source Harvesting & Concurrent Search (`pop-linux` Superiority)
- **Windows PoP**: Queries one database at a time.
- **`pop-linux`**: Supports querying individual providers (**OpenAlex**, **Semantic Scholar**, **CrossRef**, **PubMed**, **Google Scholar**) or running `--provider all` to query the four open-API providers simultaneously with automated DOI and fuzzy title ($\ge 0.92$) deduplication.

### 🌐 Google Scholar CAPTCHA Bridge
- **Windows PoP**: Prompts manual browser popups or proxy configurations when blocked.
- **`pop-linux`**: Uses a Playwright Chromium browser bridge that launches on HTTP 429/challenge blocks, lets you solve the challenge interactively, and saves session cookies (`~/.config/pop_linux/cookies.json`) for later reuse.

### 🕒 Citation History & Growth Trajectory Tracking (`pop-linux` Superiority)
- **Windows PoP**: Requires manually saving and managing `.pop` query files.
- **`pop-linux`**: Features a native SQLite database (`history.sqlite3`) that auto-logs search runs. Includes `pop-linux history` and `pop-linux diff <snap1> <snap2>` to track citation growth deltas and new paper discoveries between any two search snapshots over time.

### 🎯 Search Filters & Profiles
Filter queries by `--author`, `--journal`, `--issn`, `--year-from`, `--year-to`, `--min-citations`, and harvest Google Scholar user profiles directly with `--profile <user_id>`.

### Interpretation notes

- Bibliometric values are calculated from the records actually returned after the active limit and filters. A limited topic search should not be interpreted as a complete author- or database-level bibliometric record.
- `--provider all` searches OpenAlex, Semantic Scholar, CrossRef, and PubMed concurrently. Google Scholar is excluded from this mode because it may require interactive browser handling.
- When duplicate records from different providers are merged, the current implementation keeps the highest observed citation count. Multi-provider metrics therefore describe the merged dataset rather than one provider's citation index.
- Provider filter semantics differ. CrossRef and PubMed support structured ISSN handling; OpenAlex uses its API filter; Semantic Scholar includes ISSN as a query hint; Google Scholar does not have an ISSN path in this implementation.

---

## 🙏 Credits & Acknowledgments

- **Original Concept & Metrics**: Deep gratitude and credit go to **Professor Anne-Wil Harzing** ([harzing.com](https://www.harzing.com)), who invented the original *Publish or Perish* software and authored foundational research on citation analysis and bibliometric indices.
- *Disclaimer*: `pop-linux` is an independent open-source project created for Linux users and is not officially affiliated with or endorsed by Professor Anne-Wil Harzing or Harzing.com.

---

## ✨ Features

- 🔍 **Multi-Provider Academic Search**: Harvest metadata from OpenAlex (250M+ works), Semantic Scholar, CrossRef, PubMed, and Google Scholar.
- 🎯 **Advanced Query Targeting**: Filter queries by `--author`, `--journal`, `--issn`, `--year-from`, `--year-to`, and `--min-citations`. Filter precision varies by provider; Semantic Scholar treats ISSN as a query hint and Google Scholar does not use the ISSN option.
- 📊 **Complete Harzing Bibliometrics Suite**:
  - **Standard Metrics**: Total Papers, Total Citations, Average Citations/Paper, Citations/Author, Papers/Author.
  - **Impact Indices**: $h$-index, $g$-index, $e$-index (excess citations), $hI_{\text{annual}}$ (individual annual h-index), $i10$-index.
  - **Normalized & Age-Weighted Indices**: $hL_{\text{norm}}$ (author-count normalized $h$-index), $\text{AWCR}$ (Age-Weighted Citation Rate), and $\text{AW-index}$.
  - **H-Core Subsets**: Filter the Rich terminal table to only show $h$-core papers with `--show-h-core`.
- 🔀 **Multi-Provider Deduplication**: Merge results from multiple databases using `--provider all` or run `pop-linux merge file1.json file2.json`.
- 👤 **Google Scholar Profile Harvesting**: Harvest publications directly from Google Scholar profile IDs using `--profile <id>`, bounded by the active `--limit`/default limit.
- 🌐 **Playwright CAPTCHA Bridge**: Interactive Chromium fallback lets you solve Google Scholar challenges and saves session cookies for later reuse.
- 🕒 **SQLite Search History & Citation Diffing**: Automatically logs searches to `~/.config/pop_linux/history.sqlite3`. Compare growth deltas between search snapshots with `pop-linux diff <snap1> <snap2>`.
- 📤 **Multi-Format Exporters**: Export search results to BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), and RIS (`.ris`).

---

## 🛠️ Requirements

- **Linux** (any modern distro). The Google Scholar CAPTCHA bridge additionally
  requires a graphical session (it opens a real browser window only when blocked).
- **Python 3.11 or newer** (`python3 --version`).
- **pip / venv** (standard on Debian/Ubuntu via the `python3-venv` and
  `python3-pip` packages).
- **~20 MB free disk space** plus the optional Playwright Chromium download
  (~150 MB) if you want automated Google Scholar CAPTCHA solving.
- No database server needed — search history is stored in a local SQLite file.

## 🛠️ Installation

```bash
git clone https://github.com/munir-abbasi/pop-linux.git
cd pop-linux

# Create virtual environment and install pop-linux
python3 -m venv venv
source venv/bin/activate
pip install -e .

# (Optional) Install Playwright Chromium for Google Scholar CAPTCHA solving
playwright install chromium
```

> **💡 Tip:** `pip install -e .` is the editable/development install. For a
> plain (non-editable) install, run `pip install .` instead — the `pop-linux`
> command is registered either way.

### Verify the install

```bash
pop-linux --help
pop-linux providers
```

## 🔑 API Keys & Provider Registration

`pop-linux` works out of the box **with no API keys**. Adding free API keys for
Semantic Scholar and NCBI/PubMed lifts their rate limits and is
recommended for anything beyond occasional search runs. Keys are stored in
`~/.config/pop_linux/config.toml` (auto-created with owner-only permissions) and
are **masked in `pop-linux config --show` output** and never logged.

Set a key with:

```bash
pop-linux config --set api_keys.semanticscholar --value "YOUR_KEY_HERE"
pop-linux config --set api_keys.ncbi --value "YOUR_KEY_HERE"
```

### Configure your contact email (recommended)

Set `polite_email` to **your own** email address. It is sent in the
`User-Agent` header to the API providers (OpenAlex, Semantic Scholar, CrossRef,
NCBI) as polite-pool identification, so providers can reach you about rate
limits or API changes:

```bash
pop-linux config --set polite_email --value "you@example.com"
```

`polite_email` ships **unset** (empty) by default — this has no functional
impact on search results. However, popular usage of the APIs expects a contact
email, and failing to provide one may subject you to stricter throttling by
some providers. You must configure it yourself before heavy use.

> **🔒 Security note:** `config.toml` is written with `0600` permissions and the
> config directory with `0700`. Never commit your `config.toml` or share your
> keys — `pop-linux` asks you to supply keys only via the local config file.

### Provider-by-provider registration steps

| Provider | Required? | How to register | What a key gets you |
|---|---|---|---|
| **OpenAlex** | Keyless works for casual use | Create a free account at [openalex.org](https://openalex.org) and copy your key from [openalex.org/settings/api](https://openalex.org/settings/api) | 10× the keyless daily budget (keyless budget is fine for demos/testing only) |
| **Semantic Scholar** | No | Request a free key via the [Semantic Scholar API product page](https://www.semanticscholar.org/product/api) ("Request an API key" form) — the key is sent to you by email | 1 request/second dedicated rate (keyless shares a global throttled pool) |
| **NCBI / PubMed** | No | Create an [NCBI account](https://www.ncbi.nlm.nih.gov/account/), open **Account settings → API Key Management**, click **Create an API Key**, copy it | E-utilities rate limit raised from 3 to 10 requests/second |
| **CrossRef** | No | No key exists — just use it | — (polite `mailto`/User-Agent identification) |
| **Google Scholar** | No | No API key exists — the scraper persists a session cookie file (`~/.config/pop_linux/cookies.json`) after you solve a CAPTCHA once | Persistent session that avoids re-solving CAPTCHAs |

> **⚠️ OpenAlex note (Feb 2026 change):** OpenAlex retired its "polite pool"
> (`mailto=` requests are now ignored) and moved to **free API keys** required
> for real-scale use. This release queries OpenAlex keyless (suited to casual /
> test use); configuring an OpenAlex API key in `pop-linux` is on the roadmap.

---

## 💻 Usage & Examples

### 1. Basic Academic Search
Harvest papers using default fast open provider (OpenAlex):
```bash
pop-linux search "respiratory infections" --limit 20
```

### 2. Search Filters & Specific Provider
```bash
pop-linux search "asthma management" --provider semanticscholar --author "Smith" --year-from 2018 --min-citations 10 --export asthma.bib
```

### 3. Multi-Provider Concurrent Harvest & Deduplication
Search across OpenAlex, Semantic Scholar, CrossRef, and PubMed concurrently with automated record deduplication:
```bash
pop-linux search "pulmonary rehabilitation" --provider all --limit 50 --export combined.json
```

### 4. Display $h$-Core Paper Subsets
```bash
pop-linux search "chronic obstructive pulmonary disease" --show-h-core
```

### 5. Google Scholar Profile Harvesting
Harvest publications directly from a researcher's Google Scholar profile:
```bash
pop-linux search "" --profile "u123456789" --export profile.bib
```

### 6. Google Scholar Search with Playwright CAPTCHA Solver
```bash
pop-linux search "machine learning in healthcare" --provider google_scholar --limit 20
```

> **⚠️ Legal / ToS notice:** the `google_scholar` provider scrapes the Google Scholar
> public website and its CAPTCHA bridge automates past Google's challenge. This
> conflicts with Google's Terms of Service, may violate the operator's fair-use
> expectations, and can result in your IP being temporarily blocked. Use it at
> your own risk; prefer `--provider all` (OpenAlex / Semantic Scholar / CrossRef /
> PubMed) which use sanctioned APIs for bulk harvesting.

> **🔒 Privacy note:** search queries and harvested paper metadata are persisted in
> plaintext to the local SQLite history database (`~/.config/pop_linux/history.sqlite3`,
> permissions 0600). Search topics can be sensitive (e.g. health-related queries);
> the file, its backups, and the plaintext API keys in `config.toml` should be
> protected like credentials.

### 7. Search Snapshot History, Rerun & Citation Growth Diffing
```bash
# List past search snapshots
pop-linux history

# Compare citation growth and metric trajectory between snapshot #1 and snapshot #2
pop-linux diff 1 2

# Re-execute a saved search exactly as it ran (same resolved request, same provider set)
pop-linux rerun 42

# Machine-readable rerun: prints the same JSON execution envelope as `--machine search`
pop-linux --machine rerun 42
```

**History storage (schema v2):** every search snapshot stores its resolved request, per-provider
reports, provenance, metrics context, and rerun lineage alongside the classic result payload.
Legacy v1 databases are migrated automatically on first use, with a versioned backup
(`history.sqlite3.bak-<timestamp>`) written first; if migration fails, the original database is
left untouched and usable. A history-write failure never masks a successful search: the CLI
warns and continues, and the `--no-history` flag skips persistence entirely.

### 8. Merge Saved Results
```bash
pop-linux merge results1.json results2.json --export merged_library.bib
```

### 9. View Configuration & Providers
```bash
pop-linux providers
pop-linux capabilities
pop-linux config --show
pop-linux config --set default_provider --value semanticscholar
```

### 10. Recompute Metrics for a Saved Result
```bash
pop-linux metrics /tmp/results.json
```

---

## 🤖 AI Agent & MCP Integration Guide (Claude Code, OpenCode, Cursor)

`pop-linux` is CLI-first and Python-native. It ships a dedicated machine execution profile for agents: `--machine` prints exactly one versioned JSON execution envelope to stdout, never opens a browser, and never writes history unless explicitly requested.

### 0. Machine Mode (recommended for agents)

```bash
# Step 0: discover providers, filter modes, pagination, and local readiness
# (no network calls; parse one JSON document):
pop-linux --machine capabilities

# Then execute and parse one JSON document:
pop-linux --machine search "asthma" --provider all --limit 20
```

Contract:

- stdout carries exactly one JSON document with `schema: "pop-linux.execution/v1"`; pass it straight to `json.loads()` with no preprocessing.
- Status is one of `success`, `partial`, `empty` (exit code 0) or `error` (exit code 1). Provider-level failures appear as structured entries in `provider_reports` (status plus classified, retryable error codes), never as terminal prose.
- `google_scholar` and `--profile` are refused with an `INTERACTION_FORBIDDEN` error rather than risking an unexpected Chromium launch.
- No history snapshot is written unless `--save-history` is passed; `persistence` in the envelope reports every side effect (snapshot id, exported files, structured `EXPORT_FAILED`/`HISTORY_WRITE_FAILED` errors).
- `--export` remains a scholarly-data projection (BibTeX/CSV/JSON/RIS) and is independent of machine stdout.
- Every provider report includes `pages_or_requests` (retrieval scope) and `filter_modes` describing how each requested filter was enforced (`native`, `query_hint`, `post_filter`, or `unsupported` with a structured `FILTER_UNSUPPORTED` warning); requests that exceed one page are paginated up to the requested limit with safety guards (OpenAlex/CrossRef cursor paging, PubMed `retstart`, Semantic Scholar `offset`/`next`).

The human examples below remain fully supported.

### 1. Direct Bash Execution (Claude Code CLI / OpenCode / Cursor Agent)
Any AI agent with terminal execution capabilities can run `pop-linux` directly and parse structured JSON outputs:

```bash
# Harvest multi-source deduplicated papers to structured JSON
pop-linux search "pulmonary rehabilitation COPD" --provider all --limit 30 --export /tmp/results.json

# Read bibliometrics metrics dictionary
jq '.metrics' /tmp/results.json
```

### 2. Python Package / Direct Library Import
AI agents building custom scripts or web applications can import `pop-linux` modules directly without subprocesses:

```python
import asyncio
from pop_linux.providers import get_provider
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.metrics import calculate_metrics

async def main():
    openalex = get_provider("openalex")
    semanticscholar = get_provider("semanticscholar")

    res1, res2 = await asyncio.gather(
        openalex.search("asthma exacerbations", limit=20),
        semanticscholar.search("asthma exacerbations", limit=20)
    )

    combined = deduplicate_papers(res1.papers + res2.papers)
    metrics = calculate_metrics(combined)
    print(f"Combined h-index: {metrics.h_index}, Total Citations: {metrics.total_citations}")

asyncio.run(main())
```

### 3. OpenCode / Claude Code Custom Agent Skill Integration
Create an Agent Skill file (e.g., `.opencode/skills/pop-linux.md` or `~/.claude/commands/academic_search.md`):

```markdown
---
name: academic-search
description: Search academic literature across OpenAlex, Semantic Scholar, CrossRef, PubMed & compute Harzing bibliometrics using pop-linux.
---

When the user asks to find papers or check citation metrics:
1. Run: `pop-linux search "<query>" --provider all --limit 30 --export results.json`
2. Parse `results.json` to extract top cited papers and Harzing metrics ($h$-index, $g$-index, $\text{AWCR}$).
3. Present Vancouver-formatted citations to the user.
```

---

## 📋 Search Provider Summary

| Provider Key | Search Type | API Key Required? | Description & Capabilities |
|---|---|---|---|
| `openalex` | REST API (Default) | Keyless OK for casual use; free key lifts 10× daily budget | Fast, 250M+ items, structured inverted-index abstract reconstruction. See the API-keys note above. |
| `semanticscholar` | REST API | Optional | Semantic Scholar Graph API with citations, venues, & abstracts; dedicated 1 RPS with a key |
| `crossref` | REST API | No | DOI lookups, publisher metadata, citation count sorting |
| `pubmed` | REST API | Optional | NCBI Entrez biomedical & life sciences literature; 3→10 RPS with a key |
| `google_scholar` | Scraper / Playwright | No | Native HTML parser with Playwright cookie bridge for CAPTCHAs |
| `all` | Multi-Source API | No | Concurrent multi-provider search with automated DOI & title deduplication |

---

## 👤 Author

**Munir Abbasi**
- **GitHub**: [github.com/munir-abbasi](https://github.com/munir-abbasi/)
- **Website**: [syntaxhouse.com](https://syntaxhouse.com)

---

## 📄 License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

- **Allowed**: any *noncommercial* use — personal research, study, hobby,
  educational institutions, charities, public health, and government use.
- **Requires permission**: *commercial* use. If you want to use `pop-linux` for
  any commercial purpose, contact the author for a commercial license.

See [LICENSE](LICENSE) for the full terms.
