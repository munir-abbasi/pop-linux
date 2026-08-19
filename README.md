# Perish or Publish Linux (`pop-linux`)

`pop-linux` (**Perish or Publish Linux**) is a native, lightweight, production-hardened Python CLI application for Linux. It provides multi-source academic paper harvesting, comprehensive Harzing bibliometric index calculations ($h$, $g$, $e$, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$), multi-provider data deduplication, SQLite search snapshot tracking, and Playwright-powered Google Scholar CAPTCHA solving.

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
| **Interface & Workflow** | Interactive Desktop GUI | Rich Terminal UI (TUI) + Headless / Scriptable CLI |
| **Supported Data Sources** | Google Scholar, GS Profiles, OpenAlex, Crossref, PubMed, Semantic Scholar, Scopus*, Web of Science* (*Subscription/Key required) | OpenAlex (Default), Semantic Scholar, Crossref, PubMed, Google Scholar, Google Scholar Profiles, plus `--provider all` multi-source search |
| **Google Scholar CAPTCHA Bridge** | Manual browser popup / proxy configuration when blocked | Automated Playwright Chromium browser bridge that pops up when blocked, allows interactive CAPTCHA solving, and saves session cookies (`~/.config/pop_linux/cookies.json`) for automatic reuse |
| **Multi-Provider Search** | Single-provider queries (manual inspection per database) | `--provider all` parallel multi-source harvesting with automated DOI & fuzzy title ($\ge 0.92$) deduplication |
| **Bibliometrics Suite** | Standard Harzing metrics ($h, g, e, hI_{\text{annual}}, hL_{\text{norm}}, \text{AWCR}, \text{AW-index}, i10$) | Identical Harzing bibliometric formulas ($h, g, e, hI_{\text{annual}}, hL_{\text{norm}}, \text{AWCR}, \text{AW-index}, i10$) + `--show-h-core` CLI filter |
| **Search History & Trajectory** | Saved search files (`.pop` / XML) | Native SQLite database (`~/.config/pop_linux/history.sqlite3`) auto-saving all search snapshots with `pop-linux history` and `pop-linux diff <snap1> <snap2>` citation growth tracking |
| **File Merging** | Manual GUI row management | `pop-linux merge file1.json file2.json` CLI command |
| **Export Formats** | CSV, EndNote, PDF, BibTeX, Copy-to-clipboard | BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), RIS (`.ris`) |

---

## ⭐ Features Where `pop-linux` Has Full Parity or Superiority

> [!IMPORTANT]
> **Summary**: `pop-linux` achieves 100% mathematical parity with Harzing's bibliometric engine while adding parallel multi-provider search, automatic cookie-based CAPTCHA solving, and native SQLite citation trajectory diffing.

### 🎯 Complete Harzing Bibliometrics Engine (100% Parity)
Calculates all standard and advanced Harzing impact metrics:
- **Impact Indices**: $h$-index, $g$-index, $e$-index (excess citations), $hI_{\text{annual}}$ (individual annual h-index).
- **Normalized & Age-Weighted Indices**: $hL_{\text{norm}}$ (author-count normalized h-index), $\text{AWCR}$ (Age-Weighted Citation Rate), and $\text{AW-index}$.
- **Summary Statistics**: $i10$-index, total citations, average citations per paper, citations per author, papers per author, citations per year.
- 💡 **`pop-linux` Bonus**: Includes a `--show-h-core` CLI flag to isolate and display only the $h$-core paper subset.

### 🔀 Multi-Source Harvesting & Concurrent Search (`pop-linux` Superiority)
- **Windows PoP**: Queries one database at a time.
- **`pop-linux`**: Supports querying individual providers (**OpenAlex**, **Semantic Scholar**, **CrossRef**, **PubMed**, **Google Scholar**) or running `--provider all` to query all open databases simultaneously with automated DOI and fuzzy title ($\ge 0.92$) deduplication.

### 🌐 Google Scholar CAPTCHA Bridge (`pop-linux` Superiority)
- **Windows PoP**: Prompts manual browser popups or proxy configurations when blocked.
- **`pop-linux`**: Uses an automated Playwright Chromium browser bridge that launches on HTTP 429/CAPTCHA blocks, lets you solve the challenge interactively, and saves session cookies (`~/.config/pop_linux/cookies.json`) for automatic background reuse.

### 🕒 Citation History & Growth Trajectory Tracking (`pop-linux` Superiority)
- **Windows PoP**: Requires manually saving and managing `.pop` query files.
- **`pop-linux`**: Features a native SQLite database (`history.sqlite3`) that auto-logs search runs. Includes `pop-linux history` and `pop-linux diff <snap1> <snap2>` to track citation growth deltas and new paper discoveries between any two search snapshots over time.

### 🎯 Search Filters & Profiles
Filter queries by `--author`, `--journal`, `--issn`, `--year-from`, `--year-to`, `--min-citations`, and harvest Google Scholar user profiles directly with `--profile <user_id>`.

---

## 🙏 Credits & Acknowledgments

- **Original Concept & Metrics**: Deep gratitude and credit go to **Professor Anne-Wil Harzing** ([harzing.com](https://www.harzing.com)), who invented the original *Publish or Perish* software and authored foundational research on citation analysis and bibliometric indices.
- *Disclaimer*: `pop-linux` is an independent open-source project created for Linux users and is not officially affiliated with or endorsed by Professor Anne-Wil Harzing or Harzing.com.

---

## ✨ Features

- 🔍 **Multi-Provider Academic Search**: Harvest metadata from OpenAlex (250M+ works), Semantic Scholar, CrossRef, PubMed, and Google Scholar.
- 🎯 **Advanced Query Targeting**: Filter queries by `--author`, `--journal`, `--issn`, `--year-from`, `--year-to`, and `--min-citations`. *Note:* ISSN filtering is applied by the OpenAlex, CrossRef, and PubMed providers; Semantic Scholar and Google Scholar do not expose an ISSN field and ignore it.
- 📊 **Complete Harzing Bibliometrics Suite**:
  - **Standard Metrics**: Total Papers, Total Citations, Average Citations/Paper, Citations/Author, Papers/Author.
  - **Impact Indices**: $h$-index, $g$-index, $e$-index (excess citations), $hI_{\text{annual}}$ (individual annual h-index), $i10$-index.
  - **Normalized & Age-Weighted Indices**: $hL_{\text{norm}}$ (author-count normalized $h$-index), $\text{AWCR}$ (Age-Weighted Citation Rate), and $\text{AW-index}$.
  - **H-Core Subsets**: Filter Rich TUI table view to only show $h$-core papers with `--show-h-core`.
- 🔀 **Multi-Provider Deduplication**: Merge results from multiple databases using `--provider all` or run `pop-linux merge file1.json file2.json`.
- 👤 **Google Scholar Profile Harvesting**: Harvest full publication lists directly from Google Scholar profile IDs using `--profile <id>`.
- 🌐 **Playwright CAPTCHA Bridge**: Interactive Chromium fallback solves Google Scholar CAPTCHA challenges seamlessly and saves session cookies for background reuse.
- 🕒 **SQLite Search History & Citation Diffing**: Automatically logs searches to `~/.config/pop_linux/history.sqlite3`. Compare growth deltas between search snapshots with `pop-linux diff <snap1> <snap2>`.
- 📤 **Multi-Format Exporters**: Export search results to BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), and RIS (`.ris`).

---

## 🛠️ Installation

```bash
git clone https://github.com/munir-abbasi/pop-linux.git
cd pop-linux

# Create virtual environment and install pop-linux
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Install Playwright Chromium for Google Scholar CAPTCHA solving
playwright install chromium
```

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

### 7. Search Snapshot History & Citation Growth Diffing
```bash
# List past search snapshots
pop-linux history

# Compare citation growth and metric trajectory between snapshot #1 and snapshot #2
pop-linux diff 1 2
```

### 8. Merge Saved Results
```bash
pop-linux merge results1.json results2.json --export merged_library.bib
```

### 9. View Configuration & Providers
```bash
pop-linux providers
pop-linux config --show
pop-linux config --set default_provider --value semanticscholar
```

---

## 🤖 AI Agent & MCP Integration Guide (Claude Code, OpenCode, Cursor)

`pop-linux` was built CLI-first and Python-native, making it seamless to integrate into AI coding agents, autonomous LLM execution loops, and MCP (Model Context Protocol) setups.

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
| `openalex` | REST API (Default) | No | Fast, 250M+ items, structured inverted-index abstract reconstruction |
| `semanticscholar` | REST API | Optional | Semantic Scholar Graph API with citations, venues, & abstracts |
| `crossref` | REST API | No | DOI lookups, publisher metadata, citation count sorting |
| `pubmed` | REST API | Optional | NCBI Entrez biomedical & life sciences literature |
| `google_scholar` | Scraper / Playwright | No | Native HTML parser with Playwright cookie bridge for CAPTCHAs |
| `all` | Multi-Source API | No | Concurrent multi-provider search with automated DOI & title deduplication |

---

## 👤 Author

**Munir Abbasi**
- **GitHub**: [github.com/munir-abbasi](https://github.com/munir-abbasi/)
- **Website**: [syntaxhouse.com](https://syntaxhouse.com)

---

## 📄 License

MIT License. Developed for native Linux academic research workflows.
