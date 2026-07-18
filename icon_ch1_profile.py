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

# Disabilitiamo i warning per i calcoli su array vuoti
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_icon_ch1.txt"
FILENAME = "icon_ch1_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica media e spread sull'intero array valido, adattandosi alla lunghezza del run."""
    
    temp_mean = hourly_data.get("temperature_2m", [])
    temp_spread = hourly_data.get("temperature_2m_spread", [])
    
    # Estraiamo TUTTI i dati reali, scartando i "vuoti" (None) alla fine dell'array
    valid_mean = [x for x in temp_mean if x is not None]
    valid_spread = [x for x in temp_spread if x is not None]
    
    # ICON-CH1 ha un orizzonte di 33 ore. Usiamo 30 come margine di sicurezza minimo.
    if len(valid_mean) < 30 or len(valid_spread) < 30:
        print(f"⏳ Dati insufficienti (ore valide: {len(valid_mean)}/33). Attendo run...")
        return False
        
    # Calcoliamo l'hash sull'INTERO blocco di dati validi
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
    
    # CONDIZIONE RIGOROSA: Sia la media sia lo spread dell'intero run devono essere nuovi
    if mean_cambiata and spread_cambiato:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True
    else:
        if mean_cambiata or spread_cambiato:
            print("⏳ Aggiornamento API ICON-CH1 a metà (Media o Spread non allineati). Attendo...")
        return False

def fetch_dati_con_retry() -> dict:
    """Prova a scaricare i dati per 3 volte, con pause da 15 secondi."""
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    var_list = [
        "temperature_2m", "temperature_2m_spread", "dew_point_2m",
        "precipitation", "precipitation_spread", 
        "wind_gusts_10m", "wind_gusts_10m_spread",
        "freezing_level_height", "freezing_level_height_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "meteoswiss_icon_ch1_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 2
    }
    headers = {"User-Agent": "MeteoBot-ICONCH1/1.0"}

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
    print("Scaricamento dati ICON-CH1 Ensemble Mean (2 Giorni)...")
    
    hourly = fetch_dati_con_retry()
    
    if not hourly:
        print("❌ Impossibile ottenere i dati dal server dopo 3 tentativi. Uscita silenziosa.")
        sys.exit(0)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento completo trovato per ICON-CH1. Uscita silenziosa.")
        sys.exit(0)
        
    print("ℹ️ Dati ICON-CH1 pronti e aggiornati. Generazione del grafico...")
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

    # Layout con 4 grafici
    fig, axs = plt.subplots(4, 1, figsize=(14, 20), sharex=True)

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
    # 2. SUBPLOT: Zero Termico (Freezing Level)
    # ====================================================
    ax2 = axs[1]
    
    z_mean, z_min, z_max = get_stats("freezing_level_height")

    if z_mean is not None:
        ax2.plot(times, z_mean, color="#ff7f0e", linewidth=2.5, label='Zero Termico (m)')
        ax2.fill_between(times, np.maximum(0, z_min), z_max, color="#ff7f0e", alpha=0.2)
        
        # Gestione dinamica limite Y
        abs_z_min, abs_z_max = np.nanmin(z_min), np.nanmax(z_max)
        z_range = abs_z_max - abs_z_min if (abs_z_max - abs_z_min) > 0 else 500.0
        ax2.set_ylim(max(0, abs_z_min - z_range * 0.1), abs_z_max + z_range * 0.2)

    ax2.set_ylabel("Altitudine (m)", fontsize=11, color="#ff7f0e", fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='upper left', fontsize=10)
    ax2.set_title("Quota dello Zero Termico (Freezing Level)", fontsize=13, fontweight='bold')

    # ====================================================
    # 3. SUBPLOT: Raffiche di Vento 10m
    # ====================================================
    ax3 = axs[2]
    gust_mean, gust_min, gust_max = get_stats("wind_gusts_10m")
    
    if gust_mean is not None:
        ax3.plot(times, gust_mean, color="#e377c2", linewidth=2.5, label='Raffiche di Vento (km/h)')
        ax3.fill_between(times, np.maximum(0, gust_min), gust_max, color="#e377c2", alpha=0.2)
        ax3.set_ylim(bottom=0, top=max(np.nanmax(gust_max) * 1.2, 10.0))

    ax3.set_ylabel("Raffiche (km/h)", fontsize=11, color="#e377c2", fontweight='bold')
    ax3.grid(True, linestyle='--', alpha=0.5)
    ax3.legend(loc='upper left', fontsize=10)
    ax3.set_title("Vento di Raffica al Suolo (10m)", fontsize=13, fontweight='bold')

    # ====================================================
    # 4. SUBPLOT: Precipitazioni
    # ====================================================
    ax4 = axs[3]
    precip_mean, precip_min, precip_max = get_stats("precipitation")
    
    if precip_mean is not None:
        ax4.plot(times, precip_mean, color="#1f77b4", linewidth=2.5, label='Precipitazione (mm/h)')
        ax4.fill_between(times, np.maximum(0, precip_min), precip_max, color="#1f77b4", alpha=0.3)
        ax4.set_ylim(bottom=0, top=max(np.nanmax(precip_max) * 1.2, 1.0))

    ax4.set_ylabel("Pioggia (mm/h)", fontsize=11, color="#1f77b4", fontweight='bold')
    ax4.grid(True, linestyle='--', alpha=0.5)
    ax4.legend(loc='upper left', fontsize=10)
    ax4.set_title("Accumulo Orario Precipitazioni", fontsize=13, fontweight='bold')

    # Formattazione Asse X Finale (ogni 6 ore sul breve termine)
    titolo_in_basso = "Modello MeteoSwiss ICON-CH1 Ensemble Mean (33h)   |   Data e Ora (Fuso Orario Locale)"
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
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD") 
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        # Testo strettamente richiesto: "ICON-CH1"
        payload = {
            "chat_id": chat_id, 
            "caption": "ICON-CH1"
        }
        
        if thread_id:
            payload["message_thread_id"] = thread_id

        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass 

if __name__ == "__main__":
    main()