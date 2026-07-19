import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

FILENAME = "profili_atmosferici_icon_2i.xlsx"
FILE_LAST_HOUR = "ultima_ora_icon_2i_excel.txt"

# Regole fisse per ICON-2I (da tuo file originale)
RUN_DURATION = 72
START_DELAY = 0

URL = "https://api.open-meteo.com/v1/forecast?latitude=45.0707&longitude=7.5146&hourly=temperature_1000hPa,temperature_925hPa,temperature_850hPa,temperature_500hPa,temperature_700hPa,temperature_250hPa,relative_humidity_1000hPa,relative_humidity_700hPa,relative_humidity_925hPa,relative_humidity_850hPa,relative_humidity_500hPa,relative_humidity_250hPa,wind_speed_1000hPa,wind_speed_925hPa,wind_speed_850hPa,wind_speed_700hPa,wind_speed_500hPa,wind_speed_250hPa,wind_direction_1000hPa,wind_direction_925hPa,wind_direction_850hPa,wind_direction_700hPa,wind_direction_250hPa,wind_direction_500hPa,geopotential_height_1000hPa,geopotential_height_925hPa,geopotential_height_850hPa,geopotential_height_700hPa,geopotential_height_500hPa,geopotential_height_250hPa&models=italia_meteo_arpae_icon_2i&timezone=auto&forecast_days=5"

def estrai_limiti_run(hourly_data: dict, ref_param: str, utc_offset_sec: int) -> tuple[bool, str, int, int]:
    times = hourly_data.get("time", [])
    mean_vals = hourly_data.get(ref_param, [])

    if not times or not mean_vals: return False, "", -1, -1

    end_idx = -1
    for i in range(len(mean_vals) - 1, -1, -1):
        if mean_vals[i] is not None:
            end_idx = i
            break

    if end_idx == -1: return False, "", -1, -1

    ultima_ora_valida_str = times[end_idx]

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
    actual_points = end_idx - start_idx + 1

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

    return True, nome_run, start_idx, end_idx


def gradi_a_punti_cardinali(gradi):
    if pd.isna(gradi) or gradi is None:
        return None
    val = int((gradi / 45) + 0.5)
    punti = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    return punti[val % 8]

def fetch_dati_con_retry():
    headers = {"User-Agent": "MeteoBot-Excel-ICON2I/1.0"}
    for tentativo in range(3):
        try:
            response = requests.get(URL, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def main():
    print("Scaricamento dati ICON-2I per generazione Excel...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    
    # Utilizziamo temperature_1000hPa come parametro guida per il check del run
    is_new, nome_run, s_idx, e_idx = estrai_limiti_run(hourly, "temperature_1000hPa", utc_offset)
    
    if not is_new:
        print("Nessun nuovo run completo trovato per ICON-2I. Uscita.")
        sys.exit(0)
        
    print(f"ℹ️ Trovato nuovo run ICON-2I completo: {nome_run}. Generazione Excel in corso...")

    # I livelli di pressione presenti nella tua query per l'API
    levels = [1000, 925, 850, 700, 500, 250]
    
    times_run = hourly.get("time", [])[s_idx : e_idx + 1]
    rows = []
    
    for relative_i, t_str in enumerate(times_run):
        abs_i = s_idx + relative_i 
        
        dt_obj = datetime.fromisoformat(t_str)
        data_ora_formattata = dt_obj.strftime("%Y-%m-%d %H:%M")

        for p in levels:
            temp = hourly.get(f"temperature_{p}hPa", [])[abs_i] if f"temperature_{p}hPa" in hourly else None
            rh = hourly.get(f"relative_humidity_{p}hPa", [])[abs_i] if f"relative_humidity_{p}hPa" in hourly else None
            ws = hourly.get(f"wind_speed_{p}hPa", [])[abs_i] if f"wind_speed_{p}hPa" in hourly else None
            wd_deg = hourly.get(f"wind_direction_{p}hPa", [])[abs_i] if f"wind_direction_{p}hPa" in hourly else None
            geop_raw = hourly.get(f"geopotential_height_{p}hPa", [])[abs_i] if f"geopotential_height_{p}hPa" in hourly else None

            # Arrotondamento del geopotenziale all'intero
            geop = int(round(geop_raw)) if geop_raw is not None and not pd.isna(geop_raw) else None
            wd_cardinale = gradi_a_punti_cardinali(wd_deg)

            if temp is not None or geop is not None:
                rows.append({
                    "Data e Ora": data_ora_formattata,
                    "Pressione (hPa)": p,
                    "Geopotenziale (m)": geop,
                    "Temperatura (°C)": temp,
                    "Umidità Relativa (%)": rh,
                    "Velocità Vento (km/h)": ws,
                    "Dir. Vento": wd_cardinale
                })

    df = pd.DataFrame(rows)

    print("Salvataggio file Excel in corso...")
    df.to_excel(FILENAME, index=False, engine='openpyxl')
    print(f"✅ Excel generato con successo: {FILENAME}")

    # --- INVIO TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD")
    
    if token and chat_id:
        print("Invio del file Excel a Telegram...")
        url_telegram = f"https://api.telegram.org/bot{token}/sendDocument"
        payload = {
            "chat_id": chat_id, 
            "caption": f"📊 Profili Atmosferici ICON-2I aggiornati ({nome_run})"
        }
        if thread_id: 
            payload["message_thread_id"] = thread_id
            
        try:
            with open(FILENAME, "rb") as doc:
                requests.post(url_telegram, data=payload, files={"document": doc})
                print("Inviato con successo!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

if __name__ == "__main__":
    main()