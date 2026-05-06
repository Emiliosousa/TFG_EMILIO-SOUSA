import pandas as pd
import numpy as np
import json
import os

class ProFeatureEngine:
    def __init__(self, df):
        self.df = df.copy()
        if 'Date' in self.df.columns:
            self.df['Date'] = pd.to_datetime(self.df['Date'], dayfirst=True, errors='coerce')
        self.df = self.df.sort_values(['Date'])
        
    def _calculate_base_metrics(self):
        # Fallback for older data or missing columns
        for col in ['HS', 'HST', 'AS', 'AST', 'HF', 'HY', 'HR', 'AF', 'AY', 'AR', 'HC', 'AC']:
            if col not in self.df.columns: self.df[col] = 0

        self.df['Home_Points'] = np.where(self.df['FTR'] == 'H', 3, np.where(self.df['FTR'] == 'D', 1, 0))
        self.df['Away_Points'] = np.where(self.df['FTR'] == 'A', 3, np.where(self.df['FTR'] == 'D', 1, 0))
        
        # xG Proxy
        self.df['PostMatch_Home_xG'] = (self.df['HS'] * 0.09) + (self.df['HST'] * 0.29)
        self.df['PostMatch_Away_xG'] = (self.df['AS'] * 0.09) + (self.df['AST'] * 0.29)
        
        # Goal Diff
        self.df['Goal_Diff'] = self.df['FTHG'] - self.df['FTAG']
        
        # Pressure Proxy
        self.df['Home_Possession_Est'] = 0.50 
        self.df['Away_Possession_Est'] = 0.50
        
        # Avoid div by zero
        self.df['PostMatch_Home_Pressure'] = (self.df['HF'] + self.df['HY'] + self.df['HR']) / np.maximum(self.df['Away_Possession_Est'], 0.1)
        self.df['PostMatch_Away_Pressure'] = (self.df['AF'] + self.df['AY'] + self.df['AR']) / np.maximum(self.df['Home_Possession_Est'], 0.1)

        # --- BIGDATA ENGINE v3.0 METRICS ---
        
        # 1. Field Tilt (Shots + Corners Share)
        # Denom with epsilon
        total_actions = self.df['HS'] + self.df['HC'] + self.df['AS'] + self.df['AC']
        self.df['PostMatch_Home_Field_Tilt'] = (self.df['HS'] + self.df['HC']) / (total_actions + 1e-6)
        self.df['PostMatch_Away_Field_Tilt'] = (self.df['AS'] + self.df['AC']) / (total_actions + 1e-6)

        # 1.5 Dominance (Corners Share) - NEW LEAKAGE FREE VERSION
        total_corners = self.df['HC'] + self.df['AC']
        self.df['PostMatch_Home_Dominance'] = np.where(total_corners > 0, self.df['HC'] / total_corners, 0.5)
        self.df['PostMatch_Away_Dominance'] = np.where(total_corners > 0, self.df['AC'] / total_corners, 0.5)
        
        # 2. PDO (Sustainability)
        # Formula: (GF / SoT_For) + (1 - (GA / SoT_Against))
        # Protect against div0
        h_sot = self.df['HST'].replace(0, 1)
        a_sot = self.df['AST'].replace(0, 1)
        
        self.df['PostMatch_Home_PDO'] = (self.df['FTHG'] / h_sot) + (1 - (self.df['FTAG'] / a_sot))
        # Away PDO: (Goals_Away/SoT_Away) + (1 - (Goals_Home/SoT_Home))
        self.df['PostMatch_Away_PDO'] = (self.df['FTAG'] / a_sot) + (1 - (self.df['FTHG'] / h_sot))
        
        # 3. PPDA Proxy (Intensidad Presion)
        # Formula: (Opp_Shots + Opp_Corners) / (My_Fouls + My_Cards + 1)
        h_def_actions = self.df['HF'] + self.df['HY'] + self.df['HR'] + 1
        a_def_actions = self.df['AF'] + self.df['AY'] + self.df['AR'] + 1
        
        self.df['PostMatch_Home_PPDA_Proxy'] = (self.df['AS'] + self.df['AC']) / h_def_actions
        self.df['PostMatch_Away_PPDA_Proxy'] = (self.df['HS'] + self.df['HC']) / a_def_actions
        
        # 4. Market Wisdom (Implied Prob)
        # Check B365 columns
        if 'B365H' in self.df.columns:
            self.df['Home_Market_Wisdom'] = 1 / self.df['B365H'].replace(0, 3.0) # Avoid div0
        else:
            self.df['Home_Market_Wisdom'] = 0.33
            
        if 'B365A' in self.df.columns:
            self.df['Away_Market_Wisdom'] = 1 / self.df['B365A'].replace(0, 3.0)
        else:
            self.df['Away_Market_Wisdom'] = 0.33
        
    def _rolling_features(self, window=5):
        # Columns needed for calculation
        required = ['Date', 'HomeTeam', 'AwayTeam', 'PostMatch_Home_xG', 'PostMatch_Away_xG', 'Home_Points', 'Away_Points', 
                    'PostMatch_Home_Pressure', 'PostMatch_Away_Pressure', 'Goal_Diff',
                    'PostMatch_Home_Field_Tilt', 'PostMatch_Away_Field_Tilt',
                    'PostMatch_Home_Dominance', 'PostMatch_Away_Dominance',
                    'PostMatch_Home_PDO', 'PostMatch_Away_PDO',
                    'PostMatch_Home_PPDA_Proxy', 'PostMatch_Away_PPDA_Proxy']
        
        # Filter available columns only (in case some are missing in future reuse)
        required = [c for c in required if c in self.df.columns]
        
        df_lite = self.df[required].copy()
        
        # Prepare Long Format for GroupBy
        # Note: Goal Diff for Away team is inverted (FTAG - FTHG = -(FTHG - FTAG))
        home_side = df_lite[['Date', 'HomeTeam', 'PostMatch_Home_xG', 'Home_Points', 'PostMatch_Home_Pressure', 'Goal_Diff', 'PostMatch_Home_Field_Tilt', 'PostMatch_Home_Dominance', 'PostMatch_Home_PDO', 'PostMatch_Home_PPDA_Proxy']].rename(
            columns={
                'HomeTeam': 'Team', 'PostMatch_Home_xG': 'xG', 'Home_Points': 'Pts', 'PostMatch_Home_Pressure': 'Press', 'Goal_Diff': 'GD',
                'PostMatch_Home_Field_Tilt': 'FT', 'PostMatch_Home_Dominance': 'Dom', 'PostMatch_Home_PDO': 'PDO', 'PostMatch_Home_PPDA_Proxy': 'PPDA'
            }
        )
        away_side = df_lite[['Date', 'AwayTeam', 'PostMatch_Away_xG', 'Away_Points', 'PostMatch_Away_Pressure', 'Goal_Diff', 'PostMatch_Away_Field_Tilt', 'PostMatch_Away_Dominance', 'PostMatch_Away_PDO', 'PostMatch_Away_PPDA_Proxy']].rename(
            columns={
                'AwayTeam': 'Team', 'PostMatch_Away_xG': 'xG', 'Away_Points': 'Pts', 'PostMatch_Away_Pressure': 'Press',
                'PostMatch_Away_Field_Tilt': 'FT', 'PostMatch_Away_Dominance': 'Dom', 'PostMatch_Away_PDO': 'PDO', 'PostMatch_Away_PPDA_Proxy': 'PPDA'
            }
        )
        away_side['GD'] = -away_side['Goal_Diff'] # Invert for Away
        away_side = away_side.drop(columns=['Goal_Diff'])
        
        all_matches = pd.concat([home_side, away_side]).sort_values('Date')
        grouped = all_matches.groupby('Team')
        
        # Rolling Features
        # Rolling Features
        all_matches['xG_Avg_L5'] = grouped['xG'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()).fillna(0)
        all_matches['Streak_L5'] = grouped['Pts'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).sum()).fillna(0)
        all_matches['Pressure_Avg_L5'] = grouped['Press'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()).fillna(0)
        all_matches['Goal_Diff_L5'] = grouped['GD'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).sum()).fillna(0)
        
        # --- NEW ROLLING ---
        all_matches['Field_Tilt_L5'] = grouped['FT'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()).fillna(0.5)
        all_matches['Dominance_Avg_L5'] = grouped['Dom'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()).fillna(0.5)
        # PDO (Rolling 10 as requested)
        all_matches['PDO_L5'] = grouped['PDO'].transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean()).fillna(1.0)
        all_matches['PPDA_Proxy_L5'] = grouped['PPDA'].transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()).fillna(10.0) # Default mid value
        
        # Rest Days
        all_matches['Last_Date'] = grouped['Date'].shift(1)
        all_matches['Rest_Days'] = (all_matches['Date'] - all_matches['Last_Date']).dt.days.fillna(7) # Default 7 days
        all_matches['Rest_Days'] = all_matches['Rest_Days'].clip(upper=30) # Cap at 30
        
        # Merge back Home
        cols_to_merge = ['Date', 'Team', 'xG_Avg_L5', 'Streak_L5', 'Pressure_Avg_L5', 'Goal_Diff_L5', 'Rest_Days', 'Field_Tilt_L5', 'Dominance_Avg_L5', 'PDO_L5', 'PPDA_Proxy_L5']
        
        self.df = self.df.merge(
            all_matches[cols_to_merge],
            left_on=['Date', 'HomeTeam'], right_on=['Date', 'Team'], how='left'
        ).rename(columns={
            'xG_Avg_L5': 'Home_xG_Avg_L5', 
            'Streak_L5': 'Home_Streak_L5', 
            'Pressure_Avg_L5': 'Home_Pressure_Avg_L5',
            'Goal_Diff_L5': 'Home_Goal_Diff_L5',
            'Rest_Days': 'Home_Rest_Days',
            'Field_Tilt_L5': 'Home_Field_Tilt_L5',
            'Dominance_Avg_L5': 'Home_Dominance_Avg_L5',
            'PDO_L5': 'Home_PDO_L5',
            'PPDA_Proxy_L5': 'Home_PPDA_Proxy_L5'
        }).drop(columns=['Team'])
        
        # Merge back Away
        self.df = self.df.merge(
            all_matches[cols_to_merge],
            left_on=['Date', 'AwayTeam'], right_on=['Date', 'Team'], how='left'
        ).rename(columns={
            'xG_Avg_L5': 'Away_xG_Avg_L5', 
            'Streak_L5': 'Away_Streak_L5', 
            'Pressure_Avg_L5': 'Away_Pressure_Avg_L5',
            'Goal_Diff_L5': 'Away_Goal_Diff_L5',
            'Rest_Days': 'Away_Rest_Days',
            'Field_Tilt_L5': 'Away_Field_Tilt_L5',
            'Dominance_Avg_L5': 'Away_Dominance_Avg_L5',
            'PDO_L5': 'Away_PDO_L5',
            'PPDA_Proxy_L5': 'Away_PPDA_Proxy_L5'
        }).drop(columns=['Team'])
        
    def _h2h_features(self, window=3):
        h2h_home = []
        h2h_away = []
        history = {} 
        
        for idx, row in self.df.iterrows():
            h, a = row['HomeTeam'], row['AwayTeam']
            h_pts = row['Home_Points']
            a_pts = row['Away_Points']
            pair = tuple(sorted([h, a]))
            
            if pair not in history: history[pair] = []
            past_games = history[pair]
            
            if not past_games:
                h2h_home.append(1.5) 
                h2h_away.append(1.5)
            else:
                # Home H2H points
                rel_h = [g_pts_h if g_h == h else g_pts_a for g_h, g_pts_h, g_pts_a in past_games[-window:]]
                h2h_home.append(np.mean(rel_h))
                
                # Away H2H points (inverse of what happened in that game from their perspective)
                # If H won (3pts), A got 0. If H lost (0pts), A got 3.
                rel_a = [g_pts_h if g_h == a else g_pts_a for g_h, g_pts_h, g_pts_a in past_games[-window:]]
                h2h_away.append(np.mean(rel_a))
                
            history[pair].append((h, h_pts, a_pts))
            
        self.df['Home_H2H_L3'] = h2h_home
        self.df['Away_H2H_L3'] = h2h_away

    def run(self):
        self._calculate_base_metrics()
        self._rolling_features()
        self._h2h_features()
        return self.df

def enrich_static_data(df, data_dir=None):
    """Populates FIFA and Market Value using history + new static files.
       Includes Attack, Midfield, Defense and Log Value Differentials.
    """
    
    # Resolve absolute data_dir if not provided
    if data_dir is None:
        src_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(src_dir) # LaLiga/
        data_dir = os.path.join(base_dir, 'data')
    
    # Load History
    try:
        with open(os.path.join(data_dir, 'sofifa_history.json'), 'r', encoding='utf-8') as f: sofifa_hist = json.load(f)
        with open(os.path.join(data_dir, 'transfermarkt_history.json'), 'r', encoding='utf-8') as f: tm_hist = json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load history JSONs from {data_dir}: {e}")
        sofifa_hist, tm_hist = {}, {}
        
    # Load NEW 25/26 Data
    try:
        with open(os.path.join(data_dir, 'fifa_ratings_2526.json'), 'r', encoding='utf-8') as f: fifa_now = json.load(f)
        with open(os.path.join(data_dir, 'market_values_2526.json'), 'r', encoding='utf-8') as f: tm_now = json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load 25/26 JSONs from {data_dir}: {e}")
        fifa_now, tm_now = {}, {}
        
    # Lists for new columns
    home_stats = {'ova': [], 'att': [], 'mid': [], 'def': [], 'val': []}
    away_stats = {'ova': [], 'att': [], 'mid': [], 'def': [], 'val': []}
    
    # Helper to parse old TM format
    def parse_tm_val(val_str):
        if not isinstance(val_str, str): return 10.0
        clean = val_str.replace('€', '').replace('m', '').replace('Th', '/1000').strip()
        try:
            if 'bn' in clean: return float(clean.replace('bn', '')) * 1000
            if '/1000' in clean: return float(clean.replace('/1000', '')) / 1000
            return float(clean)
        except: return 10.0

    import unicodedata
    def normalize_name(name):
        """Remove accents and lowercase for robust matching."""
        if not isinstance(name, str): return ""
        # Remove accents
        name = unicodedata.normalize('NFD', name)
        name = "".join([c for c in name if unicodedata.category(c) != 'Mn'])
        return name.lower().strip()

    def get_hist_val(team, year, dataset, key):
        if str(year) not in dataset: return None
        team_norm = normalize_name(team)
        # Use a generator to find the first match
        for item in dataset[str(year)]:
            item_team_norm = normalize_name(item.get('team', ''))
            # Fuzzy match: one contains the other
            if team_norm in item_team_norm or item_team_norm in team_norm:
                raw_val = item.get(key)
                if key == 'value': return parse_tm_val(raw_val)
                # Ensure numeric for ratings
                try: return int(raw_val)
                except: return 75
        return None

    # Mapping SP1 (CSV) -> JSON Keys (Expanded)
    NAME_MAP = {
        'Alaves': 'Deportivo Alaves', 'Almeria': 'UD Almeria', 'Ath Bilbao': 'Athletic Club',
        'Athletic Club': 'Athletic Bilbao', 'Atletico Madrid': 'Atletico de Madrid',
        'Barcelona': 'FC Barcelona', 'Betis': 'Real Betis Balompie', 'Cadiz': 'Cadiz CF',
        'Celta': 'RC Celta de Vigo', 'Celta Vigo': 'RC Celta de Vigo', 'Cordoba': 'Cordoba CF',
        'Deportivo La Coruna': 'Deportivo de La Coruna', 'Eibar': 'SD Eibar', 'Elche': 'Elche CF',
        'Espanol': 'RCD Espanyol', 'Getafe': 'Getafe CF', 'Girona': 'Girona FC', 'Granada': 'Granada CF',
        'Hercules': 'Hercules CF', 'Huesca': 'SD Huesca', 'Las Palmas': 'UD Las Palmas',
        'Leganes': 'CD Leganes', 'Levante': 'Levante UD', 'Lugo': 'CD Lugo', 'Malaga': 'Malaga CF',
        'Mallorca': 'RCD Mallorca', 'Numancia': 'CD Numancia', 'Osasuna': 'CA Osasuna',
        'Oviedo': 'Real Oviedo', 'Racing Santander': 'Racing Santander', 'Rayo Vallecano': 'Rayo Vallecano',
        'Real Madrid': 'Real Madrid', 'Real Sociedad': 'Real Sociedad', 'Recreativo': 'Recreativo de Huelva',
        'Sevilla': 'Sevilla FC', 'Sociedad': 'Real Sociedad', 'Sporting Gijon': 'Sporting de Gijon',
        'Tenerife': 'CD Tenerife', 'Valencia': 'Valencia CF', 'Vallecano': 'Rayo Vallecano',
        'Valladolid': 'Real Valladolid CF', 'Vigo': 'RC Celta de Vigo', 'Villarreal': 'Villarreal CF',
        'Villarreal CF': 'Villarreal CF', 'Ath Madrid': 'Atletico de Madrid', 'Xerez': 'Xerez CD',
        'Zaragoza': 'Real Zaragoza'
    }

    print("Populating Advanced Static Features (FIFA/TM)...")
    
    for idx, row in df.iterrows():
        season_val = row.get('Season', 2025) 
        if pd.isna(season_val): season_val = 2025
        season = int(season_val) 
        
        h_raw, a_raw = row['HomeTeam'], row['AwayTeam']
        
        # Map to JSON keys
        h = NAME_MAP.get(h_raw, h_raw)
        a = NAME_MAP.get(a_raw, a_raw)
        
        # Defaults
        h_data = {'ova': 75, 'att': 75, 'mid': 75, 'def': 75, 'val': 10.0}
        a_data = {'ova': 75, 'att': 75, 'mid': 75, 'def': 75, 'val': 10.0}
        
        # LOGIC:
        # If Season >= 2025: Use NEW JSON (Note: 25/26 JSONs currently only have Ova/Value, no Att/Mid/Def)
        # For Att/Mid/Def in 2025, we will fallback to Ova if explicit data missing, or assume average.
        
        if season >= 2025:
            # Home
            h_data['ova'] = fifa_now.get(h, fifa_now.get(h_raw, 75))
            h_data['val'] = tm_now.get(h, tm_now.get(h_raw, 50.0))
            # Fallback for detailed ratings in 2025 (since json is simple) -> Use Ova
            h_data['att'] = h_data['ova']
            h_data['mid'] = h_data['ova']
            h_data['def'] = h_data['ova']
            
            # Away
            a_data['ova'] = fifa_now.get(a, fifa_now.get(a_raw, 75))
            a_data['val'] = tm_now.get(a, tm_now.get(a_raw, 50.0))
            a_data['att'] = a_data['ova']
            a_data['mid'] = a_data['ova']
            a_data['def'] = a_data['ova']
            
        else:
            # Historical Lookup
            # STRICT LEAKAGE PREVENTION: Only look at `season` and `season-1`.
            # If we are in 2015 season, we want 2015 data (snapshot start of season).
            # Fallback to 2014 if missing. NEVER 2016.
            
            # HOME
            found = False
            for s_check in [season, season-1]:
                # Check all keys
                # We need at least 'ova' to consider it a hit
                if str(s_check) in sofifa_hist:
                     # Parse logic ... could be optimized but sticking to functional loop
                     v_ova = get_hist_val(h, s_check, sofifa_hist, 'ova')
                     if not v_ova: v_ova = get_hist_val(h_raw, s_check, sofifa_hist, 'ova')
                     
                     if v_ova:
                         h_data['ova'] = v_ova
                         # Try others
                         for k in ['att', 'mid', 'def']:
                             v = get_hist_val(h, s_check, sofifa_hist, k)
                             if not v: v = get_hist_val(h_raw, s_check, sofifa_hist, k)
                             if v: h_data[k] = v
                         
                         found = True
                         
                # Market Value
                if str(s_check) in tm_hist:
                    v_val = get_hist_val(h, s_check, tm_hist, 'value')
                    if not v_val: v_val = get_hist_val(h_raw, s_check, tm_hist, 'value')
                    if v_val: h_data['val'] = v_val
                
                if found: break

            # AWAY
            found = False
            for s_check in [season, season-1]:
                if str(s_check) in sofifa_hist:
                     v_ova = get_hist_val(a, s_check, sofifa_hist, 'ova')
                     if not v_ova: v_ova = get_hist_val(a_raw, s_check, sofifa_hist, 'ova')
                     
                     if v_ova:
                         a_data['ova'] = v_ova
                         for k in ['att', 'mid', 'def']:
                             v = get_hist_val(a, s_check, sofifa_hist, k)
                             if not v: v = get_hist_val(a_raw, s_check, sofifa_hist, k)
                             if v: a_data[k] = v
                         found = True
                         
                if str(s_check) in tm_hist:
                    v_val = get_hist_val(a, s_check, tm_hist, 'value')
                    if not v_val: v_val = get_hist_val(a_raw, s_check, tm_hist, 'value')
                    if v_val: a_data['val'] = v_val
                    
                if found: break

        # Append
        home_stats['ova'].append(h_data['ova'])
        home_stats['att'].append(h_data['att'])
        home_stats['mid'].append(h_data['mid'])
        home_stats['def'].append(h_data['def'])
        home_stats['val'].append(h_data['val'])
        
        away_stats['ova'].append(a_data['ova'])
        away_stats['att'].append(a_data['att'])
        away_stats['mid'].append(a_data['mid'])
        away_stats['def'].append(a_data['def'])
        away_stats['val'].append(a_data['val'])

    # Assign Columns
    df['Home_FIFA_Ova'] = home_stats['ova']
    df['Home_FIFA_Att'] = home_stats['att']
    df['Home_FIFA_Mid'] = home_stats['mid']
    df['Home_FIFA_Def'] = home_stats['def']
    df['Home_Market_Value'] = home_stats['val']
    
    df['Away_FIFA_Ova'] = away_stats['ova']
    df['Away_FIFA_Att'] = away_stats['att']
    df['Away_FIFA_Mid'] = away_stats['mid']
    df['Away_FIFA_Def'] = away_stats['def']
    df['Away_Market_Value'] = away_stats['val']
    
    # --- CALCULATE DIFFERENTIALS (ALPHA) ---
    df['Diff_FIFA_Ova'] = df['Home_FIFA_Ova'] - df['Away_FIFA_Ova']
    df['Diff_FIFA_Att'] = df['Home_FIFA_Att'] - df['Away_FIFA_Att']
    df['Diff_FIFA_Mid'] = df['Home_FIFA_Mid'] - df['Away_FIFA_Mid']
    df['Diff_FIFA_Def'] = df['Home_FIFA_Def'] - df['Away_FIFA_Def']
    
    # Log Value Difference (Economic disparity)
    # Log(Home) - Log(Away)
    df['Log_Value_Diff'] = np.log1p(df['Home_Market_Value']) - np.log1p(df['Away_Market_Value'])
    
    return df

def calculate_ratings(df):
    """Calculates Elo and Dixon-Coles-like Attack/Defense ratings iteratively."""
    
    elo_ratings = {team: 1500 for team in pd.concat([df['HomeTeam'], df['AwayTeam']]).unique()}
    elo_k = 30  # K=30 consistente con los notebooks de backtest
    defense_ratings = {team: 1.0 for team in elo_ratings.keys()}
    attack_ratings = {team: 1.0 for team in elo_ratings.keys()}
    
    h_elo, a_elo = [], []
    h_att, a_att = [], []
    h_def, a_def = [], []
    
    dc_lr = 0.01
    
    for idx, row in df.iterrows():
        h, a = row['HomeTeam'], row['AwayTeam']
        
        # Snapshot PRE-MATCH ratings
        he = elo_ratings.get(h, 1500)
        ae = elo_ratings.get(a, 1500)
        hat = attack_ratings.get(h, 1.0)
        hde = defense_ratings.get(h, 1.0)
        aat = attack_ratings.get(a, 1.0)
        ade = defense_ratings.get(a, 1.0)
        
        h_elo.append(he)
        a_elo.append(ae)
        h_att.append(hat)
        h_def.append(hde)
        a_att.append(aat)
        a_def.append(ade)
        
        # Skip update if match hasn't been played (FTHG is NaN)
        # Assuming FTHG NaN means future match
        if pd.isna(row.get('FTHG')) or pd.isna(row.get('FTR')):
            continue
            
        # --- UPDATE ELO ---
        score = 1.0 if row['FTR'] == 'H' else (0.5 if row['FTR'] == 'D' else 0.0)
        dr = ae - (he + 100) # Home Advantage (consistent with notebooks: ELO_HA=100)
        e_prob = 1 / (1 + 10 ** (dr / 400))
        
        new_he = he + elo_k * (score - e_prob)
        new_ae = ae + elo_k * ((1 - score) - (1 - e_prob))
        
        elo_ratings[h] = new_he
        elo_ratings[a] = new_ae
        
        # --- UPDATE DIXON-COLES ---
        fthg = row['FTHG']
        ftag = row['FTAG']
        
        pred_hg = hat * ade
        pred_ag = aat * hde
        
        err_h = fthg - pred_hg
        err_a = ftag - pred_ag
        
        attack_ratings[h] += dc_lr * err_h * ade
        defense_ratings[a] += dc_lr * err_h * hat
        
        attack_ratings[a] += dc_lr * err_a * hde
        defense_ratings[h] += dc_lr * err_a * aat

    df['Home_Elo'] = h_elo
    df['Away_Elo'] = a_elo
    df['Home_Att_Strength'] = h_att
    df['Away_Att_Strength'] = a_att
    df['Home_Def_Weakness'] = h_def
    df['Away_Def_Weakness'] = a_def
    
    return df

def generate_features(df):
    """Main pipeline execution."""
    eng = ProFeatureEngine(df)
    # 1. Cleanup Duplicates (BigDataEngine v3.0) - Forced Cleanup
    eng.df = eng.df.loc[:, ~eng.df.columns.duplicated()].copy()
    
    df = eng.run()
    # Ensure cleanup propagates after merge
    df = df.loc[:, ~df.columns.duplicated()].copy()
    
    df = enrich_static_data(df)
    df = calculate_ratings(df)
    
    # --- LEAKAGE PROTECTION (BigDataEngine v3.1) ---
    # Drop all 'PostMatch_' columns so they NEVER reach the model/dashboard
    leakage_cols = [c for c in df.columns if c.startswith('PostMatch_')]
    if leakage_cols:
        df = df.drop(columns=leakage_cols)

    # --- Aliases for model compatibility ---
    # Model was trained with Home_Elo_Calc / Away_Elo_Calc / Elo_Diff
    if 'Home_Elo' in df.columns and 'Home_Elo_Calc' not in df.columns:
        df['Home_Elo_Calc'] = df['Home_Elo']
    if 'Away_Elo' in df.columns and 'Away_Elo_Calc' not in df.columns:
        df['Away_Elo_Calc'] = df['Away_Elo']
    if 'Home_Elo_Calc' in df.columns and 'Away_Elo_Calc' in df.columns and 'Elo_Diff' not in df.columns:
        df['Elo_Diff'] = df['Home_Elo_Calc'] - df['Away_Elo_Calc']

    return df
