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

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_LAST_HOUR = "ultima_ora_arome.txt"
FILENAME = "arome_profile.png"
ORIZZONTE_ORE = 51

def verifica_nuovo_run(hourly_data: dict, ref_param: str) -> tuple[bool, str]:
    times = hourly_data.get("time", [])
    mean_vals = hourly_data.get(ref_param, [])
    spread_vals = hourly_data.get(f"{ref_param}_spread", [])

    if not times or not mean_vals:
        return False, ""

    idx_mean = -1
    for i in range(len(mean_vals) - 1, -1, -1):
        if mean_vals[i] is not None:
            idx_mean = i
            break

    if spread_vals:
        idx_spread = -1
        for i in range(len(spread_vals) - 1, -1, -1):
            if spread_vals[i] is not None:
                idx_spread = i
                break
        if idx_mean != idx_spread:
            return False, ""

    if idx_mean == -1:
        return False, ""

    ultima_ora_valida = times[idx_mean]

    if os.path.exists(FILE_LAST_HOUR):
        with open(FILE_LAST_HOUR, "r") as f:
            ultima_ora_salvata = f.read().strip()
        if ultima_ora_valida <= ultima_ora_salvata:
            return False, ultima_ora_valida

    with open(FILE_LAST_HOUR, "w") as f:
        f.write(ultima_ora_valida)

    return True, ultima_ora_valida

def ottieni_nome_run(ultima_ora_valida_str: str, utc_offset_sec: int, orizzonte_ore: int) -> str:
    dt_local = datetime.fromisoformat(ultima_ora_valida_str)
    dt_utc = dt_local - timedelta(seconds=utc_offset_sec)
    dt_run = dt_utc - timedelta(hours=orizzonte_ore)
    return dt_run.strftime("%H") + "Z"

def fetch_dati_con_retry() -> dict:
    URL = "https://api.open-meteo.com/v1/forecast"
    var_list = [
        "temperature_2m", "dew_point_2m",
        "precipitation", "wind_gusts_10m",
        "temperature_850hPa", "temperature_500hPa",
        "geopotential_height_850hPa", "geopotential_height_500hPa"
    ]
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "meteofrance_arome_france",
        "timezone": "Europe/Rome",
        "forecast_days": 3 
    }
    headers = {"User-Agent": "MeteoBot-AROME/2.0"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API (Tentativo {tentativo + 1}/3): {e}", file=sys.stderr)
            if tentativo < 2:
                time.sleep(15)
    return {}

def main():
    print("Scaricamento dati AROME Deterministico...")
    data = fetch_dati_con_retry()
    
    if not data:
        print("❌ Impossibile ottenere i dati dal server. Uscita silenziosa.")
        sys.exit(0)

    hourly = data.get("hourly", {})
    
    is_new, ultima_ora = verifica_nuovo_run(hourly, "temperature_2m")
    if not is_new:
        print("⏳ Nessun nuovo run completo per AROME. Uscita silenziosa.")
        sys.exit(0)
        
    utc_offset = data.get("utc_offset_seconds", 0)
    nome_run = ottieni_nome_run(ultima_ora, utc_offset, ORIZZONTE_ORE)
    
    valid_len = len([x for x in hourly.get("temperature_2m", []) if x is not None])
    print(f"ℹ️ Trovato nuovo run AROME {nome_run} ({valid_len - 1}h valide). Generazione grafico...")
    
    times = pd.to_datetime(hourly.get("time"))[:valid_len]

    def get_arr(var_name):
        arr_data = hourly.get(var_name)
        if not arr_data: return None
        return np.array([np.nan if v is None else v for v in arr_data[:valid_len]], dtype=float)

    fig, axs = plt.subplots(5, 1, figsize=(14, 25), sharex=True)

    def applica_spaziatura_asimmetrica(ax_top, ax_bot, arr_top, arr_bot):
        if arr_top is not None and not np.isnan(arr_top).all():
            arr_top_min, arr_top_max = np.nanmin(arr_top), np.nanmax(arr_top)
            r_t = arr_top_max - arr_top_min if (arr_top_max - arr_top_min) > 0 else 5.0
            ax_top.set_ylim((arr_top_max + 0.05 * r_t) - (r_t / 0.45), arr_top_max + 0.05 * r_t)
        if arr_bot is not None and not np.isnan(arr_bot).all():
            arr_bot_min, arr_bot_max = np.nanmin(arr_bot), np.nanmax(arr_bot)
            r_b = arr_bot_max - arr_bot_min if (arr_bot_max - arr_bot_min) > 0 else 5.0
            ax_bot.set_ylim(arr_bot_min - 0.05 * r_b, (arr_bot_min - 0.05 * r_b) + (r_b / 0.45))

    ax1 = axs[0]
    ax1_dew = ax1.twinx()
    t2m, dew = get_arr("temperature_2m"), get_arr("dew_point_2m")
    if t2m is not None: ax1.plot(times, t2m, color="#d62728", linewidth=2.8, label='Temp 2m (°C)')
    if dew is not None: ax1_dew.plot(times, dew, color="#2ca02c", linewidth=2.8, linestyle='-', label='Dew Point 2m (°C)')
    applica_spaziatura_asimmetrica(ax1, ax1_dew, t2m, dew)
    ax1.set_ylabel("Temperatura 2m (°C)", fontsize=11, color="#d62728", fontweight='bold')
    ax1_dew.set_ylabel("Dew Point 2m (°C)", fontsize=11, color="#2ca02c", fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.5)
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_1_dew, labels_1_dew = ax1_dew.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_1_dew, labels_1 + labels_1_dew, loc='upper left', fontsize=10, ncol=2)
    ax1.set_title("Temperatura e Punto di Rugiada al Suolo (2m)", fontsize=13, fontweight='bold')

    ax2 = axs[1]
    ax2_z = ax2.twinx()
    t850, z850 = get_arr("temperature_850hPa"), get_arr("geopotential_height_850hPa")
    if t850 is not None: ax2.plot(times, t850, color="#ff7f0e", linewidth=2.8, label='Temp 850hPa (°C)')
    if z850 is not None: ax2_z.plot(times, z850, color="#8c564b", linewidth=2.8, linestyle='--', label='Geop 850hPa (m)')
    applica_spaziatura_asimmetrica(ax2, ax2_z, t850, z850)
    ax2.set_ylabel("Temp 850hPa (°C)", fontsize=11, color="#ff7f0e", fontweight='bold')
    ax2_z.set_ylabel("Geop 850hPa (m)", fontsize=11, color="#8c564b", fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.5)
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    lines_2_z, labels_2_z = ax2_z.get_legend_handles_labels()
    ax2.legend(lines_2 + lines_2_z, labels_2 + labels_2_z, loc='upper left', fontsize=10, ncol=2)
    ax2.set_title("Sezione Bassa Troposfera (850 hPa)", fontsize=13, fontweight='bold')

    ax3 = axs[2]
    ax3_z = ax3.twinx()
    t500, z500 = get_arr("temperature_500hPa"), get_arr("geopotential_height_500hPa")
    if t500 is not None: ax3.plot(times, t500, color="#1f77b4", linewidth=2.8, label='Temp 500hPa (°C)')
    if z500 is not None: ax3_z.plot(times, z500, color="#9467bd", linewidth=2.8, linestyle='--', label='Geop 500hPa (m)')
    applica_spaziatura_asimmetrica(ax3, ax3_z, t500, z500)
    ax3.set_ylabel("Temp 500hPa (°C)", fontsize=11, color="#1f77b4", fontweight='bold')
    ax3_z.set_ylabel("Geop 500hPa (m)", fontsize=11, color="#9467bd", fontweight='bold')
    ax3.grid(True, linestyle='--', alpha=0.5)
    lines_3, labels_3 = ax3.get_legend_handles_labels()
    lines_3_z, labels_3_z = ax3_z.get_legend_handles_labels()
    ax3.legend(lines_3 + lines_3_z, labels_3 + labels_3_z, loc='upper left', fontsize=10, ncol=2)
    ax3.set_title("Sezione Media Troposfera (500 hPa)", fontsize=13, fontweight='bold')

    ax4 = axs[3]
    gust = get_arr("wind_gusts_10m")
    if gust is not None:
        ax4.plot(times, gust, color="#e377c2", linewidth=2.5, label='Raffiche di Vento (km/h)')
        ax4.set_ylim(bottom=0, top=max(np.nanmax(gust) * 1.2, 10.0))
    ax4.set_ylabel("Raffiche (km/h)", fontsize=11, color="#e377c2", fontweight='bold')
    ax4.grid(True, linestyle='--', alpha=0.5)
    ax4.legend(loc='upper left', fontsize=10)
    ax4.set_title("Vento di Raffica al Suolo (10m)", fontsize=13, fontweight='bold')

    ax5 = axs[4]
    precip = get_arr("precipitation")
    if precip is not None:
        ax5.plot(times, precip, color="#1f77b4", linewidth=2.5, label='Precipitazione (mm/h)')
        ax5.fill_between(times, 0, precip, color="#1f77b4", alpha=0.4)
        ax5.set_ylim(bottom=0, top=max(np.nanmax(precip) * 1.2, 1.0))
    ax5.set_ylabel("Pioggia (mm/h)", fontsize=11, color="#1f77b4", fontweight='bold')
    ax5.grid(True, linestyle='--', alpha=0.5)
    ax5.legend(loc='upper left', fontsize=10)
    ax5.set_title("Accumulo Orario Precipitazioni", fontsize=13, fontweight='bold')

    titolo_in_basso = f"Modello MeteoFrance AROME ({valid_len - 1}h)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=15)
    axs[-1].xaxis.set_major_locator(mdates.HourLocator(interval=6))
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:00\n%d %b'))
    axs[-1].grid(which="major", axis="x", alpha=0.6, linestyle='-')

    plt.xticks(rotation=0, ha='center')
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD")
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {
            "chat_id": chat_id, 
            "caption": f"AROME (2.5 km) ({nome_run})"
        }
        if thread_id: payload["message_thread_id"] = thread_id
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass 

if __name__ == "__main__":
    main()
