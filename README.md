# Perish or Publish (`pop-linux`)

`pop-linux` is an independent, native academic literature search and bibliometric analysis suite for Linux, Windows, and macOS. It provides multi-source paper harvesting, Harzing bibliometric calculations ($h$, $g$, $e$, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$), automated DOI and fuzzy-title deduplication, SQLite citation trajectory diffing, a Playwright browser bridge for Google Scholar challenge handling, an optional PySide6 desktop workspace, and a deterministic machine execution envelope (`pop-linux.execution/v1`) for AI agents.

Both the PySide6 desktop GUI and the Python CLI are verified, tested, and distributed as standalone, cross-platform packages that require no Python environment or technical configuration.

---

## Key Capabilities Verified for Scholarly Research

| Researcher Need | How pop-linux Fulfills It | Verification Status |
| :--- | :--- | :--- |
| **Broad Literature Search** | Concurrent queries across OpenAlex, Semantic Scholar, CrossRef, PubMed, and Google Scholar. | Verified — full multi-provider coverage and query forms active. |
| **Bibliometric Analysis** | Calculates Harzing's classic metrics: $h$-index, $g$-index, $e$-index, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$, and annual citation rates. | Verified — exact mathematical parity with Harzing definitions validated by automated tests. |
| **De-duplication** | Merges duplicate records from multiple databases using strict normalized DOI matching and high-confidence title similarity, combining citation counts accurately. | Verified — preserves distinct DOIs; prevents false merges. |
| **Reference Manager Integration** | Direct export of all or selected papers to BibTeX, RIS (Zotero, Mendeley, EndNote), CSV (Excel/R), and JSON. | Verified — CSV formula injection protection active; BibTeX/RIS formatting valid. |
| **Research Tracking & Velocity** | Snapshots search queries locally to a secure SQLite database (`~/.config/pop_linux/history.sqlite3`), allowing researchers to rerun searches and diff citation growth over time. | Verified — schema migrations tested, query lineage preserved. |
| **Privacy & Security** | Local-first: no third-party telemetry, tracking, or cloud servers. All search history and API keys stay on the researcher's local machine with strict permissions (`0600`/`0700`). | Verified — Bandit static security analysis clean; masked API credentials. |

---

## Where Researchers Can Get It

The release is live on GitHub: **[Release v0.2.0](https://github.com/munir-abbasi/pop-linux/releases/tag/v0.2.0)**

| Platform | Architecture | Package | How to Run |
| :--- | :--- | :--- | :--- |
| **Linux** | `x86_64` | AppImage | `chmod +x pop-linux-0.2.0-x86_64.AppImage && ./pop-linux-0.2.0-x86_64.AppImage`<br>*(No FUSE: `APPIMAGE_EXTRACT_AND_RUN=1 ./pop-linux-0.2.0-x86_64.AppImage`)* |
| **Linux** | `x86_64` | `.deb` (Debian/Ubuntu) | `sudo dpkg -i pop-linux_0.2.0_amd64.deb` |
| **Linux** | `x86_64` | `.rpm` (Fedora/RHEL) | `sudo rpm -i pop-linux-0.2.0-1.x86_64.rpm` |
| **Windows** | `x64` | `.zip` | Extract zip, double-click `PerishOrPublish.exe` |
| **macOS** | Apple Silicon (`arm64`) | `.zip` | Extract zip, open `PerishOrPublish.app` |
| **macOS** | Intel (`x86_64`) | `.zip` | Extract zip, open `PerishOrPublish.app` |
| **Python Developers** | Any | Source package / wheel | `pip install 'pop-linux[desktop]'` |

Every release includes cryptographic checksums in `SHA256SUMS`.

### Practical Operating Notes for Researchers

1. **First-Launch OS Warnings (Standard for Independent Open Source):**
   - **Windows:** SmartScreen will display an "Unknown Publisher" warning. Click **More info** → **Run anyway**.
   - **macOS:** Gatekeeper may block launch on first double-click. **Right-click (Control-click)** the app → select **Open** → click **Open**.
2. **API Keys (Optional but Recommended for Heavy Queries):**
   - The app functions immediately without any API keys.
   - For high-volume harvesting (e.g., systematic literature reviews), researchers can enter free API keys for OpenAlex, Semantic Scholar, or NCBI PubMed via the desktop Settings dialog to bypass default rate-limiting.
3. **Google Scholar Queries:**
   - Automated queries to Google Scholar may periodically prompt a CAPTCHA. If triggered, pop-linux invokes a local browser window allowing the user to solve the verification once, after which cookies are cached locally for subsequent queries.

---

## Python Package Installation

If you prefer running `pop-linux` as a Python CLI or building the desktop UI from source:

### Requirements
- Python 3.11 or newer (`python3 --version`).
- Linux, macOS, or Windows.
- SQLite3 (included in Python standard library).

```bash
git clone https://github.com/munir-abbasi/pop-linux.git
cd pop-linux

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install CLI only:
pip install -e .

# Or install with the PySide6 Desktop GUI:
pip install -e '.[desktop]'

# (Optional) Install Playwright Chromium for Google Scholar CAPTCHA solving:
playwright install chromium
```

### Quick Start
```bash
# Launch the PySide6 Desktop GUI:
pop-linux-gui
# Or directly:
python -m pop_linux.gui

# Verify the CLI:
pop-linux --help
pop-linux providers
```

See the [desktop guide](docs/desktop.md) and [release candidate documentation](docs/release-0.2.0.md) for full interface details.

---

## Comparison with Original Software

The original **Publish or Perish** desktop software was created by **Professor Anne-Wil Harzing** ([harzing.com](https://www.harzing.com)) and has long been the gold standard for citation analysis. `pop-linux` was created to give Linux and cross-platform researchers an open, scriptable, native environment without emulation layers (Wine/Proton/VMs), while adding multi-provider concurrency, SQLite persistence, and machine-readable execution.

| Feature Dimension | Original Desktop Software (Harzing PoP) | `pop-linux` Suite |
|---|---|---|
| **Target Platform** | Microsoft Windows GUI & macOS (via Wine) | Native Linux, Windows, macOS (CLI + PySide6 Desktop) |
| **Interface & Workflow** | Interactive Windows GUI | PySide6 Desktop GUI + Typer/Rich CLI + Machine JSON |
| **Supported Data Sources** | Google Scholar, GS Profiles, OpenAlex, Crossref, PubMed, Semantic Scholar, Scopus* | OpenAlex (Default), Semantic Scholar, CrossRef, PubMed, Google Scholar, GS Profiles, plus `--provider all` |
| **Multi-Provider Search** | Single provider per query | `--provider all` parallel harvesting with automated DOI & title deduplication |
| **Google Scholar Challenge Handling** | Manual browser popup / proxy configuration | Embedded Playwright Chromium bridge saving session cookies (`cookies.json`) |
| **Bibliometrics Suite** | Standard Harzing metrics ($h$, $g$, $e$, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, $i10$) | Implements identical Harzing metric formulas over dataset + `--show-h-core` filter |
| **Search History & Trajectory** | Saved search files (`.pop` / XML) | Native SQLite database (`history.sqlite3`) with `history`, `diff`, and `rerun` |
| **Automation & Agent Support** | GUI only | `--machine` versioned JSON envelope (`pop-linux.execution/v1`) |
| **Export Formats** | CSV, EndNote, PDF, BibTeX | BibTeX (`.bib`), CSV (`.csv`), JSON (`.json`), RIS (`.ris`) |

*Disclaimer: `pop-linux` is an independent open-source project and is not officially affiliated with or endorsed by Professor Anne-Wil Harzing or Harzing.com.*

---

## Core Capabilities

### 1. Multi-Provider Harvesting & Concurrency
- Query individual scholarly providers (**OpenAlex**, **Semantic Scholar**, **CrossRef**, **PubMed**, **Google Scholar**) or run `--provider all` to query the four open REST providers concurrently.
- Fault-tolerant retrieval: failed providers emit non-fatal diagnostic reports while successful providers merge and display results.
- Bounded pagination with provider-specific cursor and offset handling up to the requested `--limit`.

### 2. Publication Identity & Deduplication
- Strict DOI precedence: identical DOIs merge automatically; differing non-empty DOIs are never merged.
- Title fuzzy matching ($\ge 0.92$) when DOIs are absent or matching and publication years align.
- Composite metadata merging retains maximum observed citation counts, richer author lists, abstracts, and per-provider provenance.

### 3. Complete Harzing Bibliometrics Suite
Metrics are calculated over the returned or filtered publication list:
- **Impact Indices**: $h$-index, $g$-index, $e$-index (excess citations), $hI_{\text{annual}}$ (individual annual h-index), $i10$-index.
- **Normalized & Age-Weighted Indices**: $hL_{\text{norm}}$ (author-count normalized $h$-index), $\text{AWCR}$ (Age-Weighted Citation Rate), and $\text{AW-index}$.
- **Summary Statistics**: Total papers, total citations, citations per paper, citations per author, papers per author, citations per year.
- **H-Core Isolation**: `--show-h-core` isolates and displays the $h$-core publication subset.

### 4. Search Snapshot History, Rerun & Citation Growth Diffing
- Every search result is automatically saved to local SQLite (`~/.config/pop_linux/history.sqlite3`).
- `pop-linux history`: Inspect past searches and snapshot IDs.
- `pop-linux diff <snap1> <snap2>`: Track citation growth deltas and new paper discoveries between any two snapshots over time.
- `pop-linux rerun <snap_id>`: Re-execute a saved search with identical parameters.

### 5. Playwright CAPTCHA Bridge
- If Google Scholar returns HTTP 429 or a CAPTCHA challenge, `pop-linux` launches an interactive Chromium session.
- Once solved, session cookies are saved to `~/.config/pop_linux/cookies.json` (`0600`) for subsequent requests.

---

## API Keys & Provider Setup

`pop-linux` works out of the box **with no API keys**. Adding free API keys lifts rate limits for heavy usage. Keys are stored in `~/.config/pop_linux/config.toml` (`0600`), masked in CLI display, and never printed in logs or envelopes.

```bash
# Configure API keys:
pop-linux config --set api_keys.semanticscholar --value "YOUR_KEY_HERE"
pop-linux config --set api_keys.ncbi --value "YOUR_KEY_HERE"

# Configure polite identification email (sent in User-Agent):
pop-linux config --set polite_email --value "you@example.com"
```

| Provider | Key Required? | How to Register | Advantage with Key |
|---|---|---|---|
| **OpenAlex** | Keyless OK for casual use | Free at [openalex.org/settings/api](https://openalex.org/settings/api) | 10× daily request budget |
| **Semantic Scholar** | Optional | Free at [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api) | Dedicated 1 request/sec (keyless shares pooled rate) |
| **NCBI / PubMed** | Optional | Free at [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) | Rate limit raised from 3 to 10 requests/sec |
| **CrossRef** | No key needed | Automatic via `polite_email` header | Access to polite pool |
| **Google Scholar** | No key exists | Scraper with Playwright cookie bridge | Persistent session via `cookies.json` |

---

## CLI Usage Examples

### 1. Basic Academic Search
```bash
pop-linux search "respiratory infections" --limit 20
```

### 2. Provider Selection & Structured Filters
```bash
pop-linux search "asthma management" --provider semanticscholar --author "Smith" --year-from 2018 --min-citations 10 --export asthma.bib
```

### 3. Multi-Provider Concurrent Harvest & Deduplication
```bash
pop-linux search "pulmonary rehabilitation" --provider all --limit 50 --export combined.json
```

### 4. Display $h$-Core Paper Subsets
```bash
pop-linux search "chronic obstructive pulmonary disease" --show-h-core
```

### 5. Google Scholar Profile Harvesting
```bash
pop-linux search "" --profile "u123456789" --export profile.bib
```

### 6. Interactive Google Scholar Search
```bash
pop-linux search "machine learning in healthcare" --provider google_scholar --limit 20
```

### 7. Search Snapshot History, Rerun & Citation Diffing
```bash
# List past search snapshots
pop-linux history

# Compare citation growth between snapshot #1 and snapshot #2
pop-linux diff 1 2

# Re-execute a saved search snapshot
pop-linux rerun 42
```

### 8. Merge Saved JSON Result Files
```bash
pop-linux merge results1.json results2.json --export merged_library.bib
```

### 9. View Configuration & Capabilities
```bash
pop-linux providers
pop-linux capabilities
pop-linux config --show
```

### 10. Recompute Metrics for Stored Datasets
```bash
pop-linux metrics /tmp/results.json
```

---

## AI Agent & Automation Integration

`pop-linux` ships a dedicated machine execution mode designed for AI agents (Claude Code, OpenCode, Cursor, Codex). Passing `--machine` guarantees:
- Exactly one versioned JSON envelope (`schema: "pop-linux.execution/v1"`) output to stdout.
- Exit code 0 for `success`, `partial`, and `empty`; exit code 1 for `error`.
- Refusal of interactive flows (`INTERACTION_FORBIDDEN` on Google Scholar / profile queries) to prevent unexpected browser popups.
- No implicit history writes unless `--save-history` is provided.

```bash
# Discover capabilities and local readiness (zero network calls):
pop-linux --machine capabilities

# Execute structured search:
pop-linux --machine search "asthma" --provider all --limit 20
```

### Direct Library Import
AI agents and Python pipelines can also import core modules directly:

```python
import asyncio
from pop_linux.providers import get_provider
from pop_linux.utils.deduplicator import deduplicate_papers
from pop_linux.utils.metrics import calculate_metrics

async def main():
    openalex = get_provider("openalex")
    semanticscholar = get_provider("semanticscholar")

    res1, res2 = await asyncio.gather(
        openalex.search("quantum computing", limit=20),
        semanticscholar.search("quantum computing", limit=20)
    )

    combined = deduplicate_papers(res1.papers + res2.papers)
    metrics = calculate_metrics(combined)
    print(f"Combined h-index: {metrics.h_index}, Citations: {metrics.total_citations}")

asyncio.run(main())
```

---

## Author & License

**Author:** Munir Abbasi  
- GitHub: [github.com/munir-abbasi](https://github.com/munir-abbasi/)  
- Website: [syntaxhouse.com](https://syntaxhouse.com)

**License:** This project is licensed under the **PolyForm Noncommercial License 1.0.0**.
- **Permitted**: Any noncommercial use (academic research, personal study, education, public health, non-profit institutions).
- **Commercial Use**: Requires a separate commercial license from the author.
- Bundled third-party dependencies (such as Qt/PySide6) are subject to their respective licenses (LGPL-3.0, Apache-2.0, BSD-3-Clause); see [`packaging/THIRD_PARTY_NOTICES.md`](packaging/THIRD_PARTY_NOTICES.md).
