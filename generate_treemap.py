import pandas as pd
import plotly.express as px
import numpy as np
import os
import sys

# --- Configuration ---
INPUT_CSV_PATH = '../customer-ops-treemap/CS_rootcause_trunc.csv'
OUTPUT_HTML_PATH = '../customer-ops-treemap/tickets-treemap.html'
DEBUG_OUTPUT_DIR = '../customer-ops-treemap/debug_output/'
ENABLE_DEBUG_OUTPUT = True # FR-18: Default ON

# Hierarchy and value column names (assuming standard names, but will try to detect value column)
HIERARCHY_COLS = ['Level 1', 'Level 2', 'Level 3', 'Level 4']
# Value column will be determined dynamically, assuming it's the last column for now if not found
DEFAULT_VALUE_COL = None # Will be determined from CSV header

# --- Helper Functions ---

def clean_value_column(series):
    """Cleans the value column (e.g., 'Total Tickets Q1'). FR-3"""
    # Remove spaces (potential thousands separators) and convert to numeric
    series_cleaned = series.astype(str).str.replace(r'\s+', '', regex=True)
    series_numeric = pd.to_numeric(series_cleaned, errors='coerce')
    # Remove rows with non-positive or non-convertible values
    series_positive = series_numeric[series_numeric > 0]
    return series_positive

def clean_hierarchy_column(series):
    """Cleans a hierarchy level column. FR-4"""
    return series.astype(str).str.strip().replace(['', 'nan', 'None'], None)

def get_last_non_empty(row, cols):
    """Gets the last non-empty string from specified columns in a row. FR-8"""
    for col in reversed(cols):
        if pd.notna(row[col]) and row[col] != '':
            return row[col]
    return "Root" # Label for the root node if all levels are empty/None

def format_value(value):
    """Formats value with comma as thousands separator. FR-8"""
    try:
        return "{:,.0f}".format(value)
    except (ValueError, TypeError):
        return str(value)

def format_percentage(value, total):
    """Formats value as percentage of total. FR-8 / FR-14"""
    if total is None or total == 0:
        return "0.00%"
    try:
        return "{:.2f}%".format((value / total) * 100)
    except (ValueError, TypeError):
        return "N/A"

def generate_display_text(row, value_col, total_value, hierarchy_cols):
    """Generates the text displayed on the treemap node. FR-8"""
    leaf_label = get_last_non_empty(row, hierarchy_cols)
    value_formatted = format_value(row[value_col])
    percentage_formatted = format_percentage(row[value_col], total_value)
    return f"{leaf_label} ({value_formatted}, {percentage_formatted})"

def generate_hover_text(row, value_col, total_value, hierarchy_cols):
    """Generates the text displayed on hover. FR-14"""
    path_elements = [row[col] for col in hierarchy_cols if pd.notna(row[col]) and row[col] != '']
    hierarchical_label = " > ".join(path_elements) if path_elements else "Root"
    value_formatted = format_value(row[value_col])
    percentage_formatted = format_percentage(row[value_col], total_value)
    # FR-14: Using value_col name dynamically in hover text
    return f"<b>{hierarchical_label}</b><br>{value_col}: {value_formatted}<br>Percentage of Total: {percentage_formatted}"

# --- Main Script Logic ---

def main():
    # --- FR-19: Error Handling - File Not Found ---
    if not os.path.exists(INPUT_CSV_PATH):
        print(f"Error: Input CSV file not found at {INPUT_CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    try:
        # --- FR-1: Load data from CSV ---
        # --- FR-2: Data Source Configuration ---
        df_raw = pd.read_csv(
            INPUT_CSV_PATH,
            delimiter=';',
            quotechar='"',
            skipinitialspace=True,
            dtype=str # Read all as string initially to handle mixed types and cleaning
        )

        # --- FR-20: Error Handling - Empty File ---
        if df_raw.empty:
            print(f"Error: Input CSV file is empty: {INPUT_CSV_PATH}", file=sys.stderr)
            sys.exit(1)

        # --- Dynamic Value Column Detection (FR-12 preparation) ---
        # Simple heuristic: assume the last column is the value column if not 'Level 4' etc.
        potential_value_col = df_raw.columns[-1]
        if potential_value_col not in HIERARCHY_COLS and 'contact root cause' not in potential_value_col.lower():
             value_col = potential_value_col
             print(f"Info: Automatically detected value column as '{value_col}'.")
        else:
             # Fallback or require specific naming if detection fails?
             # For now, let's try a common default or raise error
             print(f"Warning: Could not reliably detect value column. Please ensure it's the last column or modify script.", file=sys.stderr)
             # Attempt to find a column containing 'Tickets', 'Count', 'Volume', 'Total' etc.
             value_col_candidates = [col for col in df_raw.columns if any(kw in col for kw in ['Tickets', 'Count', 'Volume', 'Total'])]
             if value_col_candidates:
                 value_col = value_col_candidates[0] # Take the first match
                 print(f"Info: Using heuristic value column: '{value_col}'.")
             else:
                 print(f"Error: Cannot determine the value column. No column header like 'Total Tickets Q1' found.", file=sys.stderr)
                 sys.exit(1)

        # --- FR-21: Error Handling - Missing Columns ---
        required_cols = HIERARCHY_COLS + [value_col]
        missing_cols = [col for col in required_cols if col not in df_raw.columns]
        if missing_cols:
            # Allow missing Level columns (FR-4), but not the value column
            missing_hierarchy = [col for col in missing_cols if col in HIERARCHY_COLS]
            missing_value = [col for col in missing_cols if col == value_col]

            if missing_hierarchy:
                 print(f"Warning: Missing hierarchy columns: {missing_hierarchy}. They will be treated as empty.", file=sys.stderr)
                 # Add missing hierarchy columns filled with NaN/None
                 for col in missing_hierarchy:
                     df_raw[col] = None # Or np.nan

            if missing_value:
                 print(f"Error: Required value column '{value_col}' is missing from the CSV.", file=sys.stderr)
                 sys.exit(1)

        # Ensure all expected hierarchy columns exist now
        for col in HIERARCHY_COLS:
            if col not in df_raw.columns:
                 df_raw[col] = None


        # --- FR-18: Debug Output - Raw Data ---
        if ENABLE_DEBUG_OUTPUT:
            os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
            df_raw.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_raw.csv'), index=False, sep=';')
            print(f"Debug: Saved raw data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_raw.csv')}")


        # --- Data Cleaning ---
        df_cleaned = df_raw.copy()

        # FR-3: Clean Value Column
        cleaned_values = clean_value_column(df_cleaned[value_col])
        df_cleaned = df_cleaned.loc[cleaned_values.index] # Keep only rows with valid values
        df_cleaned[value_col] = cleaned_values

        # FR-4: Clean Hierarchy Columns
        for col in HIERARCHY_COLS:
             if col in df_cleaned.columns: # Handle potentially missing cols added earlier
                df_cleaned[col] = clean_hierarchy_column(df_cleaned[col])

        # --- FR-18: Debug Output - Cleaned Data ---
        if ENABLE_DEBUG_OUTPUT:
             df_cleaned.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_cleaned.csv'), index=False, sep=';')
             print(f"Debug: Saved cleaned data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_cleaned.csv')}")


        # --- FR-5: Data Aggregation ---
        # Group by all hierarchy levels present and sum the value column
        grouping_cols = [col for col in HIERARCHY_COLS if col in df_cleaned.columns]
        df_agg = df_cleaned.groupby(grouping_cols, dropna=False)[value_col].sum().reset_index()


        # --- FR-6: Hierarchy Path Handling (Replace None with '') ---
        for col in HIERARCHY_COLS:
            if col in df_agg.columns:
                df_agg[col] = df_agg[col].fillna('') # Replace remaining NaN/None with empty string for Plotly path

        # --- Calculate Total Value for Percentages ---
        total_value = df_agg[value_col].sum()


        # --- FR-7 & FR-8: Node Label Generation & Formatting ---
        df_agg['display_text'] = df_agg.apply(
            lambda row: generate_display_text(row, value_col, total_value, HIERARCHY_COLS), axis=1
        )


        # --- FR-13 & FR-14: Hover Information Formatting ---
        df_agg['hover_text'] = df_agg.apply(
            lambda row: generate_hover_text(row, value_col, total_value, HIERARCHY_COLS), axis=1
        )


        # --- FR-18: Debug Output - Aggregated Data ---
        if ENABLE_DEBUG_OUTPUT:
            df_agg.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_aggregated.csv'), index=False, sep=';')
            print(f"Debug: Saved aggregated data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_aggregated.csv')}")


        # --- Add value column name to df for custom_data ---
        df_agg['value_col_name'] = value_col # Create column containing the value column's name

        # --- FR-9: Treemap Generation ---
        # --- FR-10: Treemap Hierarchy Definition ---
        # --- FR-11: Treemap Values Definition ---
        fig = px.treemap(
            df_agg,
            path=[px.Constant("Root")] + HIERARCHY_COLS, # Add explicit root
            values=value_col,
            # text='display_text', # Removed: Incorrect argument for px.treemap
            custom_data=[df_agg['value_col_name'], df_agg['display_text']], # FR-14 + Fix: Pass value col name AND display_text
            # FR-8 (Node Text): Use texttemplate below.
            # FR-14 (Hover Text): Use hovertemplate with custom_data below.
        )

        # --- FR-8 (Node Text) & FR-14 (Hover Text) Applied ---
        fig.update_traces(
            # Use texttemplate to format the displayed text on nodes (FR-8) - Reverted to original
            # %{customdata[1]} = Use the pre-calculated display text passed via custom_data (Fix for labels with '/')
            # %{value} = Aggregated value for the node
            # %{percentRoot} = Percentage relative to the root node
            texttemplate="%{customdata[1]}<br>(%{value:,.0f}, %{percentRoot:.2%})", # Fix: Use customdata for node label
            textinfo='text', # Display the text generated by texttemplate

            # Use hovertemplate with Plotly built-ins and the value col name from custom_data[0] (FR-14) - Kept fix
            # %{id} = Hierarchical path identifier (may look odd if levels have '/', but that's correct ID)
            # %{customdata[0]} = Value column name passed via custom_data
            # %{value} = Aggregated value for the node (works for leaves and parents)
            # %{percentRoot} = Percentage relative to the root node (works for leaves and parents)
            hovertemplate="<b>%{id}</b><br>%{customdata[0]}: %{value:,.0f}<br>Percentage of Total: %{percentRoot:.2%}<extra></extra>",
        )

        # --- Remove manual text/label override section ---
        # (The code previously here setting fig.data[0].text was causing issues)


        # --- FR-12: Chart Title ---
        base_title = "Customer Service Root Cause Analysis"
        chart_title = f"{base_title}: {value_col}"
        fig.update_layout(title_text=chart_title)


        # --- FR-17: Layout Adjustment ---
        fig.update_layout(
             margin=dict(t=50, l=25, r=25, b=25)
        )


        # --- FR-15: HTML Output ---
        # --- FR-16: Plotly Integration (CDN) ---
        fig.write_html(
             OUTPUT_HTML_PATH,
             full_html=True, # Generate a complete HTML file
             include_plotlyjs='cdn' # Use CDN link
        )
        print(f"\nSuccess! Interactive treemap generated: {OUTPUT_HTML_PATH}")


    # --- FR-22: Error Handling - General ---
    except pd.errors.EmptyDataError:
        print(f"Error: Input CSV file is empty or could not be parsed correctly: {INPUT_CSV_PATH}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
         # This case is handled above, but keep it just in case
         print(f"Error: Input CSV file not found at {INPUT_CSV_PATH}", file=sys.stderr)
         sys.exit(1)
    except KeyError as e:
         print(f"Error: Missing expected column in CSV: {e}. Please check CSV headers.", file=sys.stderr)
         sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

# --- Entry Point ---
if __name__ == "__main__":
    main()
