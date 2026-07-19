import os
import sys
import requests
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.colors as mcolors
from datetime import datetime
import warnings

# Ignora i warning sulle celle vuote (NaN) di numpy e matplotlib
warnings.filterwarnings('ignore')

FILENAME = "icon_d2_meteogram.png"

# URL della tua query completa (modello deterministico)
URL = "https://api.open-meteo.com/v1/forecast?latitude=45.0707&longitude=7.5146&hourly=temperature_975hPa,temperature_1000hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa,temperature_700hPa,temperature_600hPa,temperature_500hPa,relative_humidity_1000hPa,relative_humidity_975hPa,relative_humidity_950hPa,relative_humidity_925hPa,relative_humidity_850hPa,relative_humidity_900hPa,relative_humidity_800hPa,relative_humidity_700hPa,relative_humidity_600hPa,relative_humidity_500hPa,relative_humidity_400hPa,relative_humidity_300hPa,relative_humidity_250hPa,relative_humidity_200hPa,temperature_300hPa,temperature_400hPa,temperature_250hPa,temperature_200hPa,wind_speed_1000hPa,wind_speed_975hPa,wind_speed_950hPa,wind_speed_900hPa,wind_speed_925hPa,wind_speed_850hPa,wind_speed_800hPa,wind_speed_700hPa,wind_speed_600hPa,wind_speed_500hPa,wind_speed_400hPa,wind_speed_300hPa,wind_speed_250hPa,wind_speed_200hPa,geopotential_height_1000hPa,geopotential_height_975hPa,geopotential_height_950hPa,geopotential_height_900hPa,geopotential_height_925hPa,geopotential_height_850hPa,geopotential_height_800hPa,geopotential_height_700hPa,geopotential_height_500hPa,geopotential_height_600hPa,geopotential_height_400hPa,geopotential_height_250hPa,geopotential_height_300hPa,geopotential_height_200hPa,wind_direction_1000hPa,wind_direction_975hPa,wind_direction_925hPa,wind_direction_950hPa,wind_direction_900hPa,wind_direction_850hPa,wind_direction_800hPa,wind_direction_600hPa,wind_direction_700hPa,wind_direction_400hPa,wind_direction_500hPa,wind_direction_300hPa,wind_direction_250hPa,wind_direction_200hPa&models=dwd_icon_d2&timezone=auto&forecast_days=3"

def fetch_dati():
    headers = {"User-Agent": "MeteoBot-CrossSection/1.0"}
    try:
        response = requests.get(URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

def build_safe_array(data_list):
    # Converte in Numpy array gestendo gli eventuali None come NaN
    return np.array([np.nan if v is None else v for v in data_list], dtype=float)

def main():
    print("Scaricamento dati Profilo Atmosferico ICON-D2...")
    data = fetch_dati()
    hourly = data.get("hourly", {})
    if not hourly:
        print("Dati hourly non trovati.")
        sys.exit(1)

    times = pd.to_datetime(hourly.get("time"))
    
    # IMPORTANTE: I livelli devono essere CRESCENTI per la funzione contourf di Matplotlib
    # Invertiremo poi l'asse Y sul grafico visivo.
    levels = [200, 250, 300, 400, 500, 600, 700, 800, 850, 900, 925, 950, 975, 1000]

    # Inizializza matrici 2D (Livelli di Pressione x Tempo)
    T_mat = np.array([build_safe_array(hourly.get(f"temperature_{p}hPa")) for p in levels])
    RH_mat = np.array([build_safe_array(hourly.get(f"relative_humidity_{p}hPa")) for p in levels])
    WS_mat = np.array([build_safe_array(hourly.get(f"wind_speed_{p}hPa")) for p in levels])
    WD_mat = np.array([build_safe_array(hourly.get(f"wind_direction_{p}hPa")) for p in levels])

    # Convertiamo Vento per i Barbi (in Nodi e componenti U/V)
    WS_knots = WS_mat / 1.852
    WD_rad = np.radians(WD_mat)
    # Direzione Meteo: U = Ovest-Est, V = Sud-Nord (con il segno - perché la direzione indica la provenienza)
    U_knots = -WS_knots * np.sin(WD_rad)
    V_knots = -WS_knots * np.cos(WD_rad)

    # --- CREAZIONE DEL GRAFICO ---
    fig = plt.figure(figsize=(15, 12))
    # Diamo 4/5 dello spazio allo spaccato verticale, e 1/5 ai dati al suolo
    gs = fig.add_gridspec(5, 1) 
    ax_main = fig.add_subplot(gs[0:4, 0])
    ax_bot = fig.add_subplot(gs[4, 0], sharex=ax_main)

    # 1. Mappa di Calore: Umidità Relativa (Nubi)
    cmap_rh = plt.get_cmap('YlGnBu') # Colori da Giallo a Blu intenso
    rh_levels = np.arange(50, 101, 10) # Evidenziamo solo umidità > 50%
    cf = ax_main.contourf(times, levels, RH_mat, levels=rh_levels, cmap=cmap_rh, alpha=0.8, extend='min')
    cbar = fig.colorbar(cf, ax=ax_main, pad=0.01)
    cbar.set_label('Umidità Relativa (%)', fontweight='bold')

    # 2. Linee di Contorno: Temperatura
    t_levels = np.arange(-60, 45, 4)
    ct = ax_main.contour(times, levels, T_mat, levels=t_levels, colors='#333333', linewidths=0.5, linestyles='solid')
    ax_main.clabel(ct, inline=True, fontsize=8, fmt='%1.0f')
    
    # 2.1 Evidenziamo lo Zero Termico (Isoterma 0°C)
    ct_zero = ax_main.contour(times, levels, T_mat, levels=[0], colors='red', linewidths=2.5)
    ax_main.clabel(ct_zero, inline=True, fontsize=10, fmt='0°C')

    # 3. Vento (Barbi meteo)
    # Riduciamo la densità per non accavallare i simboli: uno ogni 3 ore
    skip_t = 3 
    X_mesh, Y_mesh = np.meshgrid(mdates.date2num(times), levels)
    # Disegniamo i barbi del vento. length e linewidth controllano l'estetica.
    ax_main.barbs(times[::skip_t], Y_mesh[:, ::skip_t], U_knots[:, ::skip_t], V_knots[:, ::skip_t], 
                  length=5, linewidth=0.6, pivot='middle', color='black', alpha=0.8)

    # 4. Formattazione Asse Principale (Pressione)
    ax_main.set_yscale('log') # La scala logaritmica rispetta l'altezza fisica
    ax_main.invert_yaxis()    # 1000hPa in basso, 200hPa in alto
    ax_main.set_yticks([1000, 925, 850, 700, 500, 300, 200]) # Tick principali
    from matplotlib.ticker import ScalarFormatter
    ax_main.yaxis.set_major_formatter(ScalarFormatter())
    
    ax_main.set_ylabel('Pressione Atmosferica (hPa)', fontweight='bold', fontsize=11)
    ax_main.set_title('Cross-Section Atmosferica (Time-Height) - Modello ICON-D2', fontweight='bold', fontsize=14)
    ax_main.grid(axis='y', linestyle='--', alpha=0.5)

    # 5. Pannello Inferiore (Andamento al suolo / 1000 hPa)
    idx_1000 = levels.index(1000) # Prende l'indice del livello a 1000hPa
    ax_bot.plot(times, T_mat[idx_1000, :], color='#d62728', label='Temp 1000hPa (°C)', linewidth=2.5)
    ax_bot.fill_between(times, T_mat[idx_1000, :], color='#d62728', alpha=0.1)
    
    ax_bot_wind = ax_bot.twinx()
    ax_bot_wind.plot(times, WS_mat[idx_1000, :], color='#17becf', label='Vento 1000hPa (km/h)', linewidth=1.5, linestyle='--')
    
    ax_bot.set_ylabel('Temp al suolo (°C)', color='#d62728', fontweight='bold')
    ax_bot_wind.set_ylabel('Vento (km/h)', color='#17becf', fontweight='bold')
    ax_bot.grid(True, linestyle='--', alpha=0.5)

    # Legende e formattazione asse temporale
    lines, labels = ax_bot.get_legend_handles_labels()
    lines2, labels2 = ax_bot_wind.get_legend_handles_labels()
    ax_bot.legend(lines + lines2, labels + labels2, loc='upper left', ncol=2, fontsize=10)

    ax_bot.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax_bot.xaxis.set_major_formatter(mdates.DateFormatter('%H:00\n%d %b'))
    plt.setp(ax_bot.xaxis.get_majorticklabels(), rotation=0, ha='center')

    plt.tight_layout()
    plt.savefig(FILENAME, dpi=200, bbox_inches='tight')
    print(f"✅ Grafico salvato come {FILENAME}")

    # --- INVIO TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD")
    
    if token and chat_id:
        print("Invio del grafico a Telegram...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {"chat_id": chat_id, "caption": f"Spaccato Atmosferico ICON-D2 - Generato alle {datetime.now().strftime('%H:%M')}"}
        if thread_id: 
            payload["message_thread_id"] = thread_id
        try:
            with open(FILENAME, "rb") as photo:
                requests.post(url_telegram, data=payload, files={"photo": photo})
                print("Inviato con successo!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

if __name__ == "__main__":
    main()