import soccerdata as sd
import json
import os
import pandas as pd
import traceback

# Setup Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # LaLiga/
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Mapping: Standardize Output Keys (Matches naming in feature_engineering.py)
# We want the KEYS in the JSON to match what feature_engineering expects (which are the keys in this map values?)
# Actually, feature_engineering.py HAS a map from CSV_NAME -> JSON_KEY.
# So this script should produce JSONs with the JSON_KEYs (Official Names).
# We might need to map the Scraper output names to these Official Names if they differ.

# Official Names used in feature_engineering.py (Target Keys)
OFFICIAL_NAMES = [
    'Deportivo Alaves', 'Athletic Club', 'FC Barcelona', 'Real Betis Balompie', 
    'RC Celta de Vigo', 'Cadiz CF', 'Elche CF', 'RCD Espanyol', 'Getafe CF', 
    'Girona FC', 'Granada CF', 'Levante UD', 'RCD Mallorca', 'CA Osasuna', 
    'Rayo Vallecano', 'Sevilla FC', 'Real Sociedad', 'Valencia CF', 
    'Real Valladolid CF', 'Villarreal CF', 'UD Almeria', 'UD Las Palmas', 
    'CD Leganes', 'Oviedo'
]

def fetch_fifa_data():
    print("Fetching FIFA Ratings via SoccerData (SoFIFA)...")
    try:
        # Season 2025 = 2025/2026. If 2025 not available, fall back to 2024.
        for version in ["2025", "2024"]:
            try:
                sofifa = sd.SoFIFA(leagues="ESP-La Liga", versions=version)
                df_fifa = sofifa.read_team_ratings()
                break
            except (FileNotFoundError, KeyError, ValueError):
                print(f"   {version} data not found, trying previous version...")
        else:
            raise RuntimeError("No FIFA data available for 2024 or 2025")

        # df_fifa usually has MultiIndex or specific columns. 
        # Structure: index=[league, season, team], columns=[overall, attack, defense, midfield, ...]
        
        # Reset index to access team names
        df_fifa = df_fifa.reset_index()
        
        # Extract latest rating per team
        # Flatten and keep just Team and Overall
        # Column names might vary, usually 'overall'
        
        ratings_map = {}
        for _, row in df_fifa.iterrows():
            team = row['team']
            ova = int(row['overall'])
            ratings_map[team] = ova
            
        print(f"   Fetched {len(ratings_map)} team ratings.")
        return ratings_map

    except Exception as e:
        print(f"   Error fetching FIFA data: {e}")
        traceback.print_exc()
        return {}

def fetch_transfermarkt_data():
    print("Fetching Market Values via ScraperFC (Transfermarkt)...")
    try:
        try:
            import ScraperFC as sfc
        except ImportError:
            print("   ScraperFC not installed. Skipping Transfermarkt fetch.")
            return {}
        # ScraperFC usage
        tm = sfc.Transfermarkt()
        
        # Get valuations for La Liga 2025
        # normalize=True might map names?
        year = 2025
        for year in [2025, 2024]:
            try:
                df_tm = tm.scrape_league_table('ES1', year)  # ES1 is La Liga ID
                break
            except (KeyError, ValueError, Exception) as _e:
                print(f"   {year} data not found ({type(_e).__name__}), trying previous year...")
        else:
            raise RuntimeError("No Transfermarkt data available for 2024 or 2025")

        # ScraperFC returns a DataFrame with 'Team' and 'Squad Value' (or similar)
        # We need to inspect columns manually or assume standard 'Team', 'Value'
        
        # Note: ScraperFC might return raw strings like "€1.20bn". We need to parse.
        # But wait, ScraperFC usually cleans it? Let's check.
        # If it returns a DF, we assume 'Squad' and 'Market Value' columns.
        
        # Detect team and value columns (ScraperFC may change column names)
        team_col  = next((c for c in df_tm.columns if 'squad' in c.lower() or 'team' in c.lower()), None)
        value_col = next((c for c in df_tm.columns if 'value' in c.lower() or 'market' in c.lower()), None)
        if team_col is None or value_col is None:
            print(f"   Unexpected columns in Transfermarkt DF: {list(df_tm.columns)}")
            return {}
        df_tm = df_tm.rename(columns={team_col: 'Squad', value_col: 'Market Value'})

        values_map = {}
        if 'Squad' in df_tm.columns and 'Market Value' in df_tm.columns:
            for _, row in df_tm.iterrows():
                team = row['Squad']
                val_raw = row['Market Value']
                
                # Parse function (similar to feature_engineering but adapted)
                if isinstance(val_raw, (int, float)):
                    val = float(val_raw)
                else:
                    # Clean string "€1.00bn" -> 1000.0
                    clean = str(val_raw).replace('€', '').replace('m', '').replace('Th', '/1000').strip()
                    try:
                        if 'bn' in clean: 
                            val = float(clean.replace('bn', '')) * 1000
                        elif 'k' in clean or '/1000' in clean:
                            val = float(clean.replace('k', '').replace('/1000', '')) / 1000
                        else:
                            val = float(clean)
                    except (ValueError, TypeError):
                        val = 10.0  # Default
                
                values_map[team] = val

        print(f"   Fetched {len(values_map)} market values.")
        return values_map

    except Exception as e:
        print(f"   Error fetching Transfermarkt data: {e}")
        # traceback.print_exc()
        return {}

def main():
    print("--- STARTING EXTERNAL DATA FETCH ---")
    
    # 1. FIFA
    fifa_data = fetch_fifa_data()
    if fifa_data:
        path = os.path.join(DATA_DIR, 'fifa_ratings_2526.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(fifa_data, f, indent=4)
        print(f"   Saved to {path}")

    # 2. Transfermarkt
    tm_data = fetch_transfermarkt_data()
    if tm_data:
        path = os.path.join(DATA_DIR, 'market_values_2526.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(tm_data, f, indent=4)
        print(f"   Saved to {path}")
        
    print("--- FETCH COMPLETED ---")

if __name__ == "__main__":
    main()
