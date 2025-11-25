# Master Data Sync 🔄

**Master Data Sync** is a robust ETL (Extract, Transform, Load) web application designed to automate the processing of Import/Export trade data. It streamlines the workflow of uploading raw Excel files, standardizing entity names against a Master Database, calculating currency valuations, and pushing clean data into a SQL Server warehouse.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.0%2B-green)
![Pandas](https://img.shields.io/badge/Data-Pandas-150458)
![SQLAlchemy](https://img.shields.io/badge/ORM-SQLAlchemy-red)
![TailwindCSS](https://img.shields.io/badge/Style-TailwindCSS-38bdf8)

## 🚀 Key Features

* **3-Step Wizard Interface:** A user-friendly, step-by-step process (Upload -> Sync -> Preview -> Commit).
* **Master Data Management (MDM):** Automatically validates `IEC Codes` against an `EntityMaster` database table.
    * **Auto-Learning:** Detects new entities in upload files and automatically adds them to the Master Database with standardized formatting.
    * **Name Standardization:** Expands business terms (e.g., "PVT" -> "PRIVATE") and removes special characters for consistency.
* **Automated Calculations:**
    * **Unit Conversion:** Automatically converts metric tons (MTS) to Kilograms (KG).
    * **Currency Normalization:** Calculates USD values and INR totals using historical exchange rates (via `ExchangeRate.xlsx`).
* **Schema Mapping:** Automatically renames and maps columns based on the data context (Import vs. Export).
* **SQL Integration:** Directly uploads validated, transformed data to MS SQL Server.

## 🛠️ Tech Stack

* **Backend:** Python, Flask, SQLAlchemy, PyODBC
* **Data Processing:** Pandas, NumPy
* **Frontend:** HTML5, Tailwind CSS (CDN), JavaScript
* **Database:** Microsoft SQL Server

## 📂 Project Structure

```bash
Master-Data-Sync/
├── app.py                 # Main Flask application and ETL logic
├── templates/             # HTML Templates
│   ├── base.html          # Base layout with Tailwind and Loading scripts
│   ├── step1_upload.html  # File upload interface
│   ├── step2_sync.html    # Master sync preview
│   ├── step3_preview.html # Final calculation preview
│   └── success.html       # Success message page
├── ExchangeRate.xlsx      # Required file for currency calculations
├── requirements.txt       # Python dependencies
└── README.md              # Project documentation
```

## ⚙️ Installation & Setup
### 1. Prerequisites
* Python 3.8+ installed.
* **Microsoft SQL Server** (Local or Express).
* **ODBC Driver 17 for SQL Server** installed on your machine.

### 2. Clone the Repository
```
git clone [https://github.com/yourusername/master-data-sync.git](https://github.com/yourusername/master-data-sync.git)
cd master-data-sync
```

### 3. Set Up Virtual Environment
```
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 4. Install Dependencies
```
pip install -r requirements.txt
```

### 5. Database Configuration

Open app.py and update the connection string to match your SQL Server credentials:

```
# In app.py
TEST_EXIM_CONN_STR = "mssql+pyodbc://username:password@SERVER_ADDRESS/DatabaseName?driver=ODBC+Driver+17+for+SQL+Server"
```

### 6. Required Files

Ensure you have a file named ```ExchangeRate.xlsx``` in the root directory. It must contain the following columns:
* ```Date```
* ```Category```
* ```ExchangeRateUSD``` (or relevant currency columns)

## ▶️ Usage
1. **Run the Flask Application:**
```
python app.py
```
2. **Access the Web Interface:** Open your browser and navigate to ```http://127.0.0.1:5252```.
3. **The Workflow:**
* **Step 1:** Select "Import" or "Export" and upload your raw ```.xlsx``` file.
* **Step 2:** The system syncs with ```EntityMaster```. Review the standardized names.
* **Step 3:** The system performs unit conversions and price calculations. Review the final table.
* **Finish:** Click "Upload to DB" to commit data to SQL Server.

## 🧠 Database Schema Requirements

The application expects the following tables to exist in your SQL Database:

1. ```EntityMaster```: Stores unique companies.
  * Columns: ```IEC_Code``` (PK), ```Importer/Exporter_Name```, ```Formatted_Name```.
2. ```EximImport``` & ```EximExport```: Destination tables for the cleaned data.

## 🛡️ License

This project is open-source.
