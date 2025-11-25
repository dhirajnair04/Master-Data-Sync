from flask import Flask, request, render_template, jsonify, redirect, url_for, session
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
import numpy as np
import warnings
import re 

warnings.filterwarnings("ignore")

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session_management' # Required for session

# Global variables (Note: In a production app, use a database or Redis for state)
df_store = {
    'raw': None,
    'synced': None,
    'final': None
}

# Database connection
TEST_EXIM_CONN_STR = "mssql+pyodbc://@.\SQLEXPRESS/Test_Exim?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes"
EXPORT_TABLE_NAME = 'EximExport'
IMPORT_TABLE_NAME = 'EximImport'
ENTITY_MASTER_TABLE = 'EntityMaster'

# Master Table Columns
MASTER_COL_IEC = 'IEC_Code'        
MASTER_COL_NAME = 'Importer/Exporter_Name'    
MASTER_COL_FMT = 'Formatted_Name'  

# ========== Utility Functions ==========

def sanitize_iec_code(text):
    if pd.isna(text) or text == 'nan' or text == 'None':
        return np.nan
    text_str = str(text).strip()
    clean_code = text_str.lstrip('0')
    return clean_code if clean_code else text_str 

def clean_special_chars(text):
    if not isinstance(text, str):
        return ""
    cleaned_text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return cleaned_text.strip()

def clean_special_chars_spaces(text):
    if not isinstance(text, str):
        return ""
    cleaned_text = re.sub(r'[^a-zA-Z0-9]', '', text)
    return cleaned_text.strip()

def expand_business_terms(text):
    if not isinstance(text, str):
        return ""
    text = text.upper()
    text = re.sub(r'\bPVT\b', 'PRIVATE', text)
    text = re.sub(r'\bLTD\b', 'LIMITED', text)
    text = re.sub(r'\bCO\b', 'COMPANY', text)
    return text

def generate_formatted_name(text):
    if not isinstance(text, str):
        return ""
    expanded_text = expand_business_terms(text)
    formatted = re.sub(r'[^a-zA-Z0-9]', '', expanded_text)
    return formatted.upper()

def get_db_engine():
    return create_engine(TEST_EXIM_CONN_STR)

def sync_and_update_master(df, data_type):
    engine = get_db_engine()
    
    if data_type == 'export':
        col_iec = 'IEC'
        col_name = 'Exporter_Name'
        col_formatted = 'Exporter' 
    else:
        col_iec = 'ICE'
        col_name = 'Importer_Name'
        col_formatted = 'Importer'

    try:
        query = f"SELECT {MASTER_COL_IEC}, [{MASTER_COL_NAME}] as Entity_Name, {MASTER_COL_FMT} FROM {ENTITY_MASTER_TABLE}"
        df_master_db = pd.read_sql(query, engine)
        df_master_db[MASTER_COL_IEC] = df_master_db[MASTER_COL_IEC].apply(sanitize_iec_code)
        master_name_col_pandas = 'Entity_Name'
    except Exception as e:
        print(f"Error loading Master Table: {e}")
        return df

    df[col_iec] = df[col_iec].apply(sanitize_iec_code)
    
    valid_iec_mask = df[col_iec].notnull() & (df[col_iec] != '') & (df[col_iec] != 'nan')
    df_valid = df.loc[valid_iec_mask].copy()
    
    if df_valid.empty:
        return df

    existing_iecs = set(df_master_db[MASTER_COL_IEC].unique())
    upload_iecs = set(df_valid[col_iec].unique())
    new_iecs = upload_iecs - existing_iecs
    
    if new_iecs:
        print(f"Found {len(new_iecs)} new IECs. Processing insertions...")
        new_entries = df_valid[df_valid[col_iec].isin(new_iecs)].drop_duplicates(subset=[col_iec])[[col_iec, col_name]]
        
        new_entries_to_upload = pd.DataFrame()
        new_entries_to_upload[MASTER_COL_IEC] = new_entries[col_iec]
        new_entries_to_upload[MASTER_COL_NAME] = new_entries[col_name].apply(clean_special_chars).apply(expand_business_terms)
        new_entries_to_upload[MASTER_COL_FMT] = new_entries[col_name].apply(generate_formatted_name)
        
        try:
            new_entries_to_upload.to_sql(ENTITY_MASTER_TABLE, engine, if_exists='append', index=False)
            print("New entities added to Master successfully.")
            new_entries_to_upload.rename(columns={MASTER_COL_NAME: master_name_col_pandas}, inplace=True)
            df_master_db = pd.concat([df_master_db, new_entries_to_upload], ignore_index=True)
        except Exception as e:
            print(f"Error updating EntityMaster: {e}")

    df_merged = df.merge(df_master_db, left_on=col_iec, right_on=MASTER_COL_IEC, how='left')
    
    df_merged[col_name] = np.where(
        df_merged[MASTER_COL_IEC].notnull(),
        df_merged[master_name_col_pandas], 
        df_merged[col_name]
    )
    
    df_merged[col_formatted] = np.where(
        df_merged[MASTER_COL_IEC].notnull(),
        df_merged[MASTER_COL_FMT],
        df_merged[col_name].apply(generate_formatted_name)
    )

    cols_to_drop = [MASTER_COL_IEC, master_name_col_pandas, MASTER_COL_FMT]
    df_merged.drop(columns=cols_to_drop, inplace=True, errors='ignore')

    return df_merged

def load_exchange_rates():
    try:
        cust_exch_rate = pd.read_excel('ExchangeRate.xlsx')
        cust_exch_rate['Date'] = pd.to_datetime(cust_exch_rate['Date'])
        return cust_exch_rate
    except Exception as e:
        print(f"Error loading exchange rate: {e}")
        return pd.DataFrame()

def final_transform_logic(df, data_type):
    date_col = 'SB Date' if data_type == 'export' else 'BE Date'
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')

    quantity_col = 'Quantity' if 'Quantity' in df.columns else 'QUANTITY'
    unit_col = 'Unit'
    
    # Pre-clean Quantity to Numeric
    if quantity_col in df.columns:
        df[quantity_col] = pd.to_numeric(df[quantity_col], errors='coerce').fillna(0)

    if quantity_col in df.columns and unit_col in df.columns:
        df['QUANTITY_KG'] = np.where(df[unit_col] == 'MTS', df[quantity_col] * 1000, df[quantity_col])
    else:
        df['QUANTITY_KG'] = 0

    cust_exch_rate = load_exchange_rates()
    if not cust_exch_rate.empty:
        df = pd.merge_asof(df.sort_values(date_col), cust_exch_rate.sort_values('Date'),
                        by='Category', left_on=date_col, right_on='Date', direction='backward')

    df['Unit Rate INR'] = pd.to_numeric(df['Unit Rate INR'], errors='coerce').fillna(0)
    
    if 'ExchangeRateUSD' in df.columns:
        df['ExchangeRateUSD'] = pd.to_numeric(df['ExchangeRateUSD'], errors='coerce').fillna(1)
        df['ExchangeRateUSD'] = df['ExchangeRateUSD'].replace(0, 1)
        df['USD Value'] = df['Unit Rate INR'] / df['ExchangeRateUSD']
    else:
        df['USD Value'] = 0

    unit_check = df[unit_col].isin(['Ton', 'MTS']) if unit_col in df.columns else False
    df['Per_KG_Rate'] = np.where(unit_check, df['USD Value'] / 1000, df['USD Value'])
    df['Total_Value'] = df['QUANTITY_KG'] * df['Per_KG_Rate']
    df['Per_KG_INR'] = np.where(unit_check, df['Unit Rate INR'] / 1000, df['Unit Rate INR'])
    df['Total_Value_INR'] = df['QUANTITY_KG'] * df['Per_KG_INR']

    # === CLEANING AND TYPE ENFORCEMENT ===

    # Step 1: Clean numeric columns
    numeric_cols = ['QUANTITY_KG', 'Per_KG_Rate', 'Total_Value', 'Per_KG_INR', 'Total_Value_INR', 'USD Value']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        df[col] = df[col].replace([np.inf, -np.inf], 0)
        df[col] = df[col].fillna(0)
        df[col] = df[col].round(2)
        df[col] = df[col].astype(float)

    # Step 2: Clean HS Code as string BEFORE renaming
    df['HS Code'] = df['HS Code'].astype(str).str.replace('.0', '', regex=False).str.strip()

    # Step 3: Clean identifier columns as strings BEFORE renaming
    id_number_cols = ['SB Number', 'BE Number']
    id_code_cols = ['IEC', 'ICE']

    for col in id_number_cols + id_code_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'None', 'NaN', ''], None)

    # Step 4: Uppercase text columns only (exclude numeric, IDs, and HS Code)
    exclude_from_upper = numeric_cols + id_number_cols + id_code_cols + ['HS Code']
    for col in df.select_dtypes(include=['object']).columns:
        if col not in exclude_from_upper:
            df[col] = df[col].astype(str).str.upper()

    # === NOW DO THE RENAMING AND FINAL FORMATTING ===
    
    if data_type == 'export':
        rename_map = {
            'Product Description': 'Product_Name',
            'HS Code': 'HS_Code',
            'Consignee Name': 'Consignee_Name',
            'SB Number': 'SB_Number',
            'SB Date': 'SB_Date',
            'Exporter City': 'Exporter_City',
            'Exporter State': 'Exporter_State',
            'Port of Destination': 'Port_of_Destination',
            'Country of Destination': 'Country_of_Destination'
        }
        
        # Create formatted columns BEFORE renaming
        df['Product'] = df['Product Description'].apply(clean_special_chars_spaces).str.upper()
        df['Consignee'] = df['Consignee Name'].apply(clean_special_chars_spaces).str.upper()
        
        final_cols = [
            'Mode', 'SB_Number', 'SB_Date', 'HS_Code', 'Product_Name', 'Product', 
            'IEC', 'Exporter_Name', 'Exporter', 
            'QUANTITY_KG', 'Per_KG_Rate', 'Total_Value', 'Per_KG_INR', 'Total_Value_INR', 
            'Exporter_City', 'Exporter_State', 'Consignee_Name', 'Consignee', 
            'Port_of_Destination', 'Country_of_Destination', 'CHAPTER'
        ]

    else:
        rename_map = {
            'Product Description': 'Product_Name',
            'HS Code': 'HS_Code',
            'Shipment Mode': 'Shipment_Mode',
            'BE Number': 'BE_Number',
            'BE Date': 'BE_Date',
            'Importer City': 'Importer_City',
            'Importer State': 'Importer_State',
            'Port of Origin': 'Port_of_Origin',
            'Port of Country': 'Port_of_Country'
        }
        
        # Create formatted columns BEFORE renaming
        df['Product'] = df['Product Description'].apply(clean_special_chars).str.upper()
        df['Exporter'] = df['Exporter Name'].apply(clean_special_chars).str.upper()
        
        final_cols = [
            'Shipment_Mode', 'BE_Number', 'BE_Date', 'HS_Code', 'Product_Name', 'Product', 
            'ICE', 'Importer_Name', 'Importer', 
            'QUANTITY_KG', 'Per_KG_Rate', 'Total_Value', 'Per_KG_INR', 'Total_Value_INR', 
            'Importer_City', 'Importer_State', 'Exporter_Name', 'Exporter', 
            'Port_of_Origin', 'Port_of_Country', 'CHAPTER'
        ]

    # NOW RENAME
    df.rename(columns=rename_map, inplace=True)

    # Create CHAPTER column
    df['CHAPTER'] = df.apply(lambda row: "CH-28" if str(row['HS_Code']).startswith("28") 
                                       else "CH-29" if str(row['HS_Code']).startswith("29") 
                                       else "CH-38", axis=1)
    
    # === FINAL PASS: Ensure all columns exist and have correct types ===
    for col in final_cols:
        if col not in df.columns:
            df[col] = None

    return df[final_cols]

def upload_to_sql(df, conn_str, table_name):
    engine = create_engine(conn_str)
    df.to_sql(table_name, engine, if_exists='append', index=False, chunksize=50)

# ==========================================
#                 ROUTES
# ==========================================

@app.route('/')
def index():
    # Reset state on fresh load
    df_store['raw'] = None
    df_store['synced'] = None
    df_store['final'] = None
    session.clear()
    return render_template('step1_upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files.get('file')
    data_type = request.form.get('data_type')

    if not file or file.filename == '':
        return render_template('step1_upload.html', error="Please select a file.")

    try:
        # Read and store raw data
        df = pd.read_excel(file, dtype={'IEC': str, 'ICE': str})
        
        # Normalize column names immediately
        rename_map = {'Exporter Name': 'Exporter_Name', 'Importer Name': 'Importer_Name'}
        df.rename(columns=rename_map, inplace=True)
        
        df_store['raw'] = df
        session['data_type'] = data_type # Store type in session
        
        return redirect(url_for('step2_sync'))
        
    except Exception as e:
        return render_template('step1_upload.html', error=f"Error reading Excel: {e}")

@app.route('/step2')
def step2_sync():
    if df_store['raw'] is None:
        return redirect(url_for('index'))
    
    data_type = session.get('data_type')
    
    try:
        # Perform Sync
        df_synced = sync_and_update_master(df_store['raw'].copy(), data_type)
        df_store['synced'] = df_synced
        
        # Convert to HTML for display
        table_html = df_synced.head(50).to_html(
            classes='w-full text-sm text-left text-gray-600', 
            index=False,
            border=0
        )
        
        return render_template('step2_sync.html', table_html=table_html)
    except Exception as e:
        return f"Error in Step 2: {e}"

@app.route('/step3')
def step3_preview():
    if df_store['synced'] is None:
        return redirect(url_for('step2_sync'))

    data_type = session.get('data_type')

    try:
        # Perform Final Calculations
        df_final = final_transform_logic(df_store['synced'].copy(), data_type)
        df_store['final'] = df_final
        
        table_html = df_final.head(50).to_html(
            classes='w-full text-sm text-left text-gray-600', 
            index=False, 
            border=0
        )
        
        return render_template('step3_preview.html', table_html=table_html)
    except Exception as e:
        return f"Error in Step 3: {e}"

@app.route('/upload_db', methods=['POST'])
def upload_db():
    if df_store['final'] is None:
        return redirect(url_for('index'))
        
    data_type = session.get('data_type')
    table_name = EXPORT_TABLE_NAME if data_type == 'export' else IMPORT_TABLE_NAME
    
    try:
        upload_to_sql(df_store['final'], TEST_EXIM_CONN_STR, table_name)
        return render_template('success.html')
    except Exception as e:
        return f"Error uploading to DB: {e}"

if __name__ == "__main__":
    app.run(debug=True, port=5252)