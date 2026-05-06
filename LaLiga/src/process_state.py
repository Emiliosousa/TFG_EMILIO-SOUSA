import json
import os
import sys

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, '..', 'state_dump.json')
OUTPUT_FILE = os.path.join(BASE_DIR, '..', 'data', 'live_odds.json')

def extract_matches(data, tournament_id=None):
    results = []
    
    matches = data.get('matches', {})
    bets = data.get('bets', {})
    odds = data.get('odds', {})
    
    print(f"Total Matches in dump: {len(matches)}")
    debug_limit = 10
    
    for mid, match in matches.items():
        # Status 'PREMATCH'
        if match.get('status') != 'PREMATCH':
            # if debug_limit > 0: print(f"Reject {mid}: Status {match.get('status')}"); debug_limit -= 1
            continue
            
        # Tournament filter
        if tournament_id is not None:
            if match.get('tournamentId') != tournament_id:
                if debug_limit > 0 and tournament_id == 36: print(f"Reject {mid}: Tornament {match.get('tournamentId')} != {tournament_id}"); debug_limit -= 1
                continue
        
        # Main Bet Validity
        main_bet_id = match.get('mainBetId')
        if not main_bet_id:
            if debug_limit > 0: print(f"Reject {mid}: No MainBetId"); debug_limit -= 1
            continue
            
        # Bet Lookup (keys are strings in JSON)
        bet = bets.get(str(main_bet_id))
        if not bet:
            if debug_limit > 0: print(f"Reject {mid}: Bet {main_bet_id} not in bets"); debug_limit -= 1
            continue
            
        outcomes = bet.get('outcomes')
        if not outcomes or len(outcomes) != 3:
            if debug_limit > 0: print(f"Reject {mid}: Outcomes invalid {outcomes}"); debug_limit -= 1
            continue
            
        # Odds Lookup
        odd1 = odds.get(str(outcomes[0]))
        oddX = odds.get(str(outcomes[1]))
        odd2 = odds.get(str(outcomes[2]))
        
        if not odd1 or not oddX or not odd2:
            if debug_limit > 0: print(f"Reject {mid}: Missing odds {outcomes}"); debug_limit -= 1
            continue
            
        # Add to results
        results.append({
            "home": match.get('competitor1Name'),
            "away": match.get('competitor2Name'),
            "1": odd1,
            "X": oddX,
            "2": odd2,
            "date": match.get('matchStart'),
            "tournament": match.get('tournamentId')
        })


        
    return results

def main():
    if not os.path.exists(STATE_FILE):
        print(f"Error: State file not found at {STATE_FILE}")
        sys.exit(1)
        
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        print("Loaded state dump.")
        
        # Attempt 1: La Liga (ID 36)
        print("Attempting to extract La Liga matches (ID 36)...")
        matches = extract_matches(data, tournament_id=36)
        
        if not matches:
            print("No La Liga matches found. Falling back to ALL PREMATCH matches.")
            matches = extract_matches(data, tournament_id=None)
            
        # Sort by date
        matches.sort(key=lambda x: x['date'])
        
        # Limit to 10
        matches = matches[:10]
        
        print(f"Found {len(matches)} matches.")
        
        # Save
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(matches, f, indent=2)
            
        print(f"Saved to {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"Error processing state: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
