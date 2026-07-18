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

# Disabilitiamo i warning per array vuoti in fase di calcolo
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_rh_z.txt"
FILENAME = "ecmwf_rh_z_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica se SIA l'umidità SIA il geopotenziale sono stati aggiornati fino all'ultimo giorno."""
    
    # Usiamo 850hPa come livello di controllo standard
    rh_data = hourly_data.get("relative_humidity_850hPa", [])
    z_data = hourly_data.get("geopotential_height_850hPa", [])
    
    # Sicurezza: controlliamo che ci siano dati sufficienti prima di tagliare l'array
    if not rh_data or not z_data or len(rh_data) < 24:
        return False
        
    # Estraiamo solo le ultime 24 ore
    ultime_24h_rh = rh_data[-24:]
    ultime_24h_z = z_data[-24:]
    
    # Calcoliamo i due hash sulla "coda" del run
    hash_rh_attuale = hashlib.md5(str(ultime_24h_rh).encode('utf-8')).hexdigest()
    hash_z_attuale = hashlib.md5(str(ultime_24h_z).encode('utf-8')).hexdigest()
    
    # Prima esecuzione assoluta
    if not os.path.exists(FILE_HASH):
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_rh_attuale}\n{hash_z_attuale}")
        return True
        
    # Lettura vecchi hash
    with open(FILE_HASH, "r") as f:
        lines = f.read().splitlines()
        
    if len(lines) == 2:
        hash_rh_salvato = lines[0]
        hash_z_salvato = lines[1]
    else:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_rh_attuale}\n{hash_z_attuale}")
        return True

    rh_cambiato = (hash_rh_attuale != hash_rh_salvato)
    z_cambiato = (hash_z_attuale != hash_z_salvato)
    
    # CONDIZIONE RIGOROSA: La coda del run di entrambi i parametri deve essere nuova
    if rh_cambiato and z_cambiato:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_rh_attuale}\n{hash_z_attuale}")
        return True
    else:
        if rh_cambiato or z_cambiato:
            print("⏳ Rilevato aggiornamento API in corso. Attendo completamento del run ECMWF...")
        return False

def main():
    print("Scaricamento dati ECMWF (Umidità e Geopotenziale) a 14 giorni in corso...")
    
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
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-ECMWF-RH-Z/1.0"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento completo trovato. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati completi per ECMWF Ensemble Mean. Generazione grafici in corso...")
    
    times = pd.to_datetime(hourly.get("time"))

    # Invertiamo l'ordine dei livelli per la visualizzazione:
    # 200hPa in cima al grafico (sub_plot 0), 925hPa in fondo (sub_plot 8)
    plot_levels = ["200hPa", "250hPa", "300hPa", "400hPa", "500hPa", "600hPa", "700hPa", "850hPa", "925hPa"]
    
    # Palette colori identificativa per ogni quota
    level_colors = {
        "200hPa": "#9467bd", # Viola
        "250hPa": "#e377c2", # Rosa
        "300hPa": "#8c564b", # Marrone
        "400hPa": "#7f7f7f", # Grigio scuro
        "500hPa": "#1f77b4", # Blu
        "600hPa": "#2ca02c", # Verde
        "700hPa": "#bcbd22", # Oliva
        "850hPa": "#ff7f0e", # Arancione
        "925hPa": "#d62728"  # Rosso
    }

    # Creazione della matrice 9 righe x 1 colonna (Grafico molto alto per non schiacciare le righe)
    fig, axs = plt.subplots(9, 1, figsize=(14, 30), sharex=True)

    def applica_spaziatura_asimmetrica(ax_rh, ax_z, rh_arr, z_arr):
        """Umidità (RH) nel 45% superiore, Geopotenziale (Z) nel 45% inferiore."""
        
        # 1. Spaziatura Asse Umidità (Superiore)
        if rh_arr is not None and len(rh_arr) > 0 and not np.isnan(rh_arr).all():
            rh_min, rh_max = np.nanmin(rh_arr), np.nanmax(rh_arr)
            # Forza l'umidità nei limiti fisici (0-100) per chiarezza visiva se necessario, 
            # ma basiamo il range sui dati reali per enfatizzare le variazioni
            r_rh = rh_max - rh_min if (rh_max - rh_min) > 0 else 20.0
            limite_alto_rh = rh_max + 0.05 * r_rh
            # Il limite basso scende molto oltre i dati per "schiacciare" la linea verso l'alto
            limite_basso_rh = limite_alto_rh - (r_rh / 0.45)
            ax_rh.set_ylim(limite_basso_rh, limite_alto_rh)

        # 2. Spaziatura Asse Geopotenziale (Inferiore)
        if z_arr is not None and len(z_arr) > 0 and not np.isnan(z_arr).all():
            z_min, z_max = np.nanmin(z_arr), np.nanmax(z_arr)
            r_z = z_max - z_min if (z_max - z_min) > 0 else 50.0
            limite_basso_z = z_min - 0.05 * r_z
            # Il limite alto sale molto oltre i dati per "schiacciare" la linea verso il basso
            limite_alto_z = limite_basso_z + (r_z / 0.45)
            ax_z.set_ylim(limite_basso_z, limite_alto_z)

    for i, lvl in enumerate(plot_levels):
        ax = axs[i]
        ax_z = ax.twinx()
        color = level_colors[lvl]
        
        # Estrazione dati
        rh_raw = hourly.get(f"relative_humidity_{lvl}")
        z_raw = hourly.get(f"geopotential_height_{lvl}")
        
        rh_arr = np.array(rh_raw, dtype=float) if rh_raw else None
        z_arr = np.array(z_raw, dtype=float) if z_raw else None
        
        # Plot Umidità (Asse Sinistro - Linea Continua)
        if rh_arr is not None:
            ax.plot(times, rh_arr, color="#1f77b4", linewidth=2.5, linestyle='-', label=f"Umidità Rel. (%)")
            # Leggero riempimento azzurro sotto la linea di umidità per renderla più "pesante" visivamente
            ax.fill_between(times, rh_arr, np.nanmin(rh_arr), color="#1f77b4", alpha=0.15)
            
        # Plot Geopotenziale (Asse Destro - Linea Tratteggiata e Colorata per Livello)
        if z_arr is not None:
            ax_z.plot(times, z_arr, color=color, linewidth=2.5, linestyle='--', label=f"Geopotenziale {lvl}")

        # Applica il trucco matematico del 45% - 10% - 45%
        applica_spaziatura_asimmetrica(ax, ax_z, rh_arr, z_arr)
        
        # Formattazione Asse Sinistro (RH)
        ax.set_ylabel("Umid. %", fontsize=11, color="#1f77b4", fontweight='bold')
        ax.tick_params(axis='y', labelcolor="#1f77b4")
        ax.grid(True, linestyle='--', alpha=0.5)
        
        # Formattazione Asse Destro (Z)
        ax_z.set_ylabel(f"Geop. {lvl} (m)", fontsize=11, color=color, fontweight='bold')
        ax_z.tick_params(axis='y', labelcolor=color)

        # Unione Legende
        lines_1, labels_1 = ax.get_legend_handles_labels()
        lines_2, labels_2 = ax_z.get_legend_handles_labels()
        ax.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=10, ncol=2)
        
        # Titolo in alto per ogni subplot
        ax.set_title(f"Sezione {lvl}", fontsize=12, fontweight='bold', loc='right')

    # Formattazione Asse X Finale
    titolo_in_basso = "ECMWF Ensemble Mean - Colonna Atmosferica: Umidità vs Geopotenziale (14 Giorni)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=14, fontweight='bold', labelpad=15)

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
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ECMWF")

    if token and chat_id:
        print("Invio grafico su Telegram in corso...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"

        # Payload pulito senza alcuna caption
        payload = {
            "chat_id": chat_id, 
            "parse_mode": "HTML"
        }
        
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
        print("ℹ️ Credenziali Telegram mancanti, skip invio.")

if __name__ == "__main__":
    main()