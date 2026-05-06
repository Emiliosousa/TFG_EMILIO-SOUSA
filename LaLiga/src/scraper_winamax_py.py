"""
Scraper de cuotas Winamax para La Liga usando Playwright (Python).
Reemplaza scraper_winamax.js (requería Node.js).

Uso:
    python scraper_winamax_py.py

Genera: LaLiga/data/live_odds.json
"""

import asyncio
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, 'state_dump.json')
OUTPUT_FILE = os.path.join(BASE_DIR, 'data', 'live_odds.json')

WINAMAX_URL = 'https://www.winamax.es/apuestas-deportivas/sports/1/leagues/36/2'

# ID de torneo La Liga en Winamax (verificado empíricamente)
LA_LIGA_TOURNAMENT_IDS = [36, 252, 3616]


def extract_matches_from_state(data):
    """Extrae los partidos de La Liga del estado Redux de Winamax."""
    results = []

    matches = data.get('matches', {})
    bets    = data.get('bets', {})
    odds    = data.get('odds', {})

    for mid, match in matches.items():
        if match.get('status') != 'PREMATCH':
            continue

        t_id = match.get('tournamentId')
        if t_id not in LA_LIGA_TOURNAMENT_IDS:
            continue

        main_bet_id = match.get('mainBetId')
        if not main_bet_id:
            continue

        bet = bets.get(str(main_bet_id))
        if not bet:
            continue

        outcomes = bet.get('outcomes', [])
        if len(outcomes) != 3:
            continue

        o1 = odds.get(str(outcomes[0]))
        oX = odds.get(str(outcomes[1]))
        o2 = odds.get(str(outcomes[2]))

        if not o1 or not oX or not o2:
            continue

        results.append({
            "home": match.get('competitor1Name', ''),
            "away": match.get('competitor2Name', ''),
            "1":    round(float(o1), 4),
            "X":    round(float(oX), 4),
            "2":    round(float(o2), 4),
            "date": match.get('matchStart', ''),
        })

    results.sort(key=lambda x: x['date'])
    return results


async def scrape_winamax():
    from playwright.async_api import async_playwright

    print("Lanzando navegador Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/122.0.0.0 Safari/537.36',
            locale='es-ES',
        )
        page = await context.new_page()

        print(f"Navegando a {WINAMAX_URL} ...")
        await page.goto(WINAMAX_URL, wait_until='networkidle', timeout=60000)

        # Esperar a que se carguen cuotas (botones de odds visibles)
        try:
            await page.wait_for_selector('[class*="odds"], [class*="bet-button"], .odd-value',
                                         timeout=15000)
        except Exception:
            pass  # Continuar aunque no aparezcan (la estructura puede variar)

        # Intentar extraer PRELOADED_STATE
        state = await page.evaluate("""() => {
            if (window.PRELOADED_STATE) return window.PRELOADED_STATE;
            if (window.__REDUX_STATE__) return window.__REDUX_STATE__;
            return null;
        }""")

        if not state:
            # Intentar extraer del HTML (a veces está serializado en un <script>)
            html = await page.content()
            match = re.search(r'PRELOADED_STATE\s*=\s*(\{.*?\});', html, re.DOTALL)
            if match:
                try:
                    state = json.loads(match.group(1))
                except Exception:
                    pass

        await browser.close()

    if not state:
        print("ERROR: No se pudo extraer PRELOADED_STATE de Winamax.")
        print("       Puede que el sitio use anti-bot o haya cambiado su estructura.")
        return []

    # Guardar dump (para depuración)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"Estado guardado en {STATE_FILE}")

    matches = extract_matches_from_state(state)

    if not matches:
        print("No se encontraron partidos con tournamentId conocido. "
              "Probando sin filtro de liga...")
        # Fallback: extraer todos los PREMATCH con 3 cuotas
        all_matches = []
        m_dict = state.get('matches', {})
        b_dict = state.get('bets', {})
        o_dict = state.get('odds', {})
        for mid, m in m_dict.items():
            if m.get('status') != 'PREMATCH':
                continue
            bid = m.get('mainBetId')
            if not bid:
                continue
            bet = b_dict.get(str(bid))
            if not bet:
                continue
            outs = bet.get('outcomes', [])
            if len(outs) != 3:
                continue
            o1 = o_dict.get(str(outs[0]))
            oX = o_dict.get(str(outs[1]))
            o2 = o_dict.get(str(outs[2]))
            if not (o1 and oX and o2):
                continue
            all_matches.append({
                "home": m.get('competitor1Name', ''),
                "away": m.get('competitor2Name', ''),
                "1":    round(float(o1), 4),
                "X":    round(float(oX), 4),
                "2":    round(float(o2), 4),
                "date": m.get('matchStart', ''),
                "tournament": m.get('tournamentId'),
            })
        all_matches.sort(key=lambda x: x['date'])
        matches = all_matches[:10]
        print(f"  -> {len(matches)} partidos extraídos (sin filtro de liga). "
              f"Revisa 'tournament' para identificar el ID correcto de La Liga.")

    return matches


def main():
    matches = asyncio.run(scrape_winamax())

    if not matches:
        print("No se obtuvieron partidos. live_odds.json no actualizado.")
        sys.exit(1)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(matches, f, indent=2, ensure_ascii=True)  # ASCII-safe: evita problemas de encoding en Windows

    print(f"\n{len(matches)} partidos guardados en {OUTPUT_FILE}")
    for m in matches:
        print(f"  {m['home']} vs {m['away']}  "
              f"1:{m['1']}  X:{m['X']}  2:{m['2']}")


if __name__ == '__main__':
    main()
