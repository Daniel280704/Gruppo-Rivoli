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

FILE_LAST_HOUR = "ultima_ora_ecmwf_aifs.txt"
FILENAME = "ecmwf_aifs_profile.png"

RUN_DURATION = 365
START_DELAY = -2

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

    # Controllo che tutti i livelli siano aggiornati
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
    var_list = [
        "temperature_2m", "temperature_2m_spread", "dew_point_2m",
        "temperature_925hPa", "temperature_925hPa_spread",
        "temperature_850hPa", "temperature_850hPa_spread",
        "temperature_700hPa", "temperature_700hPa_spread",
        "temperature_600hPa", "temperature_600hPa_spread",
        "temperature_500hPa", "temperature_500hPa_spread",
        "geopotential_height_925hPa", "geopotential_height_925hPa_spread",
        "geopotential_height_850hPa", "geopotential_height_850hPa_spread",
        "geopotential_height_700hPa", "geopotential_height_700hPa_spread",
        "geopotential_height_600hPa", "geopotential_height_600hPa_spread",
        "geopotential_height_500hPa", "geopotential_height_500hPa_spread"
    ]
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_aifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "past_days": 1,
        "forecast_days": 16
    }
    headers = {"User-Agent": "MeteoBot-AIFS/3.1"}

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
    print("Scaricamento dati ECMWF AIFS...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    
    # Check incrociato
    params_to_check = [
        "temperature_2m",
        "temperature_2m_spread",
        "temperature_500hPa_spread",
        "geopotential_height_500hPa"
    ]
    
    is_new, nome_run, s_idx, e_idx = estrai_limiti_run(hourly, params_to_check, utc_offset)
    if not is_new: sys.exit(0)
        
    print(f"ℹ️ Trovato nuovo run AIFS {nome_run}. Generazione del grafico esatto...")
    times = pd.to_datetime(hourly.get("time"))[s_idx : e_idx + 1]

    def get_stats(var_name):
        mean_data = hourly.get(var_name)
        if not mean_data: return None, None, None
        mean_arr = np.array([np.nan if v is None else v for v in mean_data[s_idx : e_idx + 1]], dtype=float)
        if f"{var_name}_spread" in hourly:
            spread_data = hourly.get(f"{var_name}_spread")
            spread_arr = np.array([np.nan if v is None else v for v in spread_data[s_idx : e_idx + 1]], dtype=float)
            return mean_arr, mean_arr - spread_arr, mean_arr + spread_arr
        return mean_arr, mean_arr, mean_arr

    fig, axs = plt.subplots(6, 1, figsize=(13, 26), sharex=True)

    levels_config = [
        {"lvl": "2m",     "color": "#d62728", "has_z": False, "has_dew": True}, 
        {"lvl": "925hPa", "color": "#ff7f0e", "has_z": True,  "has_dew": False},  
        {"lvl": "850hPa", "color": "#8c564b", "has_z": True,  "has_dew": False},  
        {"lvl": "700hPa", "color": "#e377c2", "has_z": True,  "has_dew": False},  
        {"lvl": "600hPa", "color": "#2ca02c", "has_z": True,  "has_dew": False},  
        {"lvl": "500hPa", "color": "#1f77b4", "has_z": True,  "has_dew": False}   
    ]

    for ax, config in zip(axs, levels_config):
        lvl = config["lvl"]
        base_color = config["color"]
        all_y_vals = []
        
        t_mean, t_min, t_max = get_stats(f"temperature_{lvl}")
        if t_mean is not None:
            ax.plot(times, t_mean, label=f'Temp {lvl}', color=base_color, linewidth=2.2, linestyle='-')
            ax.fill_between(times, t_min, t_max, color=base_color, alpha=0.15)
            all_y_vals.extend([np.nanmin(t_min), np.nanmax(t_max)])
            
            if config.get("has_dew"):
                d_mean, _, _ = get_stats(f"dew_point_{lvl}")
                if d_mean is not None:
                    ax.plot(times, d_mean, label=f'Dew Point {lvl}', color=base_color, linewidth=2.2, linestyle='--')
                    all_y_vals.extend([np.nanmin(d_mean), np.nanmax(d_mean)])
            
            abs_y_min, abs_y_max = np.nanmin(all_y_vals), np.nanmax(all_y_vals)
            y_range = abs_y_max - abs_y_min if (abs_y_max - abs_y_min) > 0 else 5.0
            pad_bottom = y_range * 1.3 if config["has_z"] else y_range * 0.15
            ax.set_ylim(abs_y_min - pad_bottom, abs_y_max + (y_range * 0.15))
            
        ax.set_ylabel(f"Temperatura °C ({lvl})", fontsize=11, color=base_color)
        ax.tick_params(axis='y', labelcolor=base_color)
        ax.grid(True, linestyle='--', alpha=0.5)

        if config["has_z"]:
            ax2 = ax.twinx() 
            z_mean, z_min, z_max = get_stats(f"geopotential_height_{lvl}")
            if z_mean is not None:
                ax2.plot(times, z_mean, label=f'Geopotenziale {lvl}', color=base_color, linewidth=2.2, linestyle='--')
                ax2.fill_between(times, z_min, z_max, color=base_color, alpha=0.08)
                abs_z_min, abs_z_max = np.nanmin(z_min), np.nanmax(z_max)
                z_range = abs_z_max - abs_z_min if (abs_z_max - abs_z_min) > 0 else 50.0
                ax2.set_ylim(abs_z_min - z_range * 0.1, abs_z_max + z_range * 1.8)
                
            ax2.set_ylabel(f"Altezza Geop. m ({lvl})", fontsize=11, color=base_color)
            ax2.tick_params(axis='y', labelcolor=base_color)
            
            lines_1, labels_1 = ax.get_legend_handles_labels()
            lines_2, labels_2 = ax2.get_legend_handles_labels()
            ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper right', fontsize=9, ncol=2)
        else:
            ax.legend(loc='upper right', fontsize=9, ncol=2 if config.get("has_dew") else 1)

    lunghezza_effettiva = len(times) - 1
    axs[-1].set_xlabel(f"Analisi ECMWF AIFS ({lunghezza_effettiva}h)   |   Data e Ora (Locale)", fontsize=13, fontweight='bold', labelpad=15)
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
        payload = {"chat_id": chat_id, "caption": f"ECMWF AIFS (mean + spread) ({nome_run})"}
        if thread_id: payload["message_thread_id"] = thread_id
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass 

if __name__ == "__main__":
    main()
