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

FILE_HASH = "ultimo_hash_arome.txt"
FILENAME = "arome_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica l'aggiornamento sull'intero array valido per il run deterministico."""
    
    temp = hourly_data.get("temperature_2m", [])
    
    # Estraiamo TUTTI i dati reali, scartando i "vuoti" (None) alla fine dell'array
    valid_temp = [x for x in temp if x is not None]
    
    # AROME può arrivare a 51 ore di forecast (52 elementi orari).
    # Usiamo 48 come margine di sicurezza minimo per validare un run completato.
    if len(valid_temp) < 48:
        print(f"⏳ Dati insufficienti (ore valide: {len(valid_temp)}/~51). Attendo run...")
        return False
        
    # Calcoliamo l'hash sull'INTERO blocco di dati validi, per cui se il run 
    # di colpo aggiunge ore da 48 a 51, l'hash cambia e rigenera l'immagine.
    hash_attuale = hashlib.md5(str(valid_temp).encode('utf-8')).hexdigest()
    
    if not os.path.exists(FILE_HASH):
        with open(FILE_HASH, "w") as f:
            f.write(hash_attuale)
        return True
        
    with open(FILE_HASH, "r") as f:
        hash_salvato = f.read().strip()

    if hash_attuale != hash_salvato:
        with open(FILE_HASH, "w") as f:
            f.write(hash_attuale)
        return True
    else:
        print("⏳ Nessun aggiornamento API per AROME. Uscita silenziosa.")
        return False

def fetch_dati_con_retry() -> dict:
    """Prova a scaricare i dati per 3 volte, con pause da 15 secondi."""
    URL = "https://api.open-meteo.com/v1/forecast" # Endpoint deterministico
    
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
        "forecast_days": 3 # Richiediamo 72h, poi lo script taglierà i vuoti in automatico
    }
    headers = {"User-Agent": "MeteoBot-AROME/1.2"}

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
    print("Scaricamento dati AROME Deterministico (fino a 51 ore)...")
    
    hourly = fetch_dati_con_retry()
    
    if not hourly:
        print("❌ Impossibile ottenere i dati dal server dopo 3 tentativi. Uscita silenziosa.")
        sys.exit(0)

    if not verifica_dati_nuovi(hourly):
        sys.exit(0)
        
    # Calcolo dinamico della lunghezza effettiva del run (per tagliare i None finali)
    valid_len = len([x for x in hourly.get("temperature_2m", []) if x is not None])
    
    print(f"ℹ️ Dati AROME aggiornati (Trovate {valid_len - 1} ore di previsione valide). Generazione grafico...")
    
    # Tagliamo l'asse temporale esattamente dove finiscono i dati
    times = pd.to_datetime(hourly.get("time"))[:valid_len]

    def get_arr(var_name):
        data = hourly.get(var_name)
        if not data: return None
        # Tagliamo l'array dei dati alla stessa lunghezza dinamica
        return np.array([np.nan if v is None else v for v in data[:valid_len]], dtype=float)

    # Layout con 5 grafici
    fig, axs = plt.subplots(5, 1, figsize=(14, 25), sharex=True)

    def applica_spaziatura_asimmetrica(ax_top, ax_bot, arr_top, arr_bot):
        """Top nel 45% superiore, Bot nel 45% inferiore."""
        if arr_top is not None and not np.isnan(arr_top).all():
            arr_top_min, arr_top_max = np.nanmin(arr_top), np.nanmax(arr_top)
            r_t = arr_top_max - arr_top_min if (arr_top_max - arr_top_min) > 0 else 5.0
            ax_top.set_ylim((arr_top_max + 0.05 * r_t) - (r_t / 0.45), arr_top_max + 0.05 * r_t)

        if arr_bot is not None and not np.isnan(arr_bot).all():
            arr_bot_min, arr_bot_max = np.nanmin(arr_bot), np.nanmax(arr_bot)
            r_b = arr_bot_max - arr_bot_min if (arr_bot_max - arr_bot_min) > 0 else 5.0
            ax_bot.set_ylim(arr_bot_min - 0.05 * r_b, (arr_bot_min - 0.05 * r_b) + (r_b / 0.45))

    # ====================================================
    # 1. SUBPLOT: Temp 2m vs Dew Point 2m
    # ====================================================
    ax1 = axs[0]
    ax1_dew = ax1.twinx()
    
    t2m = get_arr("temperature_2m")
    dew = get_arr("dew_point_2m")
    
    if t2m is not None:
        ax1.plot(times, t2m, color="#d62728", linewidth=2.8, label='Temp 2m (°C)')
        
    if dew is not None:
        ax1_dew.plot(times, dew, color="#2ca02c", linewidth=2.8, linestyle='-', label='Dew Point 2m (°C)')
        
    applica_spaziatura_asimmetrica(ax1, ax1_dew, t2m, dew)

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
    
    t850 = get_arr("temperature_850hPa")
    z850 = get_arr("geopotential_height_850hPa")

    if t850 is not None:
        ax2.plot(times, t850, color="#ff7f0e", linewidth=2.8, label='Temp 850hPa (°C)')
        
    if z850 is not None:
        ax2_z.plot(times, z850, color="#8c564b", linewidth=2.8, linestyle='--', label='Geop 850hPa (m)')

    applica_spaziatura_asimmetrica(ax2, ax2_z, t850, z850)

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
    
    t500 = get_arr("temperature_500hPa")
    z500 = get_arr("geopotential_height_500hPa")

    if t500 is not None:
        ax3.plot(times, t500, color="#1f77b4", linewidth=2.8, label='Temp 500hPa (°C)')
        
    if z500 is not None:
        ax3_z.plot(times, z500, color="#9467bd", linewidth=2.8, linestyle='--', label='Geop 500hPa (m)')

    applica_spaziatura_asimmetrica(ax3, ax3_z, t500, z500)

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
    gust = get_arr("wind_gusts_10m")
    
    if gust is not None:
        ax4.plot(times, gust, color="#e377c2", linewidth=2.5, label='Raffiche di Vento (km/h)')
        ax4.set_ylim(bottom=0, top=max(np.nanmax(gust) * 1.2, 10.0))

    ax4.set_ylabel("Raffiche (km/h)", fontsize=11, color="#e377c2", fontweight='bold')
    ax4.grid(True, linestyle='--', alpha=0.5)
    ax4.legend(loc='upper left', fontsize=10)
    ax4.set_title("Vento di Raffica al Suolo (10m)", fontsize=13, fontweight='bold')

    # ====================================================
    # 5. SUBPLOT: Precipitazioni
    # ====================================================
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

    # Formattazione Asse X Finale (ogni 6 ore) - Didascalia dinamica
    titolo_in_basso = f"Modello MeteoFrance AROME ({valid_len - 1}h)   |   Data e Ora (Fuso Orario Locale)"
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
        
        # Testo strettamente richiesto: "AROME (2.5 km)"
        payload = {
            "chat_id": chat_id, 
            "caption": "AROME (2.5 km)"
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
