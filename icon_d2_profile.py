import os
import sys
import hashlib
import time
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import warnings

# Disabilitiamo i warning per i calcoli su array vuoti (es. pioggia assente)
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_icon_d2.txt"
FILENAME = "icon_d2_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se SIA la media SIA lo spread sono stati aggiornati fino all'ultima ora del 3° giorno."""
    
    temp_mean = hourly_data.get("temperature_2m", [])
    temp_spread = hourly_data.get("temperature_2m_spread", [])
    
    if not temp_mean or not temp_spread or len(temp_mean) < 24:
        return False
        
    # Estraiamo le ultime 24 ore
    ultime_24h_mean = temp_mean[-24:]
    ultime_24h_spread = temp_spread[-24:]
    
    # Filtriamo eventuali valori vuoti (API non ancora completa)
    valid_mean = [x for x in ultime_24h_mean if x is not None]
    valid_spread = [x for x in ultime_24h_spread if x is not None]
    
    if len(valid_mean) < 24 or len(valid_spread) < 24:
        print(f"⏳ Dati non completi (ore valide: {len(valid_mean)}/24). Attendo run...")
        return False
        
    hash_mean_attuale = hashlib.md5(str(valid_mean).encode('utf-8')).hexdigest()
    hash_spread_attuale = hashlib.md5(str(valid_spread).encode('utf-8')).hexdigest()
    
    if not os.path.exists(FILE_HASH):
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True
        
    with open(FILE_HASH, "r") as f:
        lines = f.read().splitlines()
        
    if len(lines) == 2:
        hash_mean_salvato = lines[0]
        hash_spread_salvato = lines[1]
    else:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True

    mean_cambiata = (hash_mean_attuale != hash_mean_salvato)
    spread_cambiato = (hash_spread_attuale != hash_spread_salvato)
    
    # Condizione rigorosa
    if mean_cambiata and spread_cambiato:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True
    else:
        if mean_cambiata or spread_cambiato:
            print("⏳ Aggiornamento API ICON-D2 a metà. Attendo...")
        return False

def fetch_dati_con_retry() -> dict:
    """Prova a scaricare i dati per 3 volte, con pause da 15 secondi."""
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    var_list = [
        "temperature_2m", "temperature_2m_spread", "dew_point_2m",
        "precipitation", "precipitation_spread", 
        "wind_gusts_10m", "wind_gusts_10m_spread",
        "temperature_850hPa", "temperature_850hPa_spread",
        "temperature_500hPa", "temperature_500hPa_spread",
        "geopotential_height_850hPa", "geopotential_height_850hPa_spread",
        "geopotential_height_500hPa", "geopotential_height_500hPa_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "dwd_icon_d2_eps_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 3
    }
    headers = {"User-Agent": "MeteoBot-ICOND2/2.0"}

    for tentativo in range(3):
        try:
            response = requests.get(URL, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get("hourly", {})
        except Exception as e:
            print(f"⚠️ Errore API (Tentativo {tentativo + 1}/3): {e}", file=sys.stderr)
            if tentativo < 2:
                time.sleep(15)
    return {}

def main():
    print("Scaricamento dati ICON-D2 Ensemble Mean (3 Giorni)...")
    
    hourly = fetch_dati_con_retry()
    
    if not hourly:
        print("❌ Impossibile ottenere i dati dal server dopo 3 tentativi. Uscita silenziosa.")
        sys.exit(0)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento completo trovato per ICON-D2. Uscita silenziosa.")
        sys.exit(0)
        
    print("ℹ️ Dati ICON-D2 pronti e aggiornati. Generazione del grafico unificato...")
    times = pd.to_datetime(hourly.get("time"))

    def get_stats(var_name):
        mean_data = hourly.get(var_name)
        if not mean_data: return None, None, None
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        
        spread_key = f"{var_name}_spread"
        if spread_key in hourly:
            spread_data = hourly.get(spread_key)
            spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
            return mean_arr, mean_arr - spread_arr, mean_arr + spread_arr
        return mean_arr, mean_arr, mean_arr

    # Layout con 5 grafici
    fig, axs = plt.subplots(5, 1, figsize=(14, 25), sharex=True)

    def applica_spaziatura_asimmetrica(ax_top, ax_bot, arr_top_min, arr_top_max, arr_bot_min, arr_bot_max):
        """Top nel 45% superiore, Bot nel 45% inferiore."""
        r_t = arr_top_max - arr_top_min if (arr_top_max - arr_top_min) > 0 else 5.0
        ax_top.set_ylim((arr_top_max + 0.05 * r_t) - (r_t / 0.45), arr_top_max + 0.05 * r_t)

        r_b = arr_bot_max - arr_bot_min if (arr_bot_max - arr_bot_min) > 0 else 5.0
        ax_bot.set_ylim(arr_bot_min - 0.05 * r_b, (arr_bot_min - 0.05 * r_b) + (r_b / 0.45))

    # ====================================================
    # 1. SUBPLOT: Temp 2m vs Dew Point 2m
    # ====================================================
    ax1 = axs[0]
    ax1_dew = ax1.twinx()
    
    t2m_mean, t2m_min, t2m_max = get_stats("temperature_2m")
    dew_mean, dew_min, dew_max = get_stats("dew_point_2m")
    
    if t2m_mean is not None:
        ax1.plot(times, t2m_mean, color="#d62728", linewidth=2.5, label='Temp 2m (°C)')
        ax1.fill_between(times, t2m_min, t2m_max, color="#d62728", alpha=0.2)
        
    if dew_mean is not None:
        ax1_dew.plot(times, dew_mean, color="#2ca02c", linewidth=2.5, linestyle='-', label='Dew Point 2m (°C)')
        
    if t2m_mean is not None and dew_mean is not None:
        applica_spaziatura_asimmetrica(ax1, ax1_dew, np.nanmin(t2m_min), np.nanmax(t2m_max), np.nanmin(dew_min), np.nanmax(dew_max))

    ax1.set_ylabel("Temperatura 2m (°C)", fontsize=11, color="#d62728", fontweight='bold')
    ax1_dew.set_ylabel("Dew Point 2m (°C)", fontsize=11, color="#2ca02c", fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.5)
    
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_1_dew, labels_1_dew = ax1_dew.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_1_dew, labels_1 + labels_1_dew, loc='upper left', fontsize=10, ncol=2)
    ax1.set_title("Temperatura e Punto di Rugiada al Suolo (2m)", fontsize=13, fontweight='bold')

    # ====================================================
    # 2. SUBPLOT: Temp 850hPa vs Geopotenziale 850hPa
    # ====================================================
    ax2 = axs[1]
    ax2_z = ax2.twinx()
    
    t850_mean, t850_min, t850_max = get_stats("temperature_850hPa")
    z850_mean, z850_min, z850_max = get_stats("geopotential_height_850hPa")

    if t850_mean is not None:
        ax2.plot(times, t850_mean, color="#ff7f0e", linewidth=2.5, label='Temp 850hPa (°C)')
        ax2.fill_between(times, t850_min, t850_max, color="#ff7f0e", alpha=0.2)
        
    if z850_mean is not None:
        ax2_z.plot(times, z850_mean, color="#8c564b", linewidth=2.5, linestyle='--', label='Geop 850hPa (m)')
        ax2_z.fill_between(times, z850_min, z850_max, color="#8c564b", alpha=0.1)

    if t850_mean is not None and z850_mean is not None:
        applica_spaziatura_asimmetrica(ax2, ax2_z, np.nanmin(t850_min), np.nanmax(t850_max), np.nanmin(z850_min), np.nanmax(z850_max))

    ax2.set_ylabel("Temp 850hPa (°C)", fontsize=11, color="#ff7f0e", fontweight='bold')
    ax2_z.set_ylabel("Geop 850hPa (m)", fontsize=11, color="#8c564b", fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.5)

    lines_2, labels_2 = ax2.get_legend_handles_labels()
    lines_2_z, labels_2_z = ax2_z.get_legend_handles_labels()
    ax2.legend(lines_2 + lines_2_z, labels_2 + labels_2_z, loc='upper left', fontsize=10, ncol=2)
    ax2.set_title("Sezione Bassa Troposfera (850 hPa)", fontsize=13, fontweight='bold')

    # ====================================================
    # 3. SUBPLOT: Temp 500hPa vs Geopotenziale 500hPa
    # ====================================================
    ax3 = axs[2]
    ax3_z = ax3.twinx()
    
    t500_mean, t500_min, t500_max = get_stats("temperature_500hPa")
    z500_mean, z500_min, z500_max = get_stats("geopotential_height_500hPa")

    if t500_mean is not None:
        ax3.plot(times, t500_mean, color="#1f77b4", linewidth=2.5, label='Temp 500hPa (°C)')
        ax3.fill_between(times, t500_min, t500_max, color="#1f77b4", alpha=0.2)
        
    if z500_mean is not None:
        ax3_z.plot(times, z500_mean, color="#9467bd", linewidth=2.5, linestyle='--', label='Geop 500hPa (m)')
        ax3_z.fill_between(times, z500_min, z500_max, color="#9467bd", alpha=0.1)

    if t500_mean is not None and z500_mean is not None:
        applica_spaziatura_asimmetrica(ax3, ax3_z, np.nanmin(t500_min), np.nanmax(t500_max), np.nanmin(z500_min), np.nanmax(z500_max))

    ax3.set_ylabel("Temp 500hPa (°C)", fontsize=11, color="#1f77b4", fontweight='bold')
    ax3_z.set_ylabel("Geop 500hPa (m)", fontsize=11, color="#9467bd", fontweight='bold')
    ax3.grid(True, linestyle='--', alpha=0.5)

    lines_3, labels_3 = ax3.get_legend_handles_labels()
    lines_3_z, labels_3_z = ax3_z.get_legend_handles_labels()
    ax3.legend(lines_3 + lines_3_z, labels_3 + labels_3_z, loc='upper left', fontsize=10, ncol=2)
    ax3.set_title("Sezione Media Troposfera (500 hPa)", fontsize=13, fontweight='bold')

    # ====================================================
    # 4. SUBPLOT: Raffiche di Vento 10m
    # ====================================================
    ax4 = axs[3]
    gust_mean, gust_min, gust_max = get_stats("wind_gusts_10m")
    
    if gust_mean is not None:
        ax4.plot(times, gust_mean, color="#e377c2", linewidth=2.5, label='Raffiche di Vento (km/h)')
        ax4.fill_between(times, np.maximum(0, gust_min), gust_max, color="#e377c2", alpha=0.2)
        ax4.set_ylim(bottom=0, top=max(np.nanmax(gust_max) * 1.2, 10.0))

    ax4.set_ylabel("Raffiche (km/h)", fontsize=11, color="#e377c2", fontweight='bold')
    ax4.grid(True, linestyle='--', alpha=0.5)
    ax4.legend(loc='upper left', fontsize=10)
    ax4.set_title("Vento di Raffica al Suolo (10m)", fontsize=13, fontweight='bold')

    # ====================================================
    # 5. SUBPLOT: Precipitazioni
    # ====================================================
    ax5 = axs[4]
    precip_mean, precip_min, precip_max = get_stats("precipitation")
    
    if precip_mean is not None:
        ax5.plot(times, precip_mean, color="#1f77b4", linewidth=2.5, label='Precipitazione (mm/h)')
        ax5.fill_between(times, np.maximum(0, precip_min), precip_max, color="#1f77b4", alpha=0.3)
        ax5.set_ylim(bottom=0, top=max(np.nanmax(precip_max) * 1.2, 1.0))

    ax5.set_ylabel("Pioggia (mm/h)", fontsize=11, color="#1f77b4", fontweight='bold')
    ax5.grid(True, linestyle='--', alpha=0.5)
    ax5.legend(loc='upper left', fontsize=10)
    ax5.set_title("Accumulo Orario Precipitazioni", fontsize=13, fontweight='bold')

    # Formattazione Asse X Finale (ogni 6 ore per leggibilità sui 3 giorni)
    titolo_in_basso = "Modello ICON-D2 Ensemble Mean (72h)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=15)
    axs[-1].xaxis.set_major_locator(mdates.HourLocator(interval=6))
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:00\n%d %b'))
    axs[-1].grid(which="major", axis="x", alpha=0.6, linestyle='-')

    plt.xticks(rotation=0, ha='center')
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    # --- INVIO A TELEGRAM (SILENZIOSO SE FALLISCE) ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ICOND2") # Variabile d'ambiente opzionale per la stanza
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        # Testo strettamente richiesto: "ICON-D2"
        payload = {
            "chat_id": chat_id, 
            "caption": "ICON-D2"
        }
        
        if thread_id:
            payload["message_thread_id"] = thread_id

        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass # Silent fail richiesto

if __name__ == "__main__":
    main()