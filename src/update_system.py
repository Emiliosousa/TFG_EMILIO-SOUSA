import pandas as pd
import requests
import io
import os
import sys
import json
import random
import subprocess
from datetime import datetime


# Add src to path to import engine
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
try:
    from src.feature_engineering import generate_features
except ImportError:
    # Fallback if running from src directory
    sys.path.append(os.path.dirname(os.getcwd()))
    sys.path.append(os.path.dirname(os.getcwd()))
    from src.feature_engineering import generate_features
try:
    from src import fetch_external_data
except ImportError:
    import fetch_external_data

DATA_FILE = os.path.join(BASE_DIR, 'data', 'df_final_app.csv')
ODDS_FILE = os.path.join(BASE_DIR, 'data', 'live_odds.json')
URL_2526 = "https://www.football-data.co.uk/mmz4281/2526/SP1.csv"

def download_latest_data():
    print(f"Downloading latest data from {URL_2526}...")
    try:
        s = requests.get(URL_2526, timeout=10).content
        df_new = pd.read_csv(io.StringIO(s.decode('utf-8')))
        # Clean columns usually found in football-data
        df_new = df_new.dropna(subset=['Date', 'HomeTeam', 'AwayTeam'])
        df_new['Date'] = pd.to_datetime(df_new['Date'], dayfirst=True, errors='coerce')
        return df_new
    except Exception as e:
        print(f"Error downloading data: {e}")
        return pd.DataFrame()

def update_dataset():
    # 0. Fetch External Data (FIFA/Transfermarkt)
    print("0. Fetching External Data (FIFA/Transfermarkt)...")
    try:
        fetch_external_data.main()
    except Exception as e:
        print(f"Warning: External data fetch failed: {e}")
        # Continue anyway, using existing JSONs

    # 1. Load Existing Data
    if os.path.exists(DATA_FILE):
        print(f"Loading existing {DATA_FILE}...")
        df_old = pd.read_csv(DATA_FILE)
        df_old['Date'] = pd.to_datetime(df_old['Date'])
        
        # --- LEAKAGE FIX: STRIP ENGINEERED COLUMNS ---
        # Only keep RAW match stats. This forces a clean rebuild of all features.
        raw_cols = ['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR','HS','AS','HST','AST','HF','AF','HC','AC','HY','AY','HR','AR','B365H','B365D','B365A','Season']
        # Keep only columns that actually exist
        keep_cols = [c for c in raw_cols if c in df_old.columns]
        print(f"   -> Stripping engineered features. Keeping {len(keep_cols)} raw columns.")
        df_old = df_old[keep_cols].copy()

        # --- REMOVE CURRENT SEASON BEFORE MERGE ---
        # Cutoff: August 1st of the current calendar year if month >= 8, else previous year
        today = datetime.now()
        cutoff_year = today.year if today.month >= 8 else today.year - 1
        cutoff_date = datetime(cutoff_year, 8, 1)
        print(f"Removing existing data from current season (Date >= {cutoff_date.date()})...")
        pre_len = len(df_old)
        df_old = df_old[df_old['Date'] < cutoff_date]
        print(f"   -> Removed {pre_len - len(df_old)} rows. Remaining history: {len(df_old)} matches.")
    else:
        df_old = pd.DataFrame()

    # 2. Download New Data
    df_new = download_latest_data()
    
    if df_new.empty:
        print("No new data downloaded. Aborting update.")
        return

    # --- SAVE RAW DOWNLOAD FOR USER INSPECTION ---
    sp1_path = os.path.join(BASE_DIR, 'data', 'SP1_latest.csv')
    print(f"Saving raw fresh data to {sp1_path}...")
    try:
        df_new.to_csv(sp1_path, index=False)
    except Exception as e:
        print(f"Could not save SP1_latest.csv: {e}")

    # 3. Merge and Deduplicate
    print("Merging datasets...")
    # Standardize columns for merge
    cols_to_keep = ['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR','HS','AS','HST','AST','HF','AF','HC','AC','HY','AY','HR','AR','B365H','B365D','B365A']
    # Filter only columns that exist in new data
    cols_new = [c for c in cols_to_keep if c in df_new.columns]
    df_new_clean = df_new[cols_new].copy()
    
    # Concatenate
    if not df_old.empty:
        # Align columns
        df_combined = pd.concat([df_old, df_new_clean], ignore_index=True)
    else:
        df_combined = df_new_clean
        
    # Remove duplicates based on Match Identifier (Date + Teams)
    # We keep the LAST occurrence (assuming new data is more accurate)
    df_combined = df_combined.drop_duplicates(subset=['Date', 'HomeTeam', 'AwayTeam'], keep='last').sort_values('Date')
    
    print(f"Total Matches after merge: {len(df_combined)}")

    # 4. Run Feature Engineering (Recalculate Elo, Streaks, etc.)
    print("Running Feature Engineering Pipeline (v3.0)...")
    df_final = generate_features(df_combined)
    
    # 5. Save df_final_app.csv (legacy)
    print(f"Saving to {DATA_FILE}...")
    df_final.to_csv(DATA_FILE, index=False)
    print("Database updated successfully.")

    # 5b. Also save df_final_clean.csv (used by dashboard & V3 model)
    CLEAN_FILE = os.path.join(BASE_DIR, 'data', 'df_final_clean.csv')
    df_clean = df_final.copy()
    # Add Target column (required for model retraining / backtest)
    target_map = {'H': 2, 'D': 1, 'A': 0}
    df_clean['Target'] = df_clean['FTR'].map(target_map)
    df_clean.to_csv(CLEAN_FILE, index=False)
    print(f"Also saved to {CLEAN_FILE} ({len(df_clean)} matches, latest: {df_clean['Date'].max()})")

    # --------------------------------------------------------------------------
    # 4. Run Scraper for Live Odds (Real scraping via Puppeteer + Python Processor)
    # --------------------------------------------------------------------------
    print("\n[4/4] Fetching Live Odds from Winamax...")
    try:
        scrape_script = os.path.join(BASE_DIR, "src", "scraper_winamax_py.py")
        subprocess.run([sys.executable, scrape_script], check=True, cwd=BASE_DIR,
                       text=True, encoding='utf-8')
        print("   -> Live odds updated successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error running scraper: {e}")
    except Exception as e:
        print(f"Unexpected error in scraping: {e}")

    print("\nUpdate Process Completed Successfully!")

if __name__ == "__main__":
    update_dataset()
