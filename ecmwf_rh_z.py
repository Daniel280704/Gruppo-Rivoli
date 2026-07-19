import os
import sys
import time
import requests
import hashlib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_rh_z.txt"
FILENAME = "ecmwf_rh_z_profile.png"

def verifica_dati_nuovi(hourly_data: dict, params_to_check: list) -> tuple[bool, str, int, int]:
    times = hourly_data.get("time", [])
    if not times: return False, "", -1, -1

    now_utc = datetime.utcnow()
    
    # Determiniamo quale run stiamo elaborando in base all'ora attuale UTC.
    # Dalle 06:00 UTC alle 15:59 UTC intercettiamo il run della mattina (00Z)
    if 6 <= now_utc.hour < 16:
        nome_run = "00Z"
        run_date = now_utc.date()
        start_hour_local = 4
    else:
        # Altrimenti intercettiamo il run della sera (12Z)
        nome_run = "12Z"
        # Se lo script gira dopo la mezzanotte UTC (es. 01:27), il run 12Z appartiene al giorno prima
        if now_utc.hour < 6:
            run_date = now_utc.date() - timedelta(days=1)
        else:
            run_date = now_utc.date()
        start_hour_local = 16

    # 1. Costruiamo l'istante esatto di partenza del grafico (04:00 o 16:00)
    start_time_str = f"{run_date.strftime('%Y-%m-%d')}T{start_hour_local:02d}:00"
    
    # 2. Costruiamo l'istante esatto di fine (23:00 del 5° giorno successivo)
    end_date = run_date + timedelta(days=5)
    end_time_str = f"{end_date.strftime('%Y-%m-%d')}T23:00"

    try:
        s_idx = times.index(start_time_str)
        e_idx = times.index(end_time_str)
    except ValueError:
        return False, "", -1, -1

    # 3. Barriera di sincronizzazione: Controlliamo l'hash sulle ultime 24 ore della nostra finestra
    hash_string = ""
    for param in params_to_check:
        vals = hourly_data.get(param, [])
        if not vals or len(vals) <= e_idx: return False, "", -1, -1
        
        # Estraiamo solo le ultime 24 ore della finestra (la "coda" del run di 5 giorni)
        coda = vals[e_idx - 23 : e_idx + 1]
        
        # Se ci sono buchi/None nella coda, il run sta ancora caricando
        if any(v is None for v in coda):
            return False, "", -1, -1
            
        hash_string += str(coda)

    hash_attuale = hashlib.md5(hash_string.encode('utf-8')).hexdigest()

    # 4. Confronto Hash
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            hash_salvato = f.read().strip()
        if hash_attuale == hash_salvato:
            return False, "", -1, -1

    # Aggiorniamo l'hash e diamo il via libera
    with open(FILE_HASH, "w") as f:
        f.write(hash_attuale)

    return True, nome_run, s_idx, e_idx

def fetch_dati_con_retry() -> dict:
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    levels = ["925hPa", "850hPa", "700hPa", "600hPa", "500hPa", "400hPa", "300hPa", "250hPa", "200hPa"]
    hourly_vars = []
    for lvl in levels:
        hourly_vars.append(f"relative_humidity_{lvl}")
        hourly_vars.append(f"geopotential_height_{lvl}")

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(hourly_vars),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "past_days": 1,   # Necessario per includere i run del giorno precedente post-mezzanotte
        "forecast_days": 7 # Abbondante per coprire i 5 giorni senza errori di indice
    }
    headers = {"User-Agent": "MeteoBot-ECMWF-RH-Z/5.0"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def main():
    print("Scaricamento dati ECMWF (Umidità e Geopotenziale) a 5 Giorni...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    hourly = data.get("hourly", {})
    
    # Verifica che la colonna sia aggiornata integralmente (dal basso fino a 200hPa)
    params_to_check = [
        "relative_humidity_925hPa",
        "geopotential_height_925hPa",
        "relative_humidity_200hPa",
        "geopotential_height_200hPa"
    ]
    
    is_new, nome_run, s_idx, e_idx = verifica_dati_nuovi(hourly, params_to_check)
    if not is_new: sys.exit(0)
        
    print(f"ℹ️ Trovati nuovi dati ECMWF {nome_run}. Generazione grafici esatti sui 5 giorni...")
    
    # Taglio chirurgico dell'asse temporale
    times = pd.to_datetime(hourly.get("time"))[s_idx : e_idx + 1]

    plot_levels = ["200hPa", "250hPa", "300hPa", "400hPa", "500hPa", "600hPa", "700hPa", "850hPa", "925hPa"]
    
    level_colors = {
        "200hPa": "#9467bd", "250hPa": "#e377c2", "300hPa": "#8c564b",
        "400hPa": "#7f7f7f", "500hPa": "#1f77b4", "600hPa": "#2ca02c",
        "700hPa": "#bcbd22", "850hPa": "#ff7f0e", "925hPa": "#d62728" 
    }

    fig, axs = plt.subplots(9, 1, figsize=(14, 30), sharex=True)

    def applica_spaziatura_asimmetrica(ax_rh, ax_z, z_arr):
        ax_rh.set_ylim(100 - (100 / 0.45), 100)
        ax_rh.set_yticks([0, 25, 50, 75, 100])

        if z_arr is not None and len(z_arr) > 0 and not np.isnan(z_arr).all():
            z_min, z_max = np.nanmin(z_arr), np.nanmax(z_arr)
            r_z = z_max - z_min if (z_max - z_min) > 0 else 50.0
            limite_basso_z = z_min - 0.05 * r_z
            limite_alto_z = limite_basso_z + (r_z / 0.45)
            ax_z.set_ylim(limite_basso_z, limite_alto_z)

    for i, lvl in enumerate(plot_levels):
        ax = axs[i]
        ax_z = ax.twinx()
        color = level_colors[lvl]
        
        rh_raw = hourly.get(f"relative_humidity_{lvl}")
        z_raw = hourly.get(f"geopotential_height_{lvl}")
        
        # Taglio chirurgico dei dati usando gli indici perfetti
        rh_arr = np.array(rh_raw[s_idx : e_idx + 1], dtype=float) if rh_raw else None
        z_arr = np.array(z_raw[s_idx : e_idx + 1], dtype=float) if z_raw else None
        
        if rh_arr is not None:
            ax.plot(times, rh_arr, color="#1f77b4", linewidth=2.5, linestyle='-', label=f"Umidità Rel. (%)")
            
        if z_arr is not None:
            ax_z.plot(times, z_arr, color=color, linewidth=2.5, linestyle='--', label=f"Geopotenziale {lvl}")

        applica_spaziatura_asimmetrica(ax, ax_z, z_arr)
        
        ax.set_ylabel("Umid. %", fontsize=11, color="#1f77b4", fontweight='bold')
        ax.tick_params(axis='y', labelcolor="#1f77b4")
        ax.grid(True, linestyle='--', alpha=0.5)
        
        ax_z.set_ylabel(f"Geop. {lvl} (m)", fontsize=11, color=color, fontweight='bold')
        ax_z.tick_params(axis='y', labelcolor=color)

        lines_1, labels_1 = ax.get_legend_handles_labels()
        lines_2, labels_2 = ax_z.get_legend_handles_labels()
        ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=10, ncol=2)
        ax.set_title(f"Sezione {lvl}", fontsize=12, fontweight='bold', loc='right')

    lunghezza_effettiva = len(times) - 1
    titolo_in_basso = f"ECMWF Mean ({lunghezza_effettiva}h) - RH vs Geopotenziale (5 Giorni)   |   Data/Ora (Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=14, fontweight='bold', labelpad=15)
    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axs[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12]))
    axs[-1].grid(which="minor", axis="x", alpha=0.3, linestyle=':')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ECMWF")

    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "caption": f"ECMWF RH (mean) ({nome_run})",
            "parse_mode": "HTML"
        }
        if thread_id: payload["message_thread_id"] = thread_id
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass 

if __name__ == "__main__":
    main()
