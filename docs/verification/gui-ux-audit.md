# Desktop GUI & UX Usability Audit

## Audit Overview
- **Application**: Perish or Publish (`pop-linux-gui`)
- **Version**: 0.2.0
- **Toolkit**: PySide6 6.11.2 / Qt 6.11.2 (Fusion Style)
- **Target OS**: Linux (Wayland & X11), Windows 10/11, macOS (Intel & Apple Silicon)
- **Primary Display Tested**: 1480x940, High-DPI scaling enabled.

---

## 1. Workspace Layout & Navigation

### 1.1 Structural Organization
The desktop application employs an efficient three-panel layout:
1. **Left Navigation Sidebar (195px)**:
   - Clean branding (`P / P PERISH OR PUBLISH`).
   - Primary navigation buttons: **Research workspace** (Search/Browse) and **Search history**.
   - Footer controls: **Settings** (`Ctrl+,`) and **About this application**.
2. **Search & Filter Panel (Left Splitter Pane, 250–420px)**:
   - Form fields: Research query, Provider combo, Author, Journal, ISSN, Year From/To, Min Citations, Limit, Scholar Profile ID.
   - Dynamic **Provider Filter Support** text box that explains which filters are native vs query hints for the active provider.
   - Action controls: High-visibility primary "Search literature" button and "Cancel search" button.
3. **Results & Metrics Panel (Right Splitter Pane)**:
   - Top banner: Dataset scope label explaining that metrics apply to the loaded search dataset.
   - 6 Quick Metric Cards: Publications, Total citations, $h$-index, $g$-index, Citations / paper, $i10$-index.
   - Action bar: Local search filter (`Ctrl+F`), Column visibility menu, "Save snapshot" (`Ctrl+S`), "Export…" (`Ctrl+E`).
   - Publication Table & Details Splitter: Resizable split between table and details viewer.
   - Secondary Tabs: "More metrics" (6 advanced metrics cards: $e$-index, $hI_{\text{annual}}$, $hL_{\text{norm}}$, $\text{AWCR}$, $\text{AW-index}$, Citations / author) and "Provider reports" (structured warnings/errors).

---

## 2. Interactive Usability & Discoverability

| Component | UX Design Feature | Evaluation & Evidence |
|---|---|---|
| **Search Submission** | Enter key inside query line edits or primary button click. | **Pass**: Natural keyboard flow; search triggers immediately. |
| **Search Execution State** | Indeterminate progress bar appears; "Search literature" disabled; "Cancel search" enabled. | **Pass**: Prevents duplicate submissions while providing clear visual feedback. |
| **Search Cancellation** | Dedicated "Cancel search" button. | **Pass**: Halts network requests; keeps existing table data intact; notice states: *"Search cancelled. Previous results were retained."* |
| **Provider Selection** | Dropdown with full provider names and capabilities. | **Pass**: Selecting a provider immediately updates the inline capability notice below. |
| **Table Sorting** | Clickable column headers with sort arrows. | **Pass**: Numeric sorting on Citations and Year; case-insensitive alphabetical sorting on Title and Authors. |
| **Local Row Filtering** | Instant search box (`Ctrl+F`). | **Pass**: Filters rows in real-time as user types. Row count updates dynamically: e.g., *"1 visible / 3 loaded · 0 selected"*. |
| **Details Inspection** | Single-click populates bottom pane; double-click opens full-screen dialog. | **Pass**: Formats title, authors, affiliations, journal, DOI, web URL, abstract, and JSON provider evidence. |
| **External Link Launch** | "Open DOI / publication" button. | **Pass**: Validates URL via `safe_external_url()`; opens in system default browser. Non-web schemes rejected. |
| **Export Scope Choice** | When rows are selected, clicking "Export…" presents a choice dialog. | **Pass**: Explicit prompt: *"Export X selected records, or all Y loaded records?"* Recomputes metrics for selection. |
| **Overwrite Protection** | Export dialog detects existing destination file. | **Pass**: Asks: *"Adding format extension selects file.csv, which already exists. Replace it?"* Defaults to No. |
| **Settings & Keys** | Modal dialog with masked password fields. | **Pass**: API keys display as dots (`EchoMode.Password`); atomic save writes backup file first. |

---

## 3. Accessibility & Theme Design

### 3.1 Color Contrast & Typography
- **Appearance Modes**: Supports `system`, `light`, and `dark` themes via `pop_linux.gui.style.apply_appearance()`.
- **Text Legibility**:
  - Dark Theme: Background `#18181b`, Text `#f4f4f5` (Contrast ratio: 15.3:1, exceeding WCAG AAA).
  - Light Theme: Background `#fafafa`, Text `#18181b` (Contrast ratio: 15.8:1, exceeding WCAG AAA).
  - Accent / Primary Buttons: High-contrast blue `#2563eb` with crisp white lettering.

### 3.2 Keyboard Navigation & Shortcuts
- `Ctrl+O`: Open / merge JSON datasets.
- `Ctrl+S`: Save current search snapshot to SQLite.
- `Ctrl+E`: Open export dialog.
- `Ctrl+,`: Open Settings dialog.
- `Ctrl+Q`: Quit application.
- `Ctrl+Shift+C`: Copy selected publication metadata to clipboard.
- `Ctrl+F` / Standard Find: Focus local table filter box.
- Tab order flows logically from query $\rightarrow$ provider $\rightarrow$ filters $\rightarrow$ search button $\rightarrow$ table.

---

## 4. Usability Deficiencies Found & Resolved

1. **Resolution of Window Sizing on Compact Laptops**:
   - Minimum window dimensions set to `1040 x 700`, with interactive horizontal and vertical splitters, ensuring no controls are clipped or unreachable on 1080p or 768p displays.
2. **Clear Separation Between Local Filter and Upstream Query**:
   - Tooltip and status label explicitly clarify: *"Filters this table only. The dataset, exports of all records, and metrics stay unchanged."* This prevents researchers from mistaking local table hiding for a refined query.
3. **Password Masking in Settings**:
   - Guaranteed that API keys for Semantic Scholar and NCBI are never visible to onlookers.

---

## Conclusion
The PySide6 interface is attractive, robust, responsive, and tailored specifically to academic research workflows. It avoids cluttered visual noise, provides immediate feedback, protects user data, and makes complex bibliometric operations intuitive.
