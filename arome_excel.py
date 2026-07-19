import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')

FILENAME = "profili_atmosferici_arome.xlsx"
FILE_LAST_HOUR = "ultima_ora_arome_excel.txt"

LAT = 45.07347491421504
LON = 7.543461388723449

# Regole fisse da tabella per AROME
RUN_DURATION = 51
START_DELAY = 2

URL_CHECK = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=rain,snowfall,temperature_2m&models=meteofrance_arome_france_hd&timezone=auto&forecast_days=3"
URL_MAIN = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_1000hPa,temperature_950hPa,temperature_900hPa,temperature_925hPa,temperature_850hPa,temperature_800hPa,temperature_750hPa,temperature_700hPa,temperature_650hPa,temperature_600hPa,temperature_550hPa,temperature_500hPa,temperature_450hPa,temperature_400hPa,temperature_350hPa,temperature_300hPa,temperature_275hPa,temperature_250hPa,temperature_225hPa,temperature_200hPa,dew_point_1000hPa,dew_point_950hPa,dew_point_925hPa,dew_point_900hPa,dew_point_850hPa,dew_point_800hPa,dew_point_750hPa,dew_point_700hPa,dew_point_650hPa,dew_point_600hPa,dew_point_550hPa,dew_point_350hPa,dew_point_450hPa,dew_point_400hPa,dew_point_500hPa,dew_point_300hPa,dew_point_275hPa,dew_point_250hPa,dew_point_225hPa,dew_point_200hPa,relative_humidity_1000hPa,relative_humidity_950hPa,relative_humidity_925hPa,relative_humidity_850hPa,relative_humidity_900hPa,relative_humidity_800hPa,relative_humidity_750hPa,relative_humidity_700hPa,relative_humidity_650hPa,relative_humidity_600hPa,relative_humidity_550hPa,relative_humidity_500hPa,relative_humidity_450hPa,relative_humidity_350hPa,relative_humidity_400hPa,relative_humidity_300hPa,relative_humidity_275hPa,relative_humidity_225hPa,relative_humidity_250hPa,relative_humidity_200hPa,wind_speed_1000hPa,wind_speed_950hPa,wind_speed_925hPa,wind_speed_850hPa,wind_speed_800hPa,wind_speed_900hPa,wind_speed_750hPa,wind_speed_700hPa,wind_speed_650hPa,wind_speed_600hPa,wind_speed_450hPa,wind_speed_550hPa,wind_speed_500hPa,wind_speed_400hPa,wind_speed_300hPa,wind_speed_350hPa,wind_speed_275hPa,wind_speed_225hPa,wind_speed_250hPa,wind_speed_200hPa,wind_direction_1000hPa,wind_direction_950hPa,wind_direction_925hPa,wind_direction_900hPa,wind_direction_850hPa,wind_direction_800hPa,wind_direction_750hPa,wind_direction_700hPa,wind_direction_600hPa,wind_direction_650hPa,wind_direction_550hPa,wind_direction_500hPa,wind_direction_400hPa,wind_direction_450hPa,wind_direction_350hPa,wind_direction_250hPa,wind_direction_300hPa,wind_direction_275hPa,wind_direction_225hPa,wind_direction_200hPa,geopotential_height_1000hPa,geopotential_height_950hPa,geopotential_height_925hPa,geopotential_height_900hPa,geopotential_height_850hPa,geopotential_height_800hPa,geopotential_height_750hPa,geopotential_height_650hPa,geopotential_height_700hPa,geopotential_height_600hPa,geopotential_height_550hPa,geopotential_height_500hPa,geopotential_height_450hPa,geopotential_height_400hPa,geopotential_height_350hPa,geopotential_height_300hPa,geopotential_height_275hPa,geopotential_height_225hPa,geopotential_height_200hPa,geopotential_height_250hPa&models=meteofrance_arome_france&timezone=auto&forecast_days=3"

def check_condizioni_neve() -> bool:
    print("⏳ Verifica preliminare condizioni neve AROME...")
    try:
        response = requests.get(URL_CHECK, timeout=30)
        response.raise_for_status()
        hourly = response.json().get("hourly", {})
        
        snowfall = hourly.get("snowfall", [])
        rain = hourly.get("rain", [])
        t2m = hourly.get("temperature_2m", [])

        for i in range(len(snowfall)):
            snw = snowfall[i] if snowfall[i] is not None else 0
            rn = rain[i] if rain[i] is not None else 0
            t = t2m[i] if t2m[i] is not None else 99

            if snw >= 0.5:
                return True
            if rn >= 0.5 and t < 3.0:
                return True
                
        return False
    except Exception as e:
        print(f"⚠️ Errore durante il check neve: {e}", file=sys.stderr)
        return False

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
    if pd.isna(gradi) or gradi is None: return None
    val = int((gradi / 45) + 0.5)
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][val % 8]

def fetch_dati_con_retry():
    headers = {"User-Agent": "MeteoBot-Excel-AROME/1.0"}
    for tentativo in range(3):
        try:
            response = requests.get(URL_MAIN, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"⚠️ Errore API: {e}", file=sys.stderr)
            time.sleep(15)
    return {}

def main():
    if not check_condizioni_neve():
        print("❄️ Condizioni neve/freddo non soddisfatte. Lo script si interrompe.")
        sys.exit(0)

    print("Scaricamento dati AROME per generazione Excel...")
    data = fetch_dati_con_retry()
    
    if not data: sys.exit(0)
    
    hourly = data.get("hourly", {})
    utc_offset = data.get("utc_offset_seconds", 0)
    
    is_new, nome_run, s_idx, e_idx = estrai_limiti_run(hourly, "temperature_1000hPa", utc_offset)
    
    if not is_new:
        print("Nessun nuovo run completo trovato per AROME. Uscita.")
        sys.exit(0)
        
    print(f"ℹ️ Trovato nuovo run AROME completo: {nome_run}. Generazione Excel in corso...")

    levels = [1000, 950, 925, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350, 300, 275, 250, 225, 200]
    times_run = hourly.get("time", [])[s_idx : e_idx + 1]
    rows = []
    
    for relative_i, t_str in enumerate(times_run):
        abs_i = s_idx + relative_i 
        data_ora_formattata = datetime.fromisoformat(t_str).strftime("%Y-%m-%d %H:%M")

        for p in levels:
            temp = hourly.get(f"temperature_{p}hPa", [])[abs_i] if f"temperature_{p}hPa" in hourly else None
            dew = hourly.get(f"dew_point_{p}hPa", [])[abs_i] if f"dew_point_{p}hPa" in hourly else None
            rh = hourly.get(f"relative_humidity_{p}hPa", [])[abs_i] if f"relative_humidity_{p}hPa" in hourly else None
            ws = hourly.get(f"wind_speed_{p}hPa", [])[abs_i] if f"wind_speed_{p}hPa" in hourly else None
            wd_deg = hourly.get(f"wind_direction_{p}hPa", [])[abs_i] if f"wind_direction_{p}hPa" in hourly else None
            geop_raw = hourly.get(f"geopotential_height_{p}hPa", [])[abs_i] if f"geopotential_height_{p}hPa" in hourly else None

            geop = int(round(geop_raw)) if geop_raw is not None and not pd.isna(geop_raw) else None
            wd_cardinale = gradi_a_punti_cardinali(wd_deg)

            if temp is not None or geop is not None:
                rows.append({
                    "Data e Ora": data_ora_formattata,
                    "Pressione (hPa)": p,
                    "Geopotenziale (m)": geop,
                    "Temperatura (°C)": temp,
                    "Dew Point (°C)": dew,
                    "Umidità Relativa (%)": rh,
                    "Velocità Vento (km/h)": ws,
                    "Dir. Vento": wd_cardinale
                })

    df = pd.DataFrame(rows)
    df.to_excel(FILENAME, index=False, engine='openpyxl')
    print(f"✅ Excel generato con successo: {FILENAME}")

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD_NEVE")
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendDocument"
        payload = {"chat_id": chat_id, "caption": f"❄️ Profili Atmosferici AROME Neve ({nome_run})"}
        if thread_id: payload["message_thread_id"] = thread_id
            
        try:
            with open(FILENAME, "rb") as doc:
                requests.post(url_telegram, data=payload, files={"document": doc})
        except Exception as e:
            print(f"Errore invio Telegram: {e}")

if __name__ == "__main__":
    main()
