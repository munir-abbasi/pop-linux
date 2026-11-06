# Scientific Correctness & Bibliometric Formula Validation

## Executive Summary
This document provides an independent mathematical and empirical audit of the scientific algorithms in `pop-linux`. Every formula was verified against primary literature definitions (Harzing 2007, Hirsch 2005, Egghe 2006, Zhang 2009) and tested against ground-truth hand-calculated reference datasets.

---

## 1. Bibliometric Formula Definitions & Implementations

### 1.1 Hirsch $h$-index
- **Definition**: A researcher has index $h$ if $h$ of their $N_p$ papers have at least $h$ citations each and the remaining $(N_p - h)$ papers have $\le h$ citations each (Hirsch, 2005).
- **Mathematical Form**:
  $$h = \max \{ i \in [1, N_p] : c_i \ge i \}$$
  where citations $c_i$ are sorted in non-increasing order: $c_1 \ge c_2 \ge \dots \ge c_{N_p}$.
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  h_index = 0
  for i, c in enumerate(sorted_citations, start=1):
      if c >= i:
          h_index = i
      else:
          break
  ```
- **Audit Findings**: Correct. Handles empty datasets ($h=0$), single publications, tied values, and zero-citation records properly.

---

### 1.2 Egghe $g$-index
- **Definition**: The highest rank $g$ such that the top $g$ papers together received at least $g^2$ citations (Egghe, 2006).
- **Mathematical Form**:
  $$g = \max \left\{ g \in [1, N_p] : \sum_{i=1}^g c_i \ge g^2 \right\}$$
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  g_index = 0
  cum_sum = 0
  for i, c in enumerate(sorted_citations, start=1):
      cum_sum += c
      if cum_sum >= i * i:
          g_index = i
  ```
- **Audit Findings**: Correct. Preserves the property $g \ge h$ and bounds $g \le N_p$.

---

### 1.3 Zhang $e$-index (Excess Citations)
- **Definition**: Measures the excess citations in the $h$-core not captured by the $h^2$ area (Zhang, 2009).
- **Mathematical Form**:
  $$e^2 = \sum_{i=1}^h (c_i - h) = \left( \sum_{i=1}^h c_i \right) - h^2 \implies e = \sqrt{\sum_{i=1}^h c_i - h^2}$$
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  e_index = 0.0
  if h_index > 0:
      h_core_citations = sorted_citations[:h_index]
      excess_citations = sum(c - h_index for c in h_core_citations)
      e_index = math.sqrt(max(0, excess_citations))
  ```
- **Audit Findings**: Correct. The formulation $\sum_{i=1}^h (c_i - h)$ is mathematically identical to $\sum_{i=1}^h c_i - h^2$. Zero excess yields $e=0.0$. Output is rounded to 2 decimal places.

---

### 1.4 Individual Annual $h$-index ($hI_{\text{annual}}$)
- **Definition**: Normalizes $h$-core citations by author counts and divides by the career or publication span (Harzing, 2007).
- **Mathematical Form**:
  $$hI_{\text{annual}} = \frac{\sum_{i=1}^h \frac{c_i}{A_i}}{\Delta Y}$$
  where $A_i$ is author count for paper $i$, and $\Delta Y = \max(1, Y_{\text{current}} - \min(Y_{\text{pub}}) + 1)$.
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  sorted_papers = sorted(papers, key=lambda p: p.citations, reverse=True)
  h_core_papers = sorted_papers[:h_index]
  norm_h_citations = sum(p.citations / p.author_count for p in h_core_papers)
  hI_annual = norm_h_citations / years_span
  ```
- **Audit Findings**: Correct. Automatically excludes placeholder publication years ($< 1800$) from distorting $\Delta Y$.

---

### 1.5 Author-Normalized $h$-index ($hL_{\text{norm}}$)
- **Definition**: The $h$-index calculated over individual normalized citation counts $c_i / A_i$ (Harzing, 2007).
- **Mathematical Form**:
  $$hL_{\text{norm}} = \max \left\{ i : \frac{c_i}{A_i} \ge i \right\}$$
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  norm_citations = sorted([p.citations / p.author_count for p in papers], reverse=True)
  hL_norm = 0.0
  for i, nc in enumerate(norm_citations, start=1):
      if nc >= i:
          hL_norm = float(i)
      else:
          break
  ```
- **Audit Findings**: Correct.

---

### 1.6 Age-Weighted Citation Rate ($\text{AWCR}$) & $\text{AW-index}$
- **Definition**: Weights each paper's citations inversely by its age in years (Harzing, 2007).
- **Mathematical Form**:
  $$\text{AWCR} = \sum_{i=1}^{N_p} \frac{c_i}{\text{Age}_i}, \quad \text{Age}_i = \max(1, Y_{\text{current}} - Y_{\text{pub}, i} + 1)$$
  $$\text{AW-index} = \sqrt{\text{AWCR}}$$
- **Implementation in `pop_linux/utils/metrics.py`**:
  ```python
  awcr = 0.0
  for p in papers:
      if p.citations > 0:
          pub_year = p.year if (p.year and p.year > 1800 and p.year <= current_year) else current_year
          age = max(1, current_year - pub_year + 1)
          awcr += p.citations / age
  aw_index = math.sqrt(awcr)
  ```
- **Audit Findings**: Correct.

---

## 2. Independent Reference Benchmark Matrix

The following reference datasets were evaluated independently and compared across:
1. **Mathematical Ground Truth** (Hand-computed)
2. **`utils.metrics.calculate_metrics()`**
3. **CLI Rich Panel Output**
4. **GUI Workspace Cards**

| Dataset Description | Ground Truth Values | CLI Output | GUI Card Output | Status |
|---|---|---|---|---|
| **Empty Dataset** ($N=0$) | $h=0, g=0, e=0.0, \text{cites}=0, i10=0$ | All 0 / None | Publications: 0, Total cites: 0, $h=0$ | **MATCH** |
| **Single Paper, 0 Cites** | $h=0, g=0, e=0.0, \text{cites}=0, i10=0$ | All 0 | Publications: 1, Total cites: 0, $h=0$ | **MATCH** |
| **Single Paper, 15 Cites** (Pub 2020, 1 author) | $h=1, g=1, e=3.74, \text{cites}=15, i10=1, \text{AWCR}=2.14, \text{AW}=1.46$ | $h=1, g=1, e=3.74, \text{cites}=15, i10=1$ | Publications: 1, Total cites: 15, $h=1$ | **MATCH** |
| **Harzing Vector** `[50, 25, 10, 5, 2, 1, 0]` | $h=4, g=7, e=8.60, \text{cites}=93, i10=3$ | $h=4, g=7, e=8.60, \text{cites}=93, i10=3$ | Publications: 7, Total cites: 93, $h=4$ | **MATCH** |
| **Multi-Author Vector** (3 papers: 30c/2a/2024, 12c/3a/2022, 4c/1a/2025) | $h=3, g=3, hL=3.0, hI=4.60, \text{AWCR}=14.40, \text{AW}=3.79$ | $h=3, hL=3.0, hI=4.60, \text{AWCR}=14.40, \text{AW}=3.79$ | All 6 cards match exact rounded values | **MATCH** |

---

## 3. Deduplication & Provenance Invariants

### 3.1 Strict DOI Match Invariant
- **Rule**: A match requires identical normalized DOIs. Differing non-empty DOIs are a strict non-match.
- **Verification**: Evaluated with two publications having identical titles `"Machine Learning Foundations"` but distinct DOIs (`10.1000/doi-A` vs `10.1000/doi-B`).
- **Result**: Records were strictly preserved as 2 distinct publications.

### 3.2 Citation Count Merge Policy
- **Rule**: When two provider records merge, citation counts take the maximum observed value:
  $$c_{\text{merged}} = \max(c_{\text{provider}_1}, c_{\text{provider}_2})$$
- **Verification**: OpenAlex (10 citations) merged with Semantic Scholar (15 citations) for the same paper $\rightarrow$ merged record has 15 citations.
- **Result**: Max observed citation correctly retained.

### 3.3 Provenance Transparency
- Rather than presenting merged citation counts as belonging to a single canonical database, the GUI details view renders `"PROVIDER EVIDENCE"` with full per-provider citation counts and query IDs.
