import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def main():
    print("Recupero dati di Giugno 2026 e medie storiche...")

    # --- 1. LETTURA DEL RIFERIMENTO STORICO TRENTENNALE (1991-2020) ---
    try:
        ref_df = pd.read_csv('riferimento_mensile_1991_2020.csv')
    except FileNotFoundError:
        print("❌ Errore: File riferimento_mensile_1991_2020.csv non trovato.")
        return

    june_ref = ref_df[ref_df['mese'] == 6].iloc[0]
    tmax_ref = june_ref['tmax_media']
    tmin_ref = june_ref['tmin_media']
    precip_ref = june_ref['precip_media']

    # --- 2. DOWNLOAD DATI GIUGNO 2026 (API ERA5) ---
    url = "https://archive-api.open-meteo.com/v1/archive?latitude=45.07347491421504&longitude=7.543461388723449&start_date=2026-06-01&end_date=2026-06-30&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&models=era5_seamless&timezone=auto"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"❌ Errore API: {e}")
        return

    daily = pd.DataFrame(data['daily'])

    tmax_eff = daily['temperature_2m_max'].mean()
    tmin_eff = daily['temperature_2m_min'].mean()
    precip_eff = daily['precipitation_sum'].sum()

    diff_tmax = tmax_eff - tmax_ref
    diff_tmin = tmin_eff - tmin_ref
    diff_precip = precip_eff - precip_ref

    # --- 3. CLASSIFICA STORICA (DAL 1940) ---
    testo_classifica = ""
    try:
        print("Elaborazione classifica storica dal 1940...")
        df_storico_lungo = pd.read_csv('open-meteo-45.10N7.50E326m_1940_2025.csv', skiprows=3)
        df_storico_lungo.columns = ['date', 'tmax', 'tmin', 'precip']
        df_storico_lungo['date'] = pd.to_datetime(df_storico_lungo['date'])
        df_storico_lungo['year'] = df_storico_lungo['date'].dt.year
        df_storico_lungo['month'] = df_storico_lungo['date'].dt.month
        
        # Filtriamo tutti i mesi di Giugno storici (1940-2025)
        df_giugno = df_storico_lungo[df_storico_lungo['month'] == 6]
        giugno_storico = df_giugno.groupby('year').agg({
            'tmax': 'mean', 
            'tmin': 'mean', 
            'precip': 'sum'
        }).reset_index()
        
        # Aggiungiamo i dati del 2026 appena scaricati per calcolare la graduatoria totale
        nuova_riga = pd.DataFrame({'year': [2026], 'tmax': [tmax_eff], 'tmin': [tmin_eff], 'precip': [precip_eff]})
        giugno_totale = pd.concat([giugno_storico, nuova_riga], ignore_index=True)
        tot_anni = len(giugno_totale)
        
        # Logica dei piazzamenti dinamici basata su surplus o deficit
        if diff_tmax > 0:
            pos_tmax = int(giugno_totale['tmax'].rank(ascending=False, method='min').iloc[-1])
            testo_tmax = f"{pos_tmax}° più caldo"
        else:
            pos_tmax = int(giugno_totale['tmax'].rank(ascending=True, method='min').iloc[-1])
            testo_tmax = f"{pos_tmax}° più freddo"
            
        if diff_tmin > 0:
            pos_tmin = int(giugno_totale['tmin'].rank(ascending=False, method='min').iloc[-1])
            testo_tmin = f"{pos_tmin}° più caldo"
        else:
            pos_tmin = int(giugno_totale['tmin'].rank(ascending=True, method='min').iloc[-1])
            testo_tmin = f"{pos_tmin}° più freddo"
            
        if diff_precip > 0:
            pos_precip = int(giugno_totale['precip'].rank(ascending=False, method='min').iloc[-1])
            testo_precip = f"{pos_precip}° più piovoso"
        else:
            pos_precip = int(giugno_totale['precip'].rank(ascending=True, method='min').iloc[-1])
            testo_precip = f"{pos_precip}° più secco"
            
        # Stringa pronta per la caption di Telegram
        testo_classifica = (f"\n\n🏆 **Classifica Storica (su {tot_anni} anni dal 1940)**\n"
                            f"🌡 T. Massima: {testo_tmax}\n"
                            f"❄️ T. Minima: {testo_tmin}\n"
                            f"🌧 Precipitazioni: {testo_precip}")
    except FileNotFoundError:
        print("⚠️ File open-meteo-45.10N7.50E326m_1940_2025.csv non trovato. Salto la classifica storica.")

    # --- 4. GENERAZIONE GRAFICA ---
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    x_pos = [0.18, 0.50, 0.82]

    def draw_block(x_center, y_center, width, height, color, text, text_color, fontsize):
        shadow = patches.FancyBboxPatch(
            (x_center - width/2 + 0.005, y_center - height/2 - 0.01), width, height, 
            boxstyle="round,pad=0.03,rounding_size=0.08", 
            linewidth=0, facecolor='black', alpha=0.1, zorder=0
        )
        ax.add_patch(shadow)
        
        rect = patches.FancyBboxPatch(
            (x_center - width/2, y_center - height/2), width, height, 
            boxstyle="round,pad=0.03,rounding_size=0.08", 
            linewidth=0, facecolor=color, zorder=1
        )
        ax.add_patch(rect)
        
        ax.text(x_center, y_center, text, ha='center', va='center', 
                color=text_color, fontsize=fontsize, fontweight='bold', zorder=2)

    width_main = 0.28
    height_main = 0.35
    y_main = 0.65

    draw_block(x_pos[0], y_main, width_main, height_main, '#4FC3F7', f"T. Minima\n\n{tmin_eff:.1f} °C", 'black', 16)
    draw_block(x_pos[1], y_main, width_main, height_main, '#E53935', f"T. Massima\n\n{tmax_eff:.1f} °C", 'white', 16)
    draw_block(x_pos[2], y_main, width_main, height_main, '#90A4AE', f"Precipitazioni\n\n{precip_eff:.1f} mm", 'black', 16)

    def get_color(val):
        return '#4CAF50' if val > 0 else '#795548'

    def format_val(val, unit):
        return f"+{val:.1f} {unit}" if val > 0 else f"{val:.1f} {unit}"

    width_sub = 0.22
    height_sub = 0.20
    y_sub = 0.25

    draw_block(x_pos[0], y_sub, width_sub, height_sub, get_color(diff_tmin), format_val(diff_tmin, "°C"), 'white', 15)
    draw_block(x_pos[1], y_sub, width_sub, height_sub, get_color(diff_tmax), format_val(diff_tmax, "°C"), 'white', 15)
    draw_block(x_pos[2], y_sub, width_sub, height_sub, get_color(diff_precip), format_val(diff_precip, "mm"), 'white', 15)

    plt.text(0.5, 0.95, "Report Climatico: Giugno 2026 vs Storico (1991-2020)", 
             ha='center', va='center', fontsize=18, fontweight='bold', color='#333333')

    plt.tight_layout()
    output_filename = "dashboard_giugno_2026.png"
    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    print(f"✅ Grafico generato e salvato come {output_filename}")

    # --- 5. INVIO A TELEGRAM ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_STORIA") 
    
    if token and chat_id:
        url_telegram = f"https://api.telegram.org/bot{token}/sendPhoto"
        
        # Inseriamo la classifica appena calcolata direttamente nella Caption del messaggio
        caption = f"📊 **Report Climatico: Giugno 2026**\nAnalisi delle anomalie termiche e pluviometriche rispetto alla media storica (1991-2020) di Rivoli.{testo_classifica}"
        
        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        
        if thread_id:
            payload["message_thread_id"] = thread_id
            
        try:
            with open(output_filename, "rb") as photo:
                response = requests.post(url_telegram, data=payload, files={"photo": photo})
                response.raise_for_status()
            print("✅ Immagine e Classifica inviate con successo su Telegram nel thread STORIA!")
        except Exception as e:
            print(f"❌ Eccezione Telegram: {e}")
    else:
        print("⚠️ Credenziali Telegram mancanti, salto l'invio.")

if __name__ == "__main__":
    main()
