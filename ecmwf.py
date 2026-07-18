import os
import sys
import hashlib
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf.txt"
FILENAME = "ecmwf_thermal_geopot_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se SIA la media SIA lo spread sono stati aggiornati fino all'ultimo giorno."""
    
    temp_mean = hourly_data.get("temperature_2m", [])
    temp_spread = hourly_data.get("temperature_2m_spread", [])
    
    # Sicurezza: controlliamo che ci siano dati sufficienti prima di "tagliare" l'array
    if not temp_mean or not temp_spread or len(temp_mean) < 24:
        return False
        
    # IL TRUCCO: Estraiamo solo le ultime 24 ore del periodo di previsione
    # Se l'ultimo giorno è cambiato, significa che l'API ha finito di caricare tutto il run.
    ultime_24h_mean = temp_mean[-24:]
    ultime_24h_spread = temp_spread[-24:]
    
    # Calcoliamo i due hash solo sulla "coda" del run
    hash_mean_attuale = hashlib.md5(str(ultime_24h_mean).encode('utf-8')).hexdigest()
    hash_spread_attuale = hashlib.md5(str(ultime_24h_spread).encode('utf-8')).hexdigest()
    
    # Se il file non esiste (prima esecuzione assoluta)
    if not os.path.exists(FILE_HASH):
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True
        
    # Leggiamo i vecchi hash dal file
    with open(FILE_HASH, "r") as f:
        lines = f.read().splitlines()
        
    # Setup del file se ha la lunghezza corretta
    if len(lines) == 2:
        hash_mean_salvato = lines[0]
        hash_spread_salvato = lines[1]
    else:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True

    # Valutiamo le differenze sull'ultimo giorno noto
    mean_cambiata = (hash_mean_attuale != hash_mean_salvato)
    spread_cambiato = (hash_spread_attuale != hash_spread_salvato)
    
    # CONDIZIONE RIGOROSA: La coda del run di entrambi i parametri deve essere nuova
    if mean_cambiata and spread_cambiato:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_mean_attuale}\n{hash_spread_attuale}")
        return True
    else:
        # Se solo uno è pronto o i dati stanno ancora fluendo
        if mean_cambiata or spread_cambiato:
            print("⏳ Rilevato aggiornamento API in corso. Attendo che il run raggiunga l'ultimo giorno...")
        return False

def main():
    print("Scaricamento dati ECMWF a 14 giorni (Temp + Geopotenziale + Dew Point) in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    # Lista variabili: rimosso dew_point_2m_spread poiché non calcolato per questo endpoint
    var_list = [
        "geopotential_height_925hPa", "geopotential_height_925hPa_spread",
        "geopotential_height_850hPa", "geopotential_height_850hPa_spread",
        "geopotential_height_700hPa", "geopotential_height_700hPa_spread",
        "geopotential_height_600hPa", "geopotential_height_600hPa_spread",
        "geopotential_height_500hPa", "geopotential_height_500hPa_spread",
        "temperature_2m", "temperature_2m_spread",
        "dew_point_2m",
        "temperature_925hPa", "temperature_925hPa_spread",
        "temperature_850hPa", "temperature_850hPa_spread",
        "temperature_700hPa", "temperature_700hPa_spread",
        "temperature_600hPa", "temperature_600hPa_spread",
        "temperature_500hPa", "temperature_500hPa_spread"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(var_list),
        "models": "ecmwf_ifs025_ensemble_mean",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-EnsemblePlotter/6.5"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore durante il download dei dati: {e}", file=sys.stderr)
        sys.exit(1)

    is_nuovo = verifica_dati_nuovi(hourly)
    if not is_nuovo:
        print("ℹ️ Nessun aggiornamento trovato per ECMWF. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati per ECMWF. Generazione del grafico in corso...")
    times = pd.to_datetime(hourly.get("time"))

    def get_stats(var_name):
        """Recupera media e limiti dello spread. Se non c'è spread (es. Dew Point), usa solo la media."""
        mean_data = hourly.get(var_name)
        if not mean_data:
            return None, None, None
            
        mean_arr = np.array([np.nan if v is None else v for v in mean_data], dtype=float)
        
        if f"{var_name}_spread" in hourly:
            spread_data = hourly.get(f"{var_name}_spread")
            spread_arr = np.array([np.nan if v is None else v for v in spread_data], dtype=float)
            return mean_arr, mean_arr - spread_arr, mean_arr + spread_arr
        else:
            return mean_arr, mean_arr, mean_arr

    # --- CONFIGURAZIONE GRAFICI ---
    fig, axs = plt.subplots(6, 1, figsize=(13, 26), sharex=True)

    levels_config = [
        {"lvl": "2m",     "color": "#d62728", "has_z": False, "has_dew": True}, 
        {"lvl": "925hPa", "color": "#ff7f0e", "has_z": True,  "has_dew": False},  
        {"lvl": "850hPa", "color": "#8c564b", "has_z": True,  "has_dew": False},  
        {"lvl": "700hPa", "color": "#e377c2", "has_z": True,  "has_dew": False},  
        {"lvl": "600hPa", "color": "#2ca02c", "has_z": True,  "has_dew": False},  
        {"lvl": "500hPa", "color": "#1f77b4", "has_z": True,  "has_dew": False}   
    ]

    plotted_something = False

    for ax, config in zip(axs, levels_config):
        lvl = config["lvl"]
        base_color = config["color"]
        
        all_y_vals = []
        
        # --- PLOT TEMPERATURA (Asse Y sinistro, Linea Continua) ---
        t_mean, t_min, t_max = get_stats(f"temperature_{lvl}")
        if t_mean is not None:
            ax.plot(times, t_mean, label=f'Temp {lvl}', color=base_color, linewidth=2.2, linestyle='-')
            ax.fill_between(times, t_min, t_max, color=base_color, alpha=0.15)
            plotted_something = True
            
            all_y_vals.extend([np.nanmin(t_min), np.nanmax(t_max)])
            
            # --- PLOT DEW POINT (Solo a 2m, stesso asse Y, Linea Tratteggiata) ---
            if config.get("has_dew"):
                d_mean, _, _ = get_stats(f"dew_point_{lvl}")
                if d_mean is not None:
                    ax.plot(times, d_mean, label=f'Dew Point {lvl}', color=base_color, linewidth=2.2, linestyle='--')
                    all_y_vals.extend([np.nanmin(d_mean), np.nanmax(d_mean)])
            
            # Dinamismo Asse Y (Temperatura e Dew Point)
            abs_y_min = np.nanmin(all_y_vals)
            abs_y_max = np.nanmax(all_y_vals)
            y_range = abs_y_max - abs_y_min if (abs_y_max - abs_y_min) > 0 else 5.0
            
            if config["has_z"]:
                pad_bottom = y_range * 1.3
                pad_top = y_range * 0.15
            else:
                pad_bottom = y_range * 0.15
                pad_top = y_range * 0.15
                
            ax.set_ylim(abs_y_min - pad_bottom, abs_y_max + pad_top)
            
        ax.set_ylabel(f"Temperatura °C ({lvl})", fontsize=11, color=base_color)
        ax.tick_params(axis='y', labelcolor=base_color)
        ax.grid(True, linestyle='--', alpha=0.5)

        # --- PLOT GEOPOTENZIALE (Asse Y destro, Linea Tratteggiata) ---
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

    if not plotted_something:
        print("❌ ERRORE CRITICO: Non ho potuto tracciare nessuna linea. Dati API non validi.")
        sys.exit(1)

    # --- FORMATTAZIONE ASSE X E TITOLO IN BASSO ---
    titolo_in_basso = "Analisi ECMWF (14 Giorni) - Profilo Termodinamico Verticale   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=13, fontweight='bold', labelpad=15)
    
    axs[-1].xaxis.set_major_locator(mdates.DayLocator())
    axs[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
    axs[-1].xaxis.set_minor_locator(mdates.HourLocator(byhour=[12]))
    axs[-1].grid(which="minor", axis="x", alpha=0.3, linestyle=':')

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')
    print(f"Grafico salvato come {FILENAME}")

    # --- INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ECMWF") # ID della stanza specifica
    
    if token and chat_id:
        print("Invio grafico su Telegram in corso...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        payload = {
            "chat_id": chat_id,
            "caption": "ECMWF (mean + spread)"
        }
        
        # Aggiunge l'ID della stanza se presente
        if thread_id:
            payload["message_thread_id"] = thread_id
            
        try:
            with open(FILENAME, "rb") as photo:
                res = requests.post(
                    url_telegram,
                    data=payload,
                    files={"photo": photo}
                )
                
                if res.status_code == 200:
                    print("✅ Grafico inviato con successo su Telegram!")
                else:
                    print(f"⚠️ Errore API Telegram ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"❌ Eccezione durante l'invio a Telegram: {e}")
    else:
        print("ℹ️ Credenziali Telegram (Token o Chat ID) mancanti, skip invio.")

if __name__ == "__main__":
    main()
