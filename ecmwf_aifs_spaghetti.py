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

FILE_LAST_HOUR = "ultima_ora_ecmwf_aifs_spaghetti.txt"
FILENAME = "ecmwf_aifs_spaghetti_profile.png"

RUN_DURATION = 360
START_DELAY = 0

def estrai_limiti_run(hourly_data: dict, param1: str, param2: str, utc_offset_sec: int) -> tuple[bool, str, int, int]:
    times = hourly_data.get("time", [])
    vals1 = hourly_data.get(param1, [])
    vals2 = hourly_data.get(param2, [])

    if not times or not vals1 or not vals2: return False, "", -1, -1

    end_idx1 = -1
    for i in range(len(vals1) - 1, -1, -1):
        if vals1[i] is not None:
            end_idx1 = i
            break
            
    end_idx2 = -1
    for i in range(len(vals2) - 1, -1, -1):
        if vals2[i] is not None:
            end_idx2 = i
            break

    if end_idx1 == -1 or end_idx1 != end_idx2: 
        return False, "", -1, -1

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
        "models": "ecmwf_aifs025_ensemble",
        "timezone": "Europe/Rome",
        "past_days": 1,
        "forecast_days": 16
    }
    headers = {"User-Agent": "MeteoBot-AIFS-Spaghetti/2.0"}

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
    print("Scaricamento dati ECMWF AIFS Ensemble...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    hourly = data.get("hourly", {})
    daily = data.get("daily", {})
    utc_offset = data.get("utc_offset_seconds", 0)

    member_keys = sorted([k for k in hourly.keys() if k.startswith("temperature_850hPa_member")])
    if not member_keys:
        print("⚠️ Errore: Nessun membro Ensemble trovato.")
        sys.exit(0)
    
    is_new, nome_run, s_idx, e_idx = estrai_limiti_run(hourly, member_keys[0], member_keys[-1], utc_offset)
    if not is_new: sys.exit(0)
        
    print(f"ℹ️ Trovato nuovo run AIFS Spaghetti {nome_run}. Generazione grafico...")
    
    hourly_times = pd.to_datetime(hourly.get("time"))[s_idx : e_idx + 1]
    daily_times = pd.to_datetime(daily.get("time")) + pd.Timedelta(hours=12)

    def extract_hourly_members(var_name):
        keys = [k for k in hourly.keys() if k.startswith(f"{var_name}_member")]
        if not keys: return None
        keys.sort()
        members_data = [hourly[k][s_idx : e_idx + 1] for k in keys]
        return np.array(members_data, dtype=float)

    def extract_daily_members(var_name):
        keys = [k for k in daily.keys() if k.startswith(f"{var_name}_member")]
        if not keys: return None
        keys.sort()
        members_data = [daily[k] for k in keys]
        return np.array(members_data, dtype=float)

    t850_members = extract_hourly_members("temperature_850hPa")
    z850_members = extract_hourly_members("geopotential_height_850hPa")
    t500_members = extract_hourly_members("temperature_500hPa")
    z500_members = extract_hourly_members("geopotential_height_500hPa")
    precip_members = extract_daily_members("precipitation_sum")
    
    num_members = t850_members.shape[0] if t850_members is not None else "Multipli"

    fig, axs = plt.subplots(3, 1, figsize=(14, 18), sharex=True)

    def applica_spaziatura_asimmetrica(ax_t, ax_z, t_mat, z_mat):
        if t_mat is not None:
            t_min, t_max = np.nanmin(t_mat), np.nanmax(t_mat)
            r_t = t_max - t_min if (t_max - t_min) > 0 else 5.0
            ax_t.set_ylim((t_max + 0.05 * r_t) - (r_t / 0.45), t_max + 0.05 * r_t)
        if z_mat is not None:
            z_min, z_max = np.nanmin(z_mat), np.nanmax(z_mat)
            r_z = z_max - z_min if (z_max - z_min) > 0 else 50.0
            ax_z.set_ylim(z_min - 0.05 * r_z, (z_min - 0.05 * r_z) + (r_z / 0.45))

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
    ax1.set_title(f"Profilo 850 hPa - Tutti i {num_members} Membri AIFS Ensemble", fontsize=13, fontweight='bold')

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
    ax2.set_title(f"Profilo 500 hPa - Tutti i {num_members} Membri AIFS Ensemble", fontsize=13, fontweight='bold')

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

    titolo_in_basso = "Meteogramma Spaghetti ECMWF AIFS (AI) (15 Giorni)   |   Data e Ora (Fuso Orario Locale)"
    axs[-1].set_xlabel(titolo_in_basso, fontsize=12, fontweight='bold', labelpad=15)
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
        payload = {
            "chat_id": chat_id,  
            "caption": f"ECMWF AIFS Spaghetti ({nome_run})",
            "parse_mode": "HTML"
        }
        if thread_id: payload["message_thread_id"] = thread_id
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
        except Exception:
            pass 

if __name__ == "__main__":
    main()
