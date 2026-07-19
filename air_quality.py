import os
import sys
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte richieste
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

# Nuovo file di appoggio per salvare solo il giorno (YYYY-MM-DD)
FILE_LAST_DAY = "ultimo_giorno_air_quality.txt"
FILENAME = "air_quality_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> tuple[bool, int]:
    """
    Verifica se il giorno dell'ultimo dato valido si è spostato in avanti.
    Ritorna un booleano e l'indice di taglio per pulire i grafici dai null.
    """
    times = hourly_data.get("time", [])
    pm10 = hourly_data.get("pm10", [])
    
    if not times or not pm10:
        return False, -1

    # Cerchiamo l'ultimo dato non nullo partendo dal fondo
    end_idx = -1
    for i in range(len(pm10) - 1, -1, -1):
        if pm10[i] is not None:
            end_idx = i
            break

    if end_idx == -1:
        return False, -1

    # Estraiamo solo i primi 10 caratteri (YYYY-MM-DD) dall'ultimo orario valido
    ultima_ora_valida = times[end_idx]
    ultimo_giorno_valido = ultima_ora_valida[:10]

    if os.path.exists(FILE_LAST_DAY):
        with open(FILE_LAST_DAY, "r") as f:
            giorno_salvato = f.read().strip()
            
        # Se il giorno finale non è andato in avanti, il run CAMS è lo stesso
        if ultimo_giorno_valido <= giorno_salvato:
            return False, -1

    # Aggiorniamo il file con il nuovo giorno finale
    with open(FILE_LAST_DAY, "w") as f:
        f.write(ultimo_giorno_valido)
        
    return True, end_idx

def main():
    print("Scaricamento dati Qualità dell'Aria (CAMS Europe) a 4 giorni...")
    
    URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    
    # Parametri esatti richiesti
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": "pm10,pm2_5,ozone,nitrogen_dioxide",
        "timezone": "auto",
        "domains": "cams_europe",
        "forecast_days": 4
    }
    headers = {"User-Agent": "MeteoBot-AirQuality/2.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    is_new, end_idx = verifica_dati_nuovi(hourly)
    
    if not is_new:
        print("ℹ️ L'orizzonte giornaliero non è avanzato. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati (Giorno aggiornato). Generazione dei grafici...")
    
    # Tagliamo l'asse temporale per escludere eventuali null finali
    times = pd.to_datetime(hourly.get("time"))[:end_idx + 1]
    
    def get_clean_array(var_name):
        arr = hourly.get(var_name, [])
        return np.array([np.nan if v is None else v for v in arr[:end_idx + 1]], dtype=float)

    # Configurazione Parametri: nome, dati, colore linea, soglie [Arancione, Rosso, Viola]
    params_config = [
        {
            "id": "pm10",
            "title": "PM10 (Particolato fine \u2264 10\u03bcm)",
            "data": get_clean_array("pm10"),
            "color": "#1f77b4",
            "thresholds": [36, 51, 100]
        },
        {
            "id": "pm2_5",
            "title": "PM2.5 (Particolato sottile \u2264 2.5\u03bcm)",
            "data": get_clean_array("pm2_5"),
            "color": "#2ca02c",
            "thresholds": [26, 36, 50]
        },
        {
            "id": "nitrogen_dioxide",
            "title": "NO2 (Biossido di Azoto)",
            "data": get_clean_array("nitrogen_dioxide"),
            "color": "#8c564b",
            "thresholds": [141, 201, 400]
        },
        {
            "id": "ozone",
            "title": "O3 (Ozono)",
            "data": get_clean_array("ozone"),
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
        data_max = np.nanmax(data_arr) if not np.isnan(data_arr).all() else 0
        y_top = max(data_max * 1.2, th_red * 1.2)
        if data_max > th_red:
            y_top = max(data_max * 1.2, th_purple * 1.1)
            
        ax.set_ylim(bottom=0, top=y_top)
        
        # Sposta la legenda fuori dal grafico
        ax.legend(loc='upper left', fontsize=9, ncol=2)

    # Formattazione Asse Temporale
    titolo_in_basso = "Modello Copernicus CAMS Europe (4 Giorni)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=10)
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
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ARIA") 
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        payload = {
            "chat_id": chat_id,
            "caption": "Copernicus CAMS Europe (Qualità Aria)"
        }
        
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
