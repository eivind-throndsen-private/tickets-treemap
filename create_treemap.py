import pandas as pd
import plotly.express as px
import numpy as np

# Define the input file path
csv_file_path = '../customer-ops-treemap/CS_rootcause_trunc.csv'
# Define the output file path
output_html_path = '../customer-ops-treemap/interactive_customer_treemap.html'
# Define level columns
level_cols = ['Level 1', 'Level 2', 'Level 3', 'Level 4']

try:
    # Read the CSV file, specifying the semicolon delimiter and handling potential quote issues
    df = pd.read_csv(csv_file_path, delimiter=';', quotechar='"', skipinitialspace=True)

    # --- Data Cleaning ---
    # 1. Clean 'Total Tickets Q1' column
    # Remove leading/trailing whitespace
    df['Total Tickets Q1'] = df['Total Tickets Q1'].astype(str).str.strip()
    # Remove internal spaces used as thousands separators
    df['Total Tickets Q1'] = df['Total Tickets Q1'].str.replace(' ', '', regex=False)
    # Convert to numeric, coercing errors to NaN
    df['Total Tickets Q1'] = pd.to_numeric(df['Total Tickets Q1'], errors='coerce')
    # Drop rows where conversion failed or tickets are non-positive
    df.dropna(subset=['Total Tickets Q1'], inplace=True)
    df = df[df['Total Tickets Q1'] > 0]
    df['Total Tickets Q1'] = df['Total Tickets Q1'].astype(int)


    # 2. Clean Level columns
    # Fill potential NaN values and empty strings appropriately for Plotly treemap path
    # Also remove leading/trailing whitespace from level columns
    # Removed placeholder definition as we now use None
    for col in level_cols:
        if col in df.columns:
            # Ensure column is string type before stripping whitespace
            df[col] = df[col].astype(str).str.strip()
            # Replace empty strings and 'nan' strings (resulting from astype(str)) with None
            # Plotly treemap typically ignores None values in the path
            df[col] = df[col].replace({'': None, 'nan': None})
        else:
            print(f"Warning: Expected column '{col}' not found in the CSV.")
            # Add the missing column filled with None if it doesn't exist
            df[col] = None


    # --- Aggregate Data ---
    # Group by all level columns and sum the tickets to ensure each path is unique
    # dropna=False is crucial for groupby to handle the None values correctly
    print("Aggregating data...")
    df_agg = df.groupby(level_cols, dropna=False)['Total Tickets Q1'].sum().reset_index()
    print("Data aggregated.")

    # Replace None with empty string '' after aggregation for Plotly path handling
    for col in level_cols:
        df_agg[col] = df_agg[col].fillna('')

    # --- Identify Leaf Nodes and Prepare Display Text ---
    print("Identifying leaf nodes and preparing display text...")
    # Create path tuples, stopping at the first empty string
    def get_path_tuple(row):
        path = []
        for col in level_cols:
            if row[col] != '':
                path.append(row[col])
            else:
                break # Stop if level is empty
        # Return None for root node if path is empty
        return tuple(path) if path else None

    df_agg['path_tuple'] = df_agg.apply(get_path_tuple, axis=1) # Keep path_tuple for potential future use or debugging

    # --- Prepare Display Text String ---
    print("Preparing display text string...")
    # Calculate total for percentages
    total_tickets = df_agg['Total Tickets Q1'].sum()

    # Function to get the correct label and format the full display text string
    def get_display_text(row):
        # Find the actual label (the last non-empty string in the path)
        label = ""
        path_list = []
        for col in level_cols:
             if row[col] != '':
                 path_list.append(row[col])
             else:
                 break
        label = path_list[-1] if path_list else "Root" # Get last element or 'Root'

        value = row['Total Tickets Q1']
        percentage = (value / total_tickets) * 100 if total_tickets else 0

        # Apply the detailed format to ALL nodes, creating the final string here
        return f"{label} ({value:,.0f}, {percentage:.2f}%)"

    # Apply the function to create the display_text column
    df_agg['display_text'] = df_agg.apply(get_display_text, axis=1)
    print("Display text prepared.")

    # Clean up temporary columns (optional)
    # df_agg = df_agg.drop(columns=['path_tuple']) # Removed id/parent/label logic


    # --- Create Treemap ---
    print("Generating treemap...")
    fig = px.treemap(
        df_agg, # Use the aggregated and cleaned dataframe
        path=level_cols, # REVERTED to using path for hierarchy
        values='Total Tickets Q1',
        # ids='id',             # REMOVED
        # parents='parent_id',  # REMOVED
        # labels='node_label',  # REMOVED
        title='Customer Service Root Cause Analysis (Q1 Tickets)'
        # Removed branchvalues, letting Plotly sum children by default with aggregated data
        # Removed maxdepth=1 to show all levels initially
    )

    # Customize hover text and use the pre-calculated 'display_text' for node labels
    fig.update_traces(
        text=df_agg['display_text'],       # Use the pre-formatted string column
        textinfo='text',                   # Tell Plotly to display the content of the 'text' parameter
        hovertemplate='<b>%{label}</b><br>Total Tickets: %{value:,.0f}<br>Percentage of Total: %{percentRoot:.2%}<extra></extra>', # Keep hover info as is
        selector=dict(type='treemap')
    )

    # Make layout tighter
    fig.update_layout(margin = dict(t=50, l=25, r=25, b=25))

    # --- Save Treemap ---
    print(f"Saving treemap to {output_html_path}...")
    # Explicitly include Plotly.js from CDN in the HTML file
    fig.write_html(output_html_path, include_plotlyjs='cdn')
    print("Treemap saved successfully.")

except FileNotFoundError:
    print(f"Error: The file {csv_file_path} was not found.")
except pd.errors.EmptyDataError:
    print(f"Error: The file {csv_file_path} is empty.")
except KeyError as e:
    print(f"Error: Expected column {e} not found in the CSV file.")
    print("Please ensure the CSV contains columns: 'Level 1', 'Level 2', 'Level 3', 'Level 4', 'Total Tickets Q1'")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
