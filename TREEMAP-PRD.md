# Product Requirements Document: Interactive Customer Service Root Cause Treemap

**Version:** 1.4
**Date:** 2025-04-29
**Author:** Cline (Updated based on `generate_treemap.py`)
**Changes:**
*   Refined requirements to match script implementation (dynamic value col detection, specific error handling, debug default, node/hover text formats).
*   Updated Data Schema.
*   Removed implemented FR-12 from Open Issues.
*   Added requirement/description for collapsing single-descendant nodes visually (FR-10 modification).
*   Updated FR-4 (cleaning) and FR-14 (hover text) to reflect implementation details.
*   Adjusted Data Schema for plotted DataFrame.

## 1. Introduction

This document outlines the requirements for the Interactive Customer Service Root Cause Treemap generator. The system consists of a Python script that processes customer service ticket data from a CSV file and generates an interactive HTML treemap visualization using the Plotly library.

## 2. Goals

*   Visualize hierarchical customer service root cause data effectively.
*   Provide an interactive way for users to explore ticket distribution across different root cause levels.
*   Identify key areas contributing to customer service ticket volume.


## 3. User Stories

*   As a Customer Service Manager, I want to see a breakdown of ticket root causes so that I can identify trends and areas for improvement.
*   As a Data Analyst, I want to visualize the hierarchical structure of root causes and their corresponding ticket volumes so that I can report on key drivers.

## 4. Functional Requirements

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

**FR-1: Load data from CSV**
The system MUST read data from a specified CSV file (`../CS_rootcause_trunc.csv`). 

**FR-2: Data Source Configuration**
The CSV file MUST use a semicolon (`;`) as a delimiter. The script MUST handle potential double quotes (`"`) as the quote character and MUST skip initial spaces.  

**FR-3: Data Cleaning & Value Column Identification**
The script MUST dynamically identify the value column to be used for sizing the treemap rectangles. It SHOULD first attempt to use the last column in the CSV, unless its name matches hierarchy column patterns. If the last column is not suitable, it SHOULD search for columns containing keywords like 'Tickets', 'Count', 'Volume', or 'Total'. If no suitable column is found, an error MUST be raised. Once identified, this value column MUST be cleaned by removing whitespace (including potential thousands separators like spaces), converting to numeric, and removing rows with non-positive or non-convertible values.

**FR-4: Data Cleaning - Hierarchy Levels**
The hierarchy level columns ('Level 1' through 'Level 4') MUST be cleaned by converting to string, stripping leading/trailing whitespace, **removing trailing slashes (`/`)**, and replacing empty strings or 'nan' strings with `None` for initial processing. Missing level columns MUST be handled gracefully (added as `None`).

**FR-5: Data Aggregation**
Data MUST be aggregated by summing the value column (e.g., 'Total Tickets Q1') for each unique path defined by the hierarchy levels ('Level 1' through 'Level 4'). `None` values MUST be handled correctly during grouping.  

**FR-6: Hierarchy Path Handling**
After aggregation, `None` values in level columns MUST be replaced with empty strings (`''`) for compatibility with Plotly's path parameter.  

**FR-7: Node Label Generation**
Each node (rectangle) in the treemap MUST display a label derived from its data.  

**FR-8: Node Label Formatting**
The displayed text for each node ON EVERY LEVEL MUST be generated based on the node's data. The script uses Plotly's `texttemplate` for formatting.
*   The format applied via `texttemplate` MUST effectively be: `LeafLabel<br>(Value, Percentage%)`
*   `LeafLabel`: MUST be the last non-empty string in the node's hierarchy path (e.g., the content of 'Level 3' if 'Level 4' is empty). If all hierarchy levels for a row are empty, "Root" SHOULD be used as the label for aggregation purposes, although the final treemap displays an explicit root node separately. The `get_last_non_empty` helper function implements this leaf label retrieval.
*   `Value`: MUST be the aggregated value for that node (corresponding to `%{value}` in the template), formatted with a comma as a thousands separator and no decimal places (e.g., `1,234`), achieved using `%{value:,.0f}`.
*   `Percentage`: MUST be the node's value as a percentage of the *root* total value (corresponding to `%{percentRoot}` in the template), formatted to two decimal places (e.g., `15.25%`), achieved using `%{percentRoot:.2%}`.


**FR-9: Treemap Generation**
An interactive treemap visualization MUST be generated using Plotly Express.  

**FR-10: Treemap Hierarchy Definition & Collapsing Single Descendants**
The treemap hierarchy MUST be defined by the `path` parameter provided to Plotly Express.
*   An explicit root node (e.g., using `px.Constant("Root")`) MUST be prepended to the path definition.
*   **Single-Descendant Collapsing:** To simplify the visual structure, nodes that represent a single-descendant step in the *original* hierarchy MUST be visually collapsed.
    *   The script MUST first build an internal representation of the original hierarchy based on cleaned and aggregated data.
    *   It MUST then analyze this hierarchy (e.g., by examining the flattened leaf data) to identify parent-child relationships where the parent has only **one distinct child name** appearing under it across the entire dataset at that specific level. These are identified as "single steps".
    *   A final DataFrame for plotting (`df_plot`) MUST be created. The hierarchy columns ('Level 1' through 'Level 4') in this DataFrame MUST represent the *structural* path, where nodes identified as part of a "single step" are omitted, *unless* they are the final node in the path. Unused levels in the structural path MUST be set to `None`.
    *   This `df_plot` DataFrame, with its potentially shorter structural paths in the `Level` columns, MUST be used as the input to `px.treemap`, defining the visual nesting.
    *   Node text (FR-8) and hover text (FR-14) MUST still reflect the *original*, uncollapsed hierarchy information.

**FR-11: Treemap Values Definition**
The size of each rectangle in the treemap MUST correspond to the aggregated value from the *dynamically identified* value column (see FR-3) for that node.

**FR-12: Chart Title**
The main title of the treemap chart MUST incorporate the name of the *dynamically identified* value column (see FR-3). A descriptive base title (e.g., "Customer Service Root Cause Analysis") MUST also be included. The final format MUST be: `"Base Title: ValueColumnName"`.

**FR-13: Hover Information**
When hovering over a node, additional information MUST be displayed in a tooltip.  

**FR-14: Hover Information Formatting**
The hover tooltip format MUST be controlled using Plotly's `hovertemplate`.
*   The format applied via `hovertemplate` MUST effectively be: `<b>Original Path: FullOriginalPath</b><br>Label: CurrentLabel<br>ValueColumnName: Value<br>Percentage of Total: Percentage%<extra></extra>`
*   `FullOriginalPath`: MUST be the *original*, uncollapsed, human-readable path string (e.g., "Root > Level 1 > Level 2 > ..."), derived from the original data, cleaned of trailing slashes, and passed via `custom_data[0]` (`original_path_str`) in the script. It MUST be displayed using `%{customdata[0]}` in the template, NOT `%{id}`.
*   `CurrentLabel`: MUST be the label of the specific block being hovered over (leaf or parent), corresponding to `%{label}` in the template.
*   `ValueColumnName`: MUST be the name of the *dynamically identified* value column (see FR-3). This name MUST be directly included in the template string using an f-string in the Python code.
*   `Value`: MUST be the aggregated value for the node/block being hovered over (corresponding to `%{value}`), formatted with a comma as a thousands separator and no decimal places (e.g., `1,234`), achieved using `%{value:,.0f}`.
*   `Percentage`: MUST be the node's/block's value as a percentage of the *root* total value (corresponding to `%{percentRoot}`), formatted to two decimal places (e.g., `15.25%`), achieved using `%{percentRoot:.2%}`.
*   `<extra></extra>`: MUST be included to suppress the default Plotly trace information in the hover tooltip.

**FR-15: HTML Output**
The generated treemap MUST be saved as an HTML file (`../tickets-treemap.html`).  

**FR-16: Plotly Integration**
The output HTML MUST include the Plotly.js library from a CDN (Content Delivery Network); it MUST NOT be embedded within the file.  

**FR-17: Layout Adjustment**
The treemap layout SHOULD be tight, minimizing excess margins (Recommended: Top: 50px, Left: 25px, Right: 25px, Bottom: 25px).  

**FR-18: Debug Output - Intermediate Data**
The script MUST provide an OPTIONAL mechanism (controlled by the `ENABLE_DEBUG_OUTPUT` flag, which is **defaulted to `True`** in the script) to save intermediate DataFrames to separate CSV files for debugging. When enabled, the following outputs MUST be generated:
*   The DataFrame immediately after initial loading (`df_raw.csv`).
*   The DataFrame after cleaning (`df_cleaned.csv`).
*   The final aggregated DataFrame used for plotting (`df_aggregated.csv`).
These files MUST be saved to a dedicated subdirectory (`./debug_output/`).

**FR-19: Error Handling - File Not Found**
If the input CSV file does not exist, a user-friendly error message MUST be printed to the console.  

**FR-20: Error Handling - Empty File**
If the input CSV file is empty, a user-friendly error message MUST be printed to the console.  

**FR-21: Error Handling - Missing Columns**
The script MUST check for the presence of required columns after attempting to identify the value column (see FR-3).
*   If any of the defined `HIERARCHY_COLS` ('Level 1' through 'Level 4') are missing, a warning message MUST be printed to `stderr`, and the missing columns MUST be added to the DataFrame with `None` values before proceeding.
*   If the *dynamically identified value column* is missing, a user-friendly error message MUST be printed to `stderr`, and the script MUST exit.

**FR-22: Error Handling - General**
Any other unexpected errors during script execution MUST be caught. Specific errors like `pandas.errors.EmptyDataError`, `FileNotFoundError` (though also handled earlier), and `KeyError` SHOULD be caught with tailored messages. For all other exceptions, a generic error message including the exception details MUST be printed to `stderr`, and the script SHOULD print a traceback for detailed debugging information before exiting.

## 5. Non-Functional Requirements

**NFR-1: Technology Stack**
The system MUST be implemented using Python 3.x.  

**NFR-2: Dependencies**
The system REQUIRES the `pandas` and `plotly` Python libraries. 

**NFR-3: Input Data Format**
The input data MUST be provided in CSV format as specified in FR-1 and FR-2.  

**NFR-4: Output Format**
The output MUST be a single HTML file, referencing Plotly.js and other dependencies via CDN.  

**NFR-5: Maintainability**
The code SHOULD be well-commented and SHOULD follow standard Python coding practices (PEP 8). 

**NFR-6: Performance**
Not applicable. 

**NFR-7: Scalability**
Not applicable. 

**NFR-8: Security**
The script processes local files; no external network connections are made by the script itself. Loading Plotly from CDN occurs in the user's browser.  

## 6. Data Schema

**Input CSV (`CS_rootcause_trunc.csv`):**
*(Header row defines column names)*

*   **Contact Root Cause** (String): Combined root cause path (potentially ignored by script if Level columns are present).
*   **Level 1** (String): Top-level root cause category. (Cleaned: String conversion, whitespace stripping, empty/nan -> `None` -> `''`)
*   **Level 2** (String): Second-level root cause category. (Cleaned: String conversion, whitespace stripping, empty/nan -> `None` -> `''`)
*   **Level 3** (String): Third-level root cause category. (Cleaned: String conversion, whitespace stripping, empty/nan -> `None` -> `''`)
*   **Level 4** (String): Fourth-level root cause category (most specific). (Cleaned: String conversion, whitespace stripping, empty/nan -> `None` -> `''`)
*   **[Value Column]** (String / Integer): *Dynamically Identified*. Header name varies (e.g., 'Total Tickets Q1', 'Volume'). Number of items associated with the specific root cause path. (Cleaned: Whitespace/separator removal, numeric conversion, non-positive/NaN removal, invalid rows dropped.)

**Internal DataFrame (`df_agg` used for plotting):**

*   **Level 1** (String): Cleaned and aggregated level 1 category (empty string if `None` or missing).
*   **Level 2** (String): Cleaned and aggregated level 2 category (empty string if `None` or missing).
*   **Level 1** (String / `None`): Represents the *structural* path after collapsing (see FR-10). May be `None` if path depth is less than this level.
*   **Level 2** (String / `None`): Represents the *structural* path after collapsing.
*   **Level 3** (String / `None`): Represents the *structural* path after collapsing.
*   **Level 4** (String / `None`): Represents the *structural* path after collapsing.
*   **value_plot** (Integer/Float): Aggregated value for the original leaf node this row represents. Used for sizing rectangles.
*   **original_path_str** (String): The full, original, human-readable path (e.g., "Root > L1 > L2 > L3"). Used in `custom_data` for hover text (FR-14).
*   **original_leaf_label** (String): The label of the original leaf node (last part of `original_path_str`). Used in `custom_data` for display text (FR-8).
*   **display_text** (String): Pre-calculated text for display *on* the treemap node (see FR-8), passed via `custom_data`.
*   *(Implicitly Used by Plotly)*: The `value_plot` column is used for `values`. The `Level` columns are used for `path`. The `custom_data` array contains `original_path_str`, `display_text`, and `value_plot`.

## 7. Open Issues / Future Considerations

*   [Placeholder: Consider adding configuration options for input/output file paths, hierarchy columns, or value column keywords via command-line arguments or a config file.]
*   [Placeholder: Explore alternative color schemes or allow user configuration.]
*   [Placeholder: Add unit tests for data cleaning, value column detection, and aggregation logic.]
*   [Placeholder: Investigate performance optimization for very large datasets.]

## 8. Appendix

*   Plotly treemap documentation: https://plotly.com/python/treemaps/
