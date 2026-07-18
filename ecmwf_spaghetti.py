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

# Disabilitiamo i warning per i calcoli su array temporaneamente vuoti
warnings.filterwarnings('ignore', category=RuntimeWarning)

# Coordinate esatte - Rivoli
LATITUDE = 45.07347491421504
LONGITUDE = 7.543461388723449

FILE_HASH = "ultimo_hash_ecmwf_spaghetti.txt"
FILENAME = "ecmwf_spaghetti_profile.png"

def verifica_dati_nuovi(hourly_data: dict) -> bool:
    """Verifica dinamicamente se il primo e l'ultimo membro dell'ensemble sono stati aggiornati completando il run."""
    
    # Troviamo dinamicamente tutte le chiavi dei membri (es. da member00 a member50)
    member_keys = sorted([k for k in hourly_data.keys() if k.startswith("temperature_850hPa_member")])
    
    if not member_keys:
        print("⚠️ Errore: Nessun membro Ensemble trovato nei dati scaricati.")
        return False
        
    first_key = member_keys[0]
    last_key = member_keys[-1]
    
    member_first = hourly_data.get(first_key, [])
    member_last = hourly_data.get(last_key, [])
    
    # Filtriamo i None: se il run API è in corso, le ultime ore nel JSON potrebbero essere vuote
    valid_first = [x for x in member_first if x is not None]
    valid_last = [x for x in member_last if x is not None]
    
    # Sicurezza: controlliamo di avere almeno 24 ore di dati calcolati
    if len(valid_first) < 24 or len(valid_last) < 24:
        print(f"⏳ Run in elaborazione (ore valide calcolate: {len(valid_first)}). Attendo...")
        return False
        
    # Estraiamo solo le ultime 24 ore "reali" del periodo di previsione
    ultime_24h_first = valid_first[-24:]
    ultime_24h_last = valid_last[-24:]
    
    # Calcoliamo i due hash sulla "coda" del run
    hash_first_attuale = hashlib.md5(str(ultime_24h_first).encode('utf-8')).hexdigest()
    hash_last_attuale = hashlib.md5(str(ultime_24h_last).encode('utf-8')).hexdigest()
    
    # Se il file non esiste (prima esecuzione assoluta)
    if not os.path.exists(FILE_HASH):
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_first_attuale}\n{hash_last_attuale}")
        return True
        
    # Leggiamo i vecchi hash dal file
    with open(FILE_HASH, "r") as f:
        lines = f.read().splitlines()
        
    # Setup del file se ha la lunghezza corretta
    if len(lines) == 2:
        hash_first_salvato = lines[0]
        hash_last_salvato = lines[1]
    else:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_first_attuale}\n{hash_last_attuale}")
        return True

    # Valutiamo le differenze sull'ultimo giorno noto
    first_cambiato = (hash_first_attuale != hash_first_salvato)
    last_cambiato = (hash_last_attuale != hash_last_salvato)
    
    # CONDIZIONE RIGOROSA: La coda del run di entrambi i membri estremi deve essere nuova
    if first_cambiato and last_cambiato:
        with open(FILE_HASH, "w") as f:
            f.write(f"{hash_first_attuale}\n{hash_last_attuale}")
        return True
    else:
        if first_cambiato or last_cambiato:
            print("⏳ Rilevato aggiornamento API ECMWF in corso. Attendo che tutti i membri completino il run...")
        return False

def main():
    print("Scaricamento dati ECMWF (membri Ensemble) a 14 giorni in corso...")
    
    URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
    
    # Variabili orarie
    hourly_vars = [
        "temperature_850hPa",
        "temperature_500hPa",
        "geopotential_height_850hPa",
        "geopotential_height_500hPa"
    ]

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(hourly_vars),
        "daily": "precipitation_sum",
        "models": "ecmwf_ifs025_ensemble",
        "timezone": "Europe/Rome",
        "forecast_days": 14
    }
    headers = {"User-Agent": "MeteoBot-Spaghetti/4.1"}

    try:
        response = requests.get(URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        hourly = data.get("hourly", {})
        daily = data.get("daily", {})
    except Exception as e:
        print(f"❌ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

    if not verifica_dati_nuovi(hourly):
        print("ℹ️ Nessun aggiornamento completo trovato per ECMWF Spaghetti. Elaborazione fermata.")
        sys.exit(0)
        
    print("ℹ️ Trovati nuovi dati completi per ECMWF Ensemble. Generazione del grafico in corso...")
    
    # Assi temporali separati
    hourly_times = pd.to_datetime(hourly.get("time"))
    daily_times = pd.to_datetime(daily.get("time")) + pd.Timedelta(hours=12)

    def extract_hourly_members(var_name):
        member_keys = [k for k in hourly.keys() if k.startswith(f"{var_name}_member")]
        if not member_keys:
            return None
        member_keys.sort()
        members_data = [hourly[k] for k in member_keys]
        return np.array(members_data, dtype=float)

    def extract_daily_members(var_name):
        member_keys = [k for k in daily.keys() if k.startswith(f"{var_name}_member")]
        if not member_keys:
            return None
        member_keys.sort()
        members_data = [daily[k] for k in member_keys]
        return np.array(members_data, dtype=float)

    # Estrazione matrici
    t850_members = extract_hourly_members("temperature_850hPa")
    z850_members = extract_hourly_members("geopotential_height_850hPa")
    t500_members = extract_hourly_members("temperature_500hPa")
    z500_members = extract_hourly_members("geopotential_height_500hPa")
    precip_members = extract_daily_members("precipitation_sum")

    num_members = t850_members.shape[0] if t850_members is not None else "Multipli"

    # Creazione dei 3 Subplot
    fig, axs = plt.subplots(3, 1, figsize=(14, 18), sharex=True)

    def applica_spaziatura_asimmetrica(ax_t, ax_z, t_mat, z_mat):
        """Forza la Temperatura nel 45% superiore e il Geopotenziale nel 45% inferiore del grafico."""
        if t_mat is not None:
            t_min, t_max = np.nanmin(t_mat), np.nanmax(t_mat)
            r_t = t_max - t_min if (t_max - t_min) > 0 else 5.0
            ax_t.set_ylim((t_max + 0.05 * r_t) - (r_t / 0.45), t_max + 0.05 * r_t)

        if z_mat is not None:
            z_min, z_max = np.nanmin(z_mat), np.nanmax(z_mat)
            r_z = z_max - z_min if (z_max - z_min) > 0 else 50.0
            ax_z.set_ylim(z_min - 0.05 * r_z, (z_min - 0.05 * r_z) + (r_z / 0.45))

    # ====================================================
    # 1. SUBPLOT 850 hPa (Temperatura & Geopotenziale)
    # ====================================================
    ax1 = axs[0]
    ax1_z = ax1.twinx()
    color_850 = "#d62728" 

    if t850_members is not None:
        for i in range(t850_members.shape[0]):
            ax1.plot(hourly_times, t850_members[i], color=color_850, alpha=0.15, linewidth=0.8, linestyle='-')
        t850_mean = np.nanmean(t850_members, axis=0)
        ax1.plot(hourly_times, t850_mean, color=color_850, linewidth=2.8, linestyle='-', label='Media Temp 850 hPa (°C)')

    if z850_members is not None:
        for i in range(z850_members.shape[0]):
            ax1_z.plot(hourly_times, z850_members[i], color=color_850, alpha=0.12, linewidth=0.8, linestyle='--')
        z850_mean = np.nanmean(z850_members, axis=0)
        ax1_z.plot(hourly_times, z850_mean, color=color_850, linewidth=2.8, linestyle='--', label='Media Geop 850 hPa (m)')

    applica_spaziatura_asimmetrica(ax1, ax1_z, t850_members, z850_members)

    ax1.set_ylabel("Temperatura 850 hPa (°C)", fontsize=11, color=color_850, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor=color_850)
    ax1.grid(True, linestyle='--', alpha=0.5)

    ax1_z.set_ylabel("Altezza Geopotenziale 850 hPa (m)", fontsize=11, color=color_850, fontweight='bold')
    ax1_z.tick_params(axis='y', labelcolor=color_850)

    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_1_z, labels_1_z = ax1_z.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_1_z, labels_1 + labels_1_z, loc='upper left', fontsize=10)
    ax1.set_title(f"Profilo 850 hPa - Tutti i {num_members} membri Ensemble ECMWF", fontsize=13, fontweight='bold')

    # ====================================================
    # 2. SUBPLOT 500 hPa (Temperatura & Geopotenziale)
    # ====================================================
    ax2 = axs[1]
    ax2_z = ax2.twinx()
    color_500 = "#1f77b4" 

    if t500_members is not None:
        for i in range(t500_members.shape[0]):
            ax2.plot(hourly_times, t500_members[i], color=color_500, alpha=0.15, linewidth=0.8, linestyle='-')
        t500_mean = np.nanmean(t500_members, axis=0)
        ax2.plot(hourly_times, t500_mean, color=color_500, linewidth=2.8, linestyle='-', label='Media Temp 500 hPa (°C)')

    if z500_members is not None:
        for i in range(z500_members.shape[0]):
            ax2_z.plot(hourly_times, z500_members[i], color=color_500, alpha=0.12, linewidth=0.8, linestyle='--')
        z500_mean = np.nanmean(z500_members, axis=0)
        ax2_z.plot(hourly_times, z500_mean, color=color_500, linewidth=2.8, linestyle='--', label='Media Geop 500 hPa (m)')

    applica_spaziatura_asimmetrica(ax2, ax2_z, t500_members, z500_members)

    ax2.set_ylabel("Temperatura 500 hPa (°C)", fontsize=11, color=color_500, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor=color_500)
    ax2.grid(True, linestyle='--', alpha=0.5)

    ax2_z.set_ylabel("Altezza Geopotenziale 500 hPa (m)", fontsize=11, color=color_500, fontweight='bold')
    ax2_z.tick_params(axis='y', labelcolor=color_500)

    lines_2, labels_2 = ax2.get_legend_handles_labels()
    lines_2_z, labels_2_z = ax2_z.get_legend_handles_labels()
    ax2.legend(lines_2 + lines_2_z, labels_2 + labels_2_z, loc='upper left', fontsize=10)
    ax2.set_title(f"Profilo 500 hPa - Tutti i {num_members} membri Ensemble ECMWF", fontsize=13, fontweight='bold')

    # ====================================================
    # 3. SUBPLOT PRECIPITAZIONI GIORNALIERE
    # ====================================================
    ax3 = axs[2]
    color_precip = "#158c3a" 

    if precip_members is not None:
        for i in range(precip_members.shape[0]):
            ax3.plot(daily_times, precip_members[i], marker='o', color=color_precip, alpha=0.2, markersize=4, linestyle='None')
        
        precip_mean = np.nanmean(precip_members, axis=0)
        ax3.bar(daily_times, precip_mean, color=color_precip, alpha=0.5, width=0.7, edgecolor=color_precip, linewidth=1, label='Media Precipitazioni (mm/24h)')
        
        ax3.plot([], [], marker='o', color=color_precip, alpha=0.5, linestyle='None', label=f'Scenari singoli ({num_members} membri)')

    ax3.set_ylabel("Precipitazioni Totali (mm/24h)", fontsize=11, color=color_precip, fontweight='bold')
    ax3.tick_params(axis='y', labelcolor=color_precip)
    
    p_max = np.nanmax(precip_members) if not np.isnan(precip_members).all() else 0
    ax3.set_ylim(bottom=0, top=max(p_max * 1.2, 5.0))
    ax3.grid(True, linestyle='--', alpha=0.5)
    ax3.legend(loc='upper left', fontsize=10)
    ax3.set_title("Precipitazioni Giornaliere - Accumulo Totale 24h", fontsize=13, fontweight='bold')

    # Formattazione Asse X
    titolo_in_basso = "Meteogramma Spaghetti ECMWF Ensemble IFS 0.25° (14 Giorni)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=15)

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
        
        payload = {
            "chat_id": chat_id,
            "caption": "ECMWF (mean + members)",
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
