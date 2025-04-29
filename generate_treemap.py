import pandas as pd
import plotly.express as px
import numpy as np
import os
import sys
import collections # Added for defaultdict if needed, although not used in final tree logic
import json # Added for debug output

# --- Configuration ---
INPUT_CSV_PATH = 'CS_rootcause_trunc.csv'
OUTPUT_HTML_PATH = 'tickets-treemap.html'
DEBUG_OUTPUT_DIR = './debug_output/'
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
    """Cleans a hierarchy level column. FR-4. Also removes trailing slashes."""
    # Strip leading/trailing whitespace, then strip trailing slashes, then strip whitespace again just in case
    cleaned = series.astype(str).str.strip().str.rstrip('/').str.strip()
    return cleaned.replace(['', 'nan', 'None'], None) # Replace empty/NA markers with None

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
    """DEPRECATED: Original hover text generation. Replaced by generate_hover_text_from_data."""
    # path_elements = [row[col] for col in hierarchy_cols if pd.notna(row[col]) and row[col] != '']
    # hierarchical_label = " > ".join(path_elements) if path_elements else "Root"
    # value_formatted = format_value(row[value_col])
    # percentage_formatted = format_percentage(row[value_col], total_value)
    # return f"<b>{hierarchical_label}</b><br>{value_col}: {value_formatted}<br>Percentage of Total: {percentage_formatted}"
    pass # Keep function signature for reference if needed, but logic moved

# --- Tree Manipulation Helpers --- START ---

# Helper function to build the tree structure
def build_tree(df, hierarchy_cols, value_col):
    """Builds a nested dictionary tree from the aggregated DataFrame."""
    tree = {'name': 'Root', 'children': {}, 'value': 0, 'original_path': ['Root'], 'is_leaf': False}
    total_value = df[value_col].sum() # Needed for root value verification

    for _, row in df.iterrows():
        current_level = tree
        full_original_path = ['Root'] # Keep track of the *original* path for this row

        for i, level_name in enumerate(hierarchy_cols):
            node_name = row[level_name]
            if pd.isna(node_name) or node_name == '':
                # Stop processing this row's hierarchy if we hit an empty level
                # Associate value with the parent node reached so far (if applicable this row represents its value)
                # This check handles cases where a row represents an intermediate node's value directly
                is_last_valid_level_in_row = True
                for next_level_name in hierarchy_cols[i:]: # Check if remaining levels are also empty/NA
                    if pd.notna(row[next_level_name]) and row[next_level_name] != '':
                        is_last_valid_level_in_row = False
                        break
                if is_last_valid_level_in_row and current_level['name'] != 'Root': # Avoid double-counting at root
                     current_level['value'] += row[value_col]
                     current_level['is_leaf'] = True # Mark as a leaf based on this row's data

                break # Stop processing levels for this row once an empty one is found

            full_original_path.append(node_name)

            if node_name not in current_level['children']:
                current_level['children'][node_name] = {
                    'name': node_name,
                    'children': {},
                    'value': 0, # Initialize value, will be summed up from leaves and direct assignments
                    'original_path': list(full_original_path), # Store original path fragment
                    'is_leaf': False # Assume not a leaf initially
                }
            # If child exists, ensure its original_path is the shortest one found (usually not needed, paths should be consistent)
            elif len(full_original_path) < len(current_level['children'][node_name]['original_path']):
                 current_level['children'][node_name]['original_path'] = list(full_original_path)


            current_level = current_level['children'][node_name]

            # If this is the last non-empty level *for this row*, it's a leaf contribution
            is_last_level_for_row = True
            for next_level_name in hierarchy_cols[i+1:]:
                 if pd.notna(row[next_level_name]) and row[next_level_name] != '':
                      is_last_level_for_row = False
                      break

            if is_last_level_for_row:
                current_level['value'] += row[value_col] # Add value contribution
                current_level['is_leaf'] = True # Mark as a potential leaf
                break # Stop processing levels for this row

    # Recalculate parent values based on children sum *after* all rows processed
    def update_parent_values_and_leaf_status(node):
        if not node['children']:
             node['is_leaf'] = True # Correctly mark leaves post-aggregation
             # Keep node['value'] as summed from direct assignments
             return node['value']

        # Node has children
        node['is_leaf'] = False # Mark as not a leaf if it has children
        children_sum = sum(update_parent_values_and_leaf_status(child) for child in node['children'].values())
        # Node's total value is its directly assigned value + sum of its children's values
        node['value'] += children_sum
        return node['value']

    # Initial call starts the recursive update; root value gets updated too
    calculated_total = update_parent_values_and_leaf_status(tree)

    # Ensure root value reflects the total sum accurately
    tree['value'] = calculated_total # Assign the recursively calculated total
    if not tree['children']: # Handle empty data case gracefully
        tree['value'] = 0
    elif abs(tree['value'] - total_value) > 1e-6 : # Verify against original sum (tolerance for floats)
        print(f"Warning: Root value recalc ({tree['value']}) doesn't match original total sum ({total_value}). Using original sum.", file=sys.stderr)
        tree['value'] = total_value # Prefer original sum if discrepancy is significant

    return tree


# Helper function to collapse the tree
def collapse_tree(node):
    """DEPRECATED: No longer used. Collapsing handled by DataFrame manipulation."""
    pass

# Helper function to flatten the tree into a DataFrame for Plotly
def flatten_tree_to_df(node, max_depth, hierarchy_cols_map, current_path=None, data_list=None):
     """DEPRECATED: Renamed to flatten_original_tree_to_df and simplified."""
     pass


# Helper function to flatten the ORIGINAL tree into a DataFrame for Plotly path calculation
def flatten_original_tree_to_df(node, max_depth, hierarchy_cols_map, current_path=None, data_list=None):
    """Flattens the ORIGINAL tree structure into a list of dictionaries for LEAF nodes."""
    if current_path is None:
        current_path = [] # Represents the ORIGINAL path
    if data_list is None:
        data_list = []

    # Determine the current node's name for the original path (skip 'Root')
    node_name = node['name']
    next_path = list(current_path) # Copy
    if node_name != 'Root':
        next_path.append(node_name)

    # Add a row ONLY if this node is an original leaf ('is_leaf' == True) and has positive value.
    if node['is_leaf'] and node['value'] > 0:
        row_data = {}
        # Populate the original path columns
        for i in range(max_depth):
             col_name = hierarchy_cols_map[i] # Get the actual 'Level N' name
             row_data[col_name] = next_path[i] if i < len(next_path) else ''

        # Add value and original path string for display/hover
        row_data['value_plot'] = node['value'] # Use the leaf's value
        row_data['original_path_str'] = " > ".join(node['original_path']) # Original full path of the leaf
        row_data['original_leaf_label'] = node['original_path'][-1] if len(node['original_path']) > 1 else node['name']

        data_list.append(row_data)

    # --- Recursive Call for Children ---
    # Recursively process children using the *next_path* derived from the original tree.
    for child_node in node['children'].values():
        flatten_original_tree_to_df(child_node, max_depth, hierarchy_cols_map, next_path, data_list)

    return data_list


# --- Original Helper Functions (get_last_non_empty, formatters) - Adjusted ---

def get_original_leaf_label(original_path_list):
    """Gets the last element of the original path list."""
    # This function is not directly used now, label comes from flatten_tree_to_df
    return original_path_list[-1] if len(original_path_list) > 1 else "Root"

# format_value remains the same
# format_percentage remains the same


# --- Modified Display/Hover Text Generation ---

def generate_display_text_from_data(original_leaf_label, value, total_value):
    """Generates the text displayed on the treemap node using flattened data."""
    value_formatted = format_value(value)
    percentage_formatted = format_percentage(value, total_value)
    # Use the original leaf label stored during flattening
    return f"{original_leaf_label}<br>{value_formatted}<br>{percentage_formatted}"

# Removed generate_hover_text_from_data as it's replaced by hovertemplate logic below
# def generate_hover_text_from_data(original_path_str, value_col_name, value, total_value):
#     """DEPRECATED: Generates the text displayed on hover using flattened data."""
#     hierarchical_label = original_path_str
#     value_formatted = format_value(value)
#     percentage_formatted = format_percentage(value, total_value)
#     return f"<b>{hierarchical_label}</b><br>{value_col_name}: {value_formatted}<br>Percentage of Total: {percentage_formatted}"


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
            dtype=str # Read all as string initially
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
             value_col_candidates = [col for col in df_raw.columns if any(kw in col.lower() for kw in ['tickets', 'count', 'volume', 'total'])] # case-insensitive check
             if value_col_candidates:
                 value_col = value_col_candidates[0] # Take the first match
                 print(f"Info: Using heuristic value column: '{value_col}'.")
             else:
                 print(f"Error: Cannot determine the value column. Last column is '{potential_value_col}'. No heuristic match found.", file=sys.stderr)
                 sys.exit(1)

        # --- FR-21: Error Handling - Missing Columns ---
        # Identify which of the configured HIERARCHY_COLS actually exist in the CSV
        current_hierarchy_cols = [col for col in HIERARCHY_COLS if col in df_raw.columns]
        missing_hierarchy = [col for col in HIERARCHY_COLS if col not in df_raw.columns]

        if missing_hierarchy:
             print(f"Warning: Missing configured hierarchy columns: {missing_hierarchy}. They will be ignored in the hierarchy.", file=sys.stderr)

        # Check if the detected or specified value column exists
        if value_col not in df_raw.columns:
             print(f"Error: Required value column '{value_col}' is missing from the CSV.", file=sys.stderr)
             sys.exit(1)

        # Define the columns we actually need to process
        required_cols = current_hierarchy_cols + [value_col]


        # --- FR-18: Debug Output - Raw Data ---
        if ENABLE_DEBUG_OUTPUT:
            os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
            df_raw.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_raw.csv'), index=False, sep=';')
            print(f"Debug: Saved raw data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_raw.csv')}")


        # --- Data Cleaning ---
        # Select only the required columns for cleaning and processing
        df_cleaned = df_raw[required_cols].copy()

        # FR-3: Clean Value Column
        cleaned_values = clean_value_column(df_cleaned[value_col])
        # Check if any valid values remain
        if cleaned_values.empty:
             print(f"Error: No valid positive numeric data found in value column '{value_col}' after cleaning.", file=sys.stderr)
             sys.exit(1)
        # Filter df_cleaned based on valid indices from cleaned_values and assign back
        df_cleaned = df_cleaned.loc[cleaned_values.index].copy() # Use .copy() to avoid SettingWithCopyWarning
        df_cleaned[value_col] = cleaned_values

        # FR-4: Clean Hierarchy Columns (only those present)
        for col in current_hierarchy_cols:
             df_cleaned[col] = clean_hierarchy_column(df_cleaned[col])

        # --- FR-18: Debug Output - Cleaned Data ---
        if ENABLE_DEBUG_OUTPUT:
             df_cleaned.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_cleaned_pre_agg.csv'), index=False, sep=';')
             print(f"Debug: Saved cleaned data before aggregation to {os.path.join(DEBUG_OUTPUT_DIR, 'df_cleaned_pre_agg.csv')}")


        # --- FR-5: Data Aggregation ---
        # Group by only the hierarchy columns that are actually present
        df_agg = df_cleaned.groupby(current_hierarchy_cols, dropna=False)[value_col].sum().reset_index()

        # Filter out zero/negative sums if any occurred (shouldn't due to cleaning, but safety check)
        df_agg = df_agg[df_agg[value_col] > 0]

        # Check if aggregation resulted in empty DataFrame
        if df_agg.empty:
             print(f"Error: No data remaining after aggregation. Check input data and hierarchy levels.", file=sys.stderr)
             sys.exit(1)

        # --- FR-6: Handle NAs after aggregation (replace with '') ---
        # Only apply to the hierarchy columns used in aggregation
        for col in current_hierarchy_cols:
            df_agg[col] = df_agg[col].fillna('')

        # --- FR-18: Debug Output - Aggregated Data ---
        if ENABLE_DEBUG_OUTPUT:
             df_agg.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_aggregated_original.csv'), index=False, sep=';')
             print(f"Debug: Saved original aggregated data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_aggregated_original.csv')}")


        # --- Build, Collapse, and Flatten Tree --- START --- NO COLLAPSE HERE ---
        print("Info: Building original hierarchy tree...")
        # Pass only the hierarchy columns that actually exist and were used for aggregation
        hierarchy_tree = build_tree(df_agg, current_hierarchy_cols, value_col)

        if ENABLE_DEBUG_OUTPUT:
            try:
                # Use default=str for objects that aren't directly serializable
                with open(os.path.join(DEBUG_OUTPUT_DIR, 'tree_original.json'), 'w') as f:
                    json.dump(hierarchy_tree, f, indent=2, default=str)
                print(f"Debug: Saved original tree structure to {os.path.join(DEBUG_OUTPUT_DIR, 'tree_original.json')}")
            except Exception as e:
                print(f"Debug: Could not serialize original tree to JSON: {e}", file=sys.stderr)


        print("Info: Flattening original tree to DataFrame...")
        # Use the original full HIERARCHY_COLS list to define the maximum depth and column names
        hierarchy_cols_map = {i: col for i, col in enumerate(HIERARCHY_COLS)}
        max_depth = len(HIERARCHY_COLS)
        # Use the new flattening function for the original tree
        flattened_data_orig = flatten_original_tree_to_df(hierarchy_tree, max_depth, hierarchy_cols_map)

        if not flattened_data_orig:
             print("Error: Flattened original data is empty. Check tree logic and input data.", file=sys.stderr)
             sys.exit(1)

        df_flat_orig = pd.DataFrame(flattened_data_orig)

        if ENABLE_DEBUG_OUTPUT:
            df_flat_orig.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_flattened_original.csv'), index=False, sep=';')
            print(f"Debug: Saved flattened original data to {os.path.join(DEBUG_OUTPUT_DIR, 'df_flattened_original.csv')}")


        # --- Identify Single-Descendant Steps ---
        print("Info: Identifying single-descendant steps...")
        single_steps = set()
        # Use HIERARCHY_COLS for full potential depth, check if col exists in df_flat_orig
        valid_hierarchy_cols_for_analysis = [col for col in HIERARCHY_COLS if col in df_flat_orig.columns]

        for k in range(len(valid_hierarchy_cols_for_analysis)):
            parent_cols = valid_hierarchy_cols_for_analysis[:k]
            child_col = valid_hierarchy_cols_for_analysis[k]

            # Group by parent path, count distinct children in child_col
            if parent_cols: # Group by parent levels if they exist
                 grouped = df_flat_orig.groupby(parent_cols)
            else: # For Level 1, effectively group the whole DataFrame
                 # Add a temporary key to group all rows
                 df_flat_orig['_root_group'] = 0
                 grouped = df_flat_orig.groupby('_root_group')


            for name, group in grouped:
                 # Get unique non-empty children for this parent group
                 unique_children = group[child_col].replace('', np.nan).dropna().unique()
                 if len(unique_children) == 1:
                      # This parent path has only one child at this level
                      parent_path_tuple = name if isinstance(name, tuple) else (name,)
                      # Handle the root case where name might be 0 from _root_group
                      if not parent_cols and name == 0:
                          parent_path_tuple = () # Root parent path is empty tuple

                      child_name = unique_children[0]
                      single_steps.add((parent_path_tuple, child_name))

            # Clean up temporary column if added
            if '_root_group' in df_flat_orig.columns:
                 del df_flat_orig['_root_group']

        if ENABLE_DEBUG_OUTPUT:
            # Convert tuples to strings for JSON serialization
            serializable_steps = [f"{' > '.join(p)} -> {c}" if p else f"Root -> {c}" for p, c in single_steps]
            try:
                with open(os.path.join(DEBUG_OUTPUT_DIR, 'single_steps.json'), 'w') as f:
                    json.dump(sorted(list(serializable_steps)), f, indent=2)
                print(f"Debug: Saved identified single-descendant steps to {os.path.join(DEBUG_OUTPUT_DIR, 'single_steps.json')}")
            except Exception as e:
                print(f"Debug: Could not serialize single steps to JSON: {e}", file=sys.stderr)


        # --- Create df_plot with Collapsed Paths ---
        print("Info: Creating structural paths for plotting...")
        df_plot = df_flat_orig.copy()
        structural_paths = []

        for _, row in df_plot.iterrows():
            # Extract original path components, stopping at first empty value
            orig_path_components = []
            for col in HIERARCHY_COLS:
                if col in row and pd.notna(row[col]) and row[col] != '':
                    orig_path_components.append(row[col])
                else:
                    break # Stop if column missing or path ends

            new_structural_path = []
            # Iterate through original path components to build structural path
            for i in range(len(orig_path_components)):
                current_node = orig_path_components[i]
                parent_path_tuple = tuple(orig_path_components[:i])

                is_single_step = (parent_path_tuple, current_node) in single_steps
                is_last_element = (i == len(orig_path_components) - 1)

                # Append node if it's NOT a single step, OR if it IS the last element
                if not is_single_step or is_last_element:
                    new_structural_path.append(current_node)

            structural_paths.append(new_structural_path)

        # Update Level columns in df_plot with the new structural paths
        for i in range(len(HIERARCHY_COLS)):
            col_name = HIERARCHY_COLS[i]
            # Apply the i-th element of the structural path, or None if path is shorter
            df_plot[col_name] = [path[i] if i < len(path) else None for path in structural_paths] # Use None instead of ''


        # --- Calculate Total Value for Percentages (use sum from original flattened data) ---
        total_value = df_flat_orig['value_plot'].sum()

        # --- Generate Display and Hover Text using flattened data ---
        if total_value <= 0:
            print("Warning: Total value is zero or negative. Percentages will be zero.", file=sys.stderr)
            total_value = 0

        # Display text generation remains the same (uses original leaf label)
        df_plot['display_text'] = df_plot.apply(
             lambda row: generate_display_text_from_data(row['original_leaf_label'], row['value_plot'], total_value), axis=1
        )


        # --- FR-18: Debug Output - Flattened Data for Plotting ---
        if ENABLE_DEBUG_OUTPUT:
            df_plot.to_csv(os.path.join(DEBUG_OUTPUT_DIR, 'df_plot_final.csv'), index=False, sep=';')
            print(f"Debug: Saved final data for plotting to {os.path.join(DEBUG_OUTPUT_DIR, 'df_plot_final.csv')}")
        # --- Build, Collapse, and Flatten Tree --- END --- DF Manipulation ---


        # --- FR-9 to FR-14: Treemap Generation (Using df_plot with modified paths) ---
        print("Info: Generating Plotly treemap...")
        fig = px.treemap(
            df_plot,
            # Path uses the *modified* structural hierarchy columns from df_plot
            path=[px.Constant("Root")] + HIERARCHY_COLS,
            values='value_plot', # Use the value column from df_plot
            # Pass necessary data for templates: original path string, calculated display text, plot value
            custom_data=['original_path_str', 'display_text', 'value_plot'],
        )

        # --- Apply Text and Hover Templates ---
        fig.update_traces(
            # texttemplate uses the pre-calculated display_text from custom_data[1]
            texttemplate="%{customdata[1]}",
            textinfo='text', # Instructs Plotly to use the texttemplate result
            textfont=dict(size=18),

            # hovertemplate uses Plotly built-ins
            # %{id} shows the structural path Plotly uses (reflects collapsing based on modified Level columns)
            # %{label} shows the name of the current block
            # %{value} shows the aggregated value for the block
            # %{percentRoot} shows the percentage relative to the total value
            # We use python f-string to inject the actual value_col name
            hovertemplate=(
                "<b>Original Path: %{customdata[0]}</b><br>" # Use original path string from custom_data
                f"Label: %{{label}}<br>" # Label of the current block
                f"{value_col}: %{{value:,.0f}}<br>" # Value
                "Percentage of Total: %{percentRoot:.2%}"
                "<extra></extra>"
            ),
            hoverinfo='skip' # Set hoverinfo='skip' as hovertemplate provides all info
        )

        # --- FR-12: Chart Title ---
        base_title = "Customer Service Root Cause Analysis"
        chart_title = f"{base_title}: {value_col}"

        fig.update_layout(title_text=chart_title)


        # --- FR-17: Layout Adjustment ---
        fig.update_layout(margin=dict(t=50, l=25, r=25, b=25))


        # --- FR-15 & FR-16: HTML Output ---
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
         print(f"Error: Missing expected column in CSV or DataFrame processing: {e}. Please check CSV headers and script logic.", file=sys.stderr)
         sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during script execution: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

# --- Entry Point ---
if __name__ == "__main__":
    main()
