import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_air_quality.txt"
FILENAME = "air_quality_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    sample = hourly_data.get("pm10", [])
    stringa_dati = str(sample).encode('utf-8')
    hash_attuale = hashlib.md5(stringa_dati).hexdigest()
    
    if os.path.exists(FILE_HASH):
        with open(FILE_HASH, "r") as f:
            if f.read().strip() == hash_attuale:
                return False

    with open(FILE_HASH, "w") as f:
        f.write(hash_attuale)
    return True

def main():
    print("Scaricamento dati Qualità dell'Aria in corso...")
    
    URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "pm10,pm2_5,ozone,nitrogen_dioxide",
        "timezone": "Europe/Rome"
    }
    headers = {"User-Agent": "MeteoBot-AirQuality/1.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento trovato per la Qualità dell'Aria. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati. Generazione dei grafici...")
    times = pd.to_datetime(hourly.get("time"))
    
    # Configurazione Parametri: nome, dati, colore linea, soglie [Arancione, Rosso, Viola]
    params_config = [
        {
            "id": "pm10",
            "title": "PM10 (Particolato fine \u2264 10\u03bcm)",
            "data": np.array(hourly.get("pm10", []), dtype=float),
            "color": "#1f77b4",
            "thresholds": [36, 51, 100]
        },
        {
            "id": "pm2_5",
            "title": "PM2.5 (Particolato sottile \u2264 2.5\u03bcm)",
            "data": np.array(hourly.get("pm2_5", []), dtype=float),
            "color": "#2ca02c",
            "thresholds": [26, 36, 50]
        },
        {
            "id": "nitrogen_dioxide",
            "title": "NO2 (Biossido di Azoto)",
            "data": np.array(hourly.get("nitrogen_dioxide", []), dtype=float),
            "color": "#8c564b",
            "thresholds": [141, 201, 400]
        },
        {
            "id": "ozone",
            "title": "O3 (Ozono)",
            "data": np.array(hourly.get("ozone", []), dtype=float),
            "color": "#9467bd",
            "thresholds": [85, 121, 240]
        }
    ]

    fig, axs = plt.subplots(4, 1, figsize=(13, 20), sharex=True)

    for ax, cfg in zip(axs, params_config):
        data_arr = cfg["data"]
        th_orange, th_red, th_purple = cfg["thresholds"]
        
        # Plot dei dati
        ax.plot(times, data_arr, color=cfg["color"], linewidth=2.5, label=f"Concentrazione {cfg['title']}")
        ax.fill_between(times, data_arr, color=cfg["color"], alpha=0.15)
        
        # Linee di Soglia
        ax.axhline(th_orange, color='orange', linewidth=2, linestyle='--', label=f'Allerta Arancione (>{th_orange})')
        ax.axhline(th_red, color='red', linewidth=2, linestyle='--', label=f'Allerta Rossa (>{th_red})')
        ax.axhline(th_purple, color='purple', linewidth=2.5, linestyle='-.', label=f'Pericolo Viola (>{th_purple})')
        
        ax.set_ylabel("Concentrazione (\u03bcg/m\u00b3)", fontsize=11, fontweight='bold')
        ax.set_title(cfg["title"], fontsize=13, fontweight='bold', color='#333333')
        ax.grid(True, linestyle=':', alpha=0.6)
        
        # Adattamento Dinamico asse Y: 
        # Mostriamo sempre fino alla soglia rossa per contesto, espandendo alla viola solo se i dati ci arrivano vicino
        data_max = np.nanmax(data_arr) if not np.isnan(data_arr).all() else 0
        y_top = max(data_max * 1.2, th_red * 1.2)
        if data_max > th_red:
            y_top = max(data_max * 1.2, th_purple * 1.1)
            
        ax.set_ylim(bottom=0, top=y_top)
        
        # Sposta la legenda fuori dal grafico o in posizione che non copre le linee
        ax.legend(loc='upper left', fontsize=9, ncol=2)

    # Formattazione Asse Temporale
    axs[-1].set_xlabel("Data e Ora (Fuso Orario Locale)", fontsize=12, fontweight='bold', labelpad=10)
    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axs[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12]))
    axs[-1].grid(which="minor", axis="x", alpha=0.3, linestyle=':')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')

    # --- INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ARIA") # ID della stanza specifica
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        # Prepara il pacchetto dati senza la caption
        payload = {"chat_id": chat_id}
        
        # Se c'è l'ID della stanza, lo aggiunge
        if thread_id:
            payload["message_thread_id"] = thread_id
            
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
            print("Immagine inviata con successo su Telegram!")
        except Exception as e:
            print(f"❌ Eccezione Telegram: {e}")

if __name__ == "__main__":
    main()