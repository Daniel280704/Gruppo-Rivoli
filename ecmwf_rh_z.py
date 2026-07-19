import os
import sys
import time
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_ecmwf_rh_z.txt"
FILENAME = "ecmwf_rh_z_profile.png"

# Regole ECMWF per 5 Giorni: Inizia a +2h, Finisce a +122h (5 gg + 2h)
RUN_DURATION = 122
START_DELAY = 2

def estrai_limiti_run(hourly_data: dict, hourly_params: list, utc_offset_sec: int) -> tuple[bool, str, int, int]:
    times = hourly_data.get("time", [])
    if not times: return False, "", -1, -1

    hourly_end_indices = []
    for param in hourly_params:
        vals = hourly_data.get(param, [])
        if not vals: return False, "", -1, -1
        
        end_idx = -1
        for i in range(len(vals) - 1, -1, -1):
            if vals[i] is not None:
                end_idx = i
                break
        
        if end_idx == -1: return False, "", -1, -1
        hourly_end_indices.append(end_idx)

    # Verifica incrociata
    if len(set(hourly_end_indices)) != 1:
        return False, "", -1, -1

    end_idx1 = hourly_end_indices[0]

    ultima_ora_valida_str = times[end_idx1]

    dt_end_local = datetime.fromisoformat(ultima_ora_valida_str)
    dt_end_utc = dt_end_local - timedelta(seconds=utc_offset_sec)
    dt_run_utc = dt_end_utc - timedelta(hours=RUN_DURATION)
    dt_start_utc = dt_run_utc + timedelta(hours=START_DELAY)

    dt_start_local = dt_start_utc + timedelta(seconds=utc_offset_sec)
    start_time_str = dt_start_local.strftime("%Y-%m-%dT%H:%M")
    nome_run = dt_run_utc.strftime("%H") + "Z"

    try:
        start_idx = times.index(start_time_str)
    except ValueError:
        return False, "", -1, -1

    expected_points = RUN_DURATION - START_DELAY + 1
    actual_points = end_idx1 - start_idx + 1

    if actual_points < expected_points:
        print(f"⏳ Run {nome_run} in caricamento... ({actual_points}/{expected_points} ore)")
        return False, "", -1, -1

    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida_str <= ultima_ora_salvata:
            return False, "", -1, -1

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida_str)

    return True, nome_run, start_idx, end_idx1

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
        "past_days": 1,
        "forecast_days": 6
    }
    headers = {"User-Agent": "MeteoBot-ECMWF-RH-Z/4.0"}

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
    print("Scaricamento dati ECMWF (Umidità e Geopotenziale)...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    
    # Sincronizzazione umidità in basso (925) e altissima quota (200)
    params_to_check = [
        "relative_humidity_925hPa",
        "geopotential_height_925hPa",
        "relative_humidity_200hPa",
        "geopotential_height_200hPa"
    ]
    
    is_new, nome_run, s_idx, e_idx = estrai_limiti_run(hourly, params_to_check, utc_offset)
    if not is_new: sys.exit(0)
        
    print(f"ℹ️ Trovati nuovi dati ECMWF {nome_run}. Generazione grafici esatti...")
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
    titolo_in_basso = f"ECMWF Mean ({lunghezza_effettiva}h) - RH vs Geopotenziale   |   Data/Ora (Locale)"
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
