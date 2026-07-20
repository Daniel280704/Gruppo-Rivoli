import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def crea_climogramma(csv_filename):
    print("Lettura del database storico in corso...")
    
    try:
        # Caricamento dati e filtro colonne
        df = pd.read_csv(csv_filename, skiprows=3)
        df.columns = ['date', 'tmax', 'tmin', 'precip']
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month

        # Filtro stringente sul trentennio climatologico di riferimento
        df_baseline = df[(df['year'] >= 1991) & (df['year'] <= 2020)]

        print("Calcolo delle medie mensili 1991-2020...")
        # Per le temperature: calcoliamo la media di tutte le massime e minime giornaliere per ogni mese
        tmax_mean = df_baseline.groupby('month')['tmax'].mean()
        tmin_mean = df_baseline.groupby('month')['tmin'].mean()

        # Per le precipitazioni: prima sommiamo la pioggia mese per mese in ogni singolo anno, poi ne facciamo la media
        precip_monthly_sum = df_baseline.groupby(['year', 'month'])['precip'].sum().reset_index()
        precip_mean = precip_monthly_sum.groupby('month')['precip'].mean()

        # --- CREAZIONE GRAFICO ---
        mesi_labels = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']
        x = np.arange(len(mesi_labels))

        fig, ax1 = plt.subplots(figsize=(12, 7))

        # Asse Y Sinistro: Precipitazioni (Barre)
        bars = ax1.bar(x, precip_mean, color='#8ABEF0', label='Precipitazioni (mm)', zorder=2, width=0.7)
        ax1.set_ylabel('Precipitazioni medie mensili (mm)', color='#115B8F', fontweight='bold', fontsize=12)
        ax1.tick_params(axis='y', labelcolor='#115B8F')
        ax1.set_ylim(0, max(precip_mean) + 40) # Margine per non tagliare le etichette
        ax1.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

        # Etichette sui valori di precipitazione
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 2,
                     f'{int(round(height))}', ha='center', va='bottom', color='#115B8F', fontsize=10, fontweight='bold')

        # Asse Y Destro: Temperature (Linee)
        ax2 = ax1.twinx()
        
        line_tmax = ax2.plot(x, tmax_mean, marker='o', color='#D62728', linewidth=2.5, label='T. Max media (°C)')
        line_tmin = ax2.plot(x, tmin_mean, marker='o', color='#1F77B4', linewidth=2.5, label='T. Min media (°C)')

        ax2.set_ylabel('Temperatura (°C)', fontweight='bold', fontsize=12)
        ax2.set_ylim(min(tmin_mean) - 8, max(tmax_mean) + 10) # Margine per staccare le linee dai bordi

        # Etichette sui valori di T. Massima
        for i, txt in enumerate(tmax_mean):
            ax2.text(x[i], txt + 0.8, f'{txt:.1f}', ha='center', va='bottom', color='#D62728', fontsize=10, fontweight='bold')

        # Etichette sui valori di T. Minima
        for i, txt in enumerate(tmin_mean):
            ax2.text(x[i], txt - 1.8, f'{txt:.1f}', ha='center', va='top', color='#1F77B4', fontsize=10, fontweight='bold')

        # Personalizzazione Titolo e Assi X
        plt.title("Climatologia Storica (1991-2020) - Torino Centro\nTemperature Medie e Precipitazioni", fontweight='bold', fontsize=16, pad=20)
        ax1.set_xticks(x)
        ax1.set_xticklabels(mesi_labels, fontsize=11)

        # Legenda Combinata in alto a sinistra
        lines_1, labels_1 = ax1.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', shadow=True, fancybox=True, fontsize=11, framealpha=1)

        plt.tight_layout()
        
        # Salvataggio
        nome_output = 'climogramma_1991_2020_torino.png'
        plt.savefig(nome_output, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✅ Climogramma generato con successo! Salvato come: {nome_output}")

    except FileNotFoundError:
        print(f"❌ Errore: Il file {csv_filename} non è stato trovato. Assicurati che sia nella stessa cartella.")
    except Exception as e:
        print(f"❌ Si è verificato un errore durante la generazione: {e}")

# Esecuzione
if __name__ == "__main__":
    crea_climogramma('open-meteo-torino-centro_1940_2025.csv')