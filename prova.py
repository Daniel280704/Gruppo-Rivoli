import os
import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def main():
    print("Elaborazione dati climatologici mensili 1991-2020...")
    
    # --- 1. CARICAMENTO E PREPARAZIONE DATI ---
    file_path = "open-meteo-torino-centro_1940_2025.csv"
    try:
        df = pd.read_csv(file_path, skiprows=3)
    except FileNotFoundError:
        print(f"❌ Errore: File {file_path} non trovato.")
        return

    df.columns = ['date', 'tmax', 'tmin', 'precip']

    df['date'] = pd.to_datetime(df['date'])
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month

    # Somma precipitazioni mensili per ogni anno, media temperature
    monthly_yearly = df.groupby(['year', 'month']).agg({
        'tmax': 'mean',
        'tmin': 'mean',
        'precip': 'sum'
    }).reset_index()

    # Media trentennale (la normale climatologica)
    climatology = monthly_yearly.groupby('month').agg({
        'tmax': 'mean',
        'tmin': 'mean',
        'precip': 'mean'
    }).reset_index()

    # --- 2. SALVATAGGIO DEL FILE CSV MENSILI ---
    climatology_csv = climatology.copy()
    climatology_csv.columns = ['mese', 'tmax_media', 'tmin_media', 'precip_media']
    climatology_csv['tmax_media'] = climatology_csv['tmax_media'].round(1)
    climatology_csv['tmin_media'] = climatology_csv['tmin_media'].round(1)
    climatology_csv['precip_media'] = climatology_csv['precip_media'].round(1)
    
    csv_filename = "riferimento_mensile_1991_2020.csv"
    climatology_csv.to_csv(csv_filename, index=False)
    print(f"✅ File {csv_filename} salvato per script successivi.")

    # --- 3. GENERAZIONE GRAFICO ---
    mesi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']
    x = np.arange(len(mesi))

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Precipitazioni
    color_precip = '#4ea4ff'
    bars = ax1.bar(x, climatology['precip'], color=color_precip, alpha=0.7, label='Precipitazioni (mm)')
    ax1.set_ylabel('Precipitazioni medie mensili (mm)', color='#005a9c', fontsize=11, fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#005a9c')
    ax1.set_xticks(x)
    ax1.set_xticklabels(mesi)
    
    # Limite precipitazioni richiesto (1.1)
    ax1.set_ylim(0, max(climatology['precip']) * 1.1)

    # Temperature
    ax2 = ax1.twinx()
    color_tmax = '#d62728'
    color_tmin = '#1f77b4'

    line_tmax = ax2.plot(x, climatology['tmax'], color=color_tmax, marker='o', linewidth=2, label='T. Max media (°C)')
    line_tmin = ax2.plot(x, climatology['tmin'], color=color_tmin, marker='o', linewidth=2, label='T. Min media (°C)')

    ax2.set_ylabel('Temperatura (°C)', color='#333333', fontsize=11, fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#333333')

    t_min_val = min(climatology['tmin'])
    t_max_val = max(climatology['tmax'])
    range_t = t_max_val - t_min_val
    ax2.set_ylim(t_min_val - range_t*0.2, t_max_val + range_t*0.6)

    ax1.grid(axis='y', linestyle='--', alpha=0.5)
    plt.title('Climatologia Storica (1991-2020)\nTemperature Medie e Precipitazioni', fontsize=14, fontweight='bold', pad=15)

    for bar in bars:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, yval + 1.5, f'{yval:.0f}', ha='center', va='bottom', color='#005a9c', fontsize=9)

    for i, txt in enumerate(climatology['tmax']):
        ax2.text(x[i], txt + 0.5, f'{txt:.1f}', ha='center', va='bottom', color=color_tmax, fontsize=9, fontweight='bold')
        
    for i, txt in enumerate(climatology['tmin']):
        ax2.text(x[i], txt - 1.2, f'{txt:.1f}', ha='center', va='top', color=color_tmin, fontsize=9, fontweight='bold')

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left', frameon=True, shadow=True)

    plt.tight_layout()

    output_img = "climatologia_1991_2020.png"
    plt.savefig(output_img, dpi=200, bbox_inches='tight')
    print("✅ Grafico salvato localmente.")

    # --- 4. INVIO TELEGRAM (IMMAGINE + CSV) ---
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_STORIA") 
    
    if token and chat_id:
        # A) Invio Immagine
        url_photo = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload_photo = {
            "chat_id": chat_id,
            "caption": "📊 **Climatologia Storica 1991-2020**\nValori normali di temperatura e precipitazioni calcolati per Rivoli.",
            "parse_mode": "Markdown"
        }
        if thread_id:
            payload_photo["message_thread_id"] = thread_id
            
        try:
            with open(output_img, "rb") as photo:
                requests.post(url_photo, data=payload_photo, files={"photo": photo})
            print("✅ Immagine inviata con successo su Telegram!")
        except Exception as e:
            print(f"❌ Eccezione invio immagine: {e}")

        # B) Invio File CSV
        url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
        payload_doc = {
            "chat_id": chat_id,
            "caption": "📁 File CSV con le medie mensili (1991-2020) per i successivi calcoli delle anomalie."
        }
        if thread_id:
            payload_doc["message_thread_id"] = thread_id

        try:
            with open(csv_filename, "rb") as doc:
                requests.post(url_doc, data=payload_doc, files={"document": doc})
            print("✅ File CSV inviato con successo su Telegram!")
        except Exception as e:
            print(f"❌ Eccezione invio documento: {e}")

    else:
        print("⚠️ Credenziali Telegram mancanti, salto l'invio.")

if __name__ == "__main__":
    main()
