import os
import sys
import requests
import pandas as pd
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')

FILENAME = "profili_atmosferici_icon_d2.xlsx"

URL = "https://api.open-meteo.com/v1/forecast?latitude=45.0707&longitude=7.5146&hourly=temperature_975hPa,temperature_1000hPa,temperature_950hPa,temperature_925hPa,temperature_900hPa,temperature_850hPa,temperature_800hPa,temperature_700hPa,temperature_600hPa,temperature_500hPa,relative_humidity_1000hPa,relative_humidity_975hPa,relative_humidity_950hPa,relative_humidity_925hPa,relative_humidity_850hPa,relative_humidity_900hPa,relative_humidity_800hPa,relative_humidity_700hPa,relative_humidity_600hPa,relative_humidity_500hPa,relative_humidity_400hPa,relative_humidity_300hPa,relative_humidity_250hPa,relative_humidity_200hPa,temperature_300hPa,temperature_400hPa,temperature_250hPa,temperature_200hPa,wind_speed_1000hPa,wind_speed_975hPa,wind_speed_950hPa,wind_speed_900hPa,wind_speed_925hPa,wind_speed_850hPa,wind_speed_800hPa,wind_speed_700hPa,wind_speed_600hPa,wind_speed_500hPa,wind_speed_400hPa,wind_speed_300hPa,wind_speed_250hPa,wind_speed_200hPa,geopotential_height_1000hPa,geopotential_height_975hPa,geopotential_height_950hPa,geopotential_height_900hPa,geopotential_height_925hPa,geopotential_height_850hPa,geopotential_height_800hPa,geopotential_height_700hPa,geopotential_height_500hPa,geopotential_height_600hPa,geopotential_height_400hPa,geopotential_height_250hPa,geopotential_height_300hPa,geopotential_height_200hPa,wind_direction_1000hPa,wind_direction_975hPa,wind_direction_925hPa,wind_direction_950hPa,wind_direction_900hPa,wind_direction_850hPa,wind_direction_800hPa,wind_direction_600hPa,wind_direction_700hPa,wind_direction_400hPa,wind_direction_500hPa,wind_direction_300hPa,wind_direction_250hPa,wind_direction_200hPa&models=dwd_icon_d2&timezone=auto&forecast_days=3"

# Funzione per convertire i gradi (0-360) in punti cardinali italiani
def gradi_a_punti_cardinali(gradi):
    if pd.isna(gradi) or gradi is None:
        return None
    val = int((gradi / 45) + 0.5)
    punti = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    return punti[val % 8]

def fetch_dati():
    headers = {"User-Agent": "MeteoBot-Excel/1.0"}
    try:
        response = requests.get(URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️ Errore API: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    print("Scaricamento dati ICON-D2 per generazione Excel...")
    data = fetch_dati()
    hourly = data.get("hourly", {})
    if not hourly:
        print("Dati hourly non trovati.")
        sys.exit(1)

    # Elenco dei livelli di pressione (ordinati dal suolo verso l'alto)
    levels = [1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200]
    times = hourly.get("time", [])

    rows = []
    
    # Costruiamo le righe iterando per ogni ora e, al suo interno, per ogni livello
    for i, t_str in enumerate(times):
        # Formattiamo la data per Excel in un formato leggibile
        dt_obj = datetime.fromisoformat(t_str)
        data_ora_formattata = dt_obj.strftime("%Y-%m-%d %H:%M")

        for p in levels:
            # Estraiamo le variabili per l'ora 'i' e il livello 'p'
            temp = hourly.get(f"temperature_{p}hPa", [])[i] if f"temperature_{p}hPa" in hourly else None
            rh = hourly.get(f"relative_humidity_{p}hPa", [])[i] if f"relative_humidity_{p}hPa" in hourly else None
            ws = hourly.get(f"wind_speed_{p}hPa", [])[i] if f"wind_speed_{p}hPa" in hourly else None
            wd_deg = hourly.get(f"wind_direction_{p}hPa", [])[i] if f"wind_direction_{p}hPa" in hourly else None
            geop = hourly.get(f"geopotential_height_{p}hPa", [])[i] if f"geopotential_height_{p}hPa" in hourly else None

            # Calcoliamo la direzione cardinale (N, NE, E...)
            wd_cardinale = gradi_a_punti_cardinali(wd_deg)

            # Aggiungiamo la riga solo se c'è almeno un dato valido (esclude ore future non coperte dal modello)
            if temp is not None or geop is not None:
                rows.append({
                    "Data e Ora": data_ora_formattata,
                    "Pressione (hPa)": p,
                    "Geopotenziale (m)": geop,
                    "Temperatura (°C)": temp,
                    "Umidità Relativa (%)": rh,
                    "Velocità Vento (km/h)": ws,
                    "Dir. Vento (Gradi)": wd_deg,
                    "Dir. Vento": wd_cardinale
                })

    # Creiamo il DataFrame di Pandas
    df = pd.DataFrame(rows)

    # Salvataggio in Excel
    print("Salvataggio file Excel in corso...")
    # Usiamo engine='openpyxl' che è lo standard per i file .xlsx
    df.to_excel(FILENAME, index=False, engine='openpyxl')
    print(f"✅ Excel generato con successo: {FILENAME}")

    # --- INVIO TELEGRAM DEL DOCUMENTO ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_HD")
    
    if token and chat_id:
        print("Invio del file Excel a Telegram...")
        # Nota: usiamo /sendDocument per inviare file non-immagine
        url_telegram = f"https://api.telegram.org/bot{token}/sendDocument"
        payload = {
            "chat_id": chat_id, 
            "caption": "📊 Tabella Profili Atmosferici ICON-D2 aggiornata."
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