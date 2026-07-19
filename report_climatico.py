import os
import requests
import calendar
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime, timedelta

LOCK_FILE = "lock_report_inviati.txt"

# --- FUNZIONI GRAFICHE E DI TESTO ---
def genera_dettaglio_classifica(df, year_target, metric, diff, unit):
    is_surplus = diff > 0
    ascending_order = not is_surplus
    tipo = "più caldo" if metric in ['tmax', 'tmin'] else "più piovoso"
    if not is_surplus:
        tipo = "più freddo" if metric in ['tmax', 'tmin'] else "più secco"

    df_sorted = df.sort_values(by=metric, ascending=ascending_order).reset_index(drop=True)
    idx = df_sorted[df_sorted['year'] == year_target].index[0]
    pos = idx + 1
    
    base_text = f"**{pos}°** {tipo}"

    if pos > 5: return base_text
    if pos == 1: return f"{base_text} [🏆 Record dal 1940!]"
    
    rows_above = df_sorted.iloc[:idx]
    details = [f"{int(row['year'])} ({row[metric]:.1f} {unit})" for _, row in rows_above.iterrows()]
    
    if len(details) > 10:
        details_troncati = details[:10]
        extra = len(details) - 10
        dettagli_str = ", ".join(details_troncati) + f", ...e altri {extra}"
    else:
        dettagli_str = ", ".join(details)
        
    return f"{base_text} [dietro al {dettagli_str}]"

def format_extreme(name, count, streak, df_storico, year_target, metric_name):
    if count == 0:
        return ""
    
    df_sorted = df_storico.sort_values(by=metric_name, ascending=False).reset_index(drop=True)
    idx = df_sorted[df_sorted['year'] == year_target].index[0]
    pos = idx + 1
    
    base_streak = f"max {int(streak)} consecutivi"
    
    if pos <= 10:
        if pos == 1:
            streak_text = f"({base_streak}, 🏆 Record dal 1940!)"
        elif pos <= 5:
            rows_above = df_sorted.iloc[:idx]
            details = [f"{int(row['year'])} ({int(row[metric_name])})" for _, row in rows_above.iterrows()]
            if len(details) > 10:
                details_str = ", ".join(details[:10]) + f", ...e altri {len(details)-10}"
            else:
                details_str = ", ".join(details)
            streak_text = f"({base_streak}, **{pos}°** serie più lunga [dietro al {details_str}])"
        else:
            streak_text = f"({base_streak}, **{pos}°** serie più lunga)"
    else:
        streak_text = f"({base_streak})"
        
    return f"{name}: {int(count)} {streak_text}\n"

# --- LOGICA PICCHI GIORNALIERI (TOP 5) ---
def check_daily_extreme(df_daily, target_year, metric, is_hot):
    if df_daily.empty: return ""
    
    # Isola i dati dell'anno target per trovare il picco
    df_target = df_daily[df_daily['group_year'] == target_year]
    if df_target.empty: return ""
    
    curr_val = df_target[metric].max() if is_hot else df_target[metric].min()
    # Prende la prima data in caso di picchi identici nello stesso anno
    curr_date = df_target[df_target[metric] == curr_val]['date'].iloc[0]
    
    # Ordina l'intero database storico (tutti i giorni dal 1940)
    df_sorted = df_daily.sort_values(by=metric, ascending=not is_hot).reset_index(drop=True)
    idx = df_sorted[df_sorted['date'] == curr_date].index[0]
    pos = idx + 1
    
    # Escludi se non è in Top 5
    if pos > 5:
        return ""
        
    tipo = "T. Massima" if metric == 'tmax' else "T. Minima"
    termine = "calda" if is_hot else "fredda"
    base_text = f"**{pos}°** giornata con {tipo} più {termine} di sempre ({curr_val:.1f} °C il {curr_date.strftime('%d/%m/%Y')})"
    
    if pos == 1:
        return f"🚨 {base_text} [🏆 Record dal 1940!]\n"
        
    rows_above = df_sorted.iloc[:idx]
    details = [f"{row['date'].strftime('%d/%m/%Y')} ({row[metric]:.1f} °C)" for _, row in rows_above.iterrows()]
    
    return f"🌡 {base_text} [dietro al {', '.join(details)}]\n"

def generate_dashboard(tmax, tmin, precip, diff_tmax, diff_tmin, diff_precip, title, filename):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis('off')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    x_pos = [0.18, 0.50, 0.82]

    def draw_block(x_c, y_c, w, h, color, txt, txt_color, fsize):
        shadow = patches.FancyBboxPatch((x_c - w/2 + 0.005, y_c - h/2 - 0.01), w, h, boxstyle="round,pad=0.03,rounding_size=0.08", linewidth=0, facecolor='black', alpha=0.1, zorder=0)
        ax.add_patch(shadow)
        rect = patches.FancyBboxPatch((x_c - w/2, y_c - h/2), w, h, boxstyle="round,pad=0.03,rounding_size=0.08", linewidth=0, facecolor=color, zorder=1)
        ax.add_patch(rect)
        ax.text(x_c, y_c, txt, ha='center', va='center', color=txt_color, fontsize=fsize, fontweight='bold', zorder=2)

    width_main, height_main, y_main = 0.28, 0.35, 0.65
    draw_block(x_pos[0], y_main, width_main, height_main, '#4FC3F7', f"T. Minima\n\n{tmin:.1f} °C", 'black', 16)
    draw_block(x_pos[1], y_main, width_main, height_main, '#E53935', f"T. Massima\n\n{tmax:.1f} °C", 'white', 16)
    draw_block(x_pos[2], y_main, width_main, height_main, '#90A4AE', f"Precipitazioni\n\n{precip:.1f} mm", 'black', 16)

    def get_color(val): return '#4CAF50' if val > 0 else '#795548'
    def format_val(val, unit): return f"+{val:.1f} {unit}" if val > 0 else f"{val:.1f} {unit}"

    width_sub, height_sub, y_sub = 0.22, 0.20, 0.25
    draw_block(x_pos[0], y_sub, width_sub, height_sub, get_color(diff_tmin), format_val(diff_tmin, "°C"), 'white', 15)
    draw_block(x_pos[1], y_sub, width_sub, height_sub, get_color(diff_tmax), format_val(diff_tmax, "°C"), 'white', 15)
    draw_block(x_pos[2], y_sub, width_sub, height_sub, get_color(diff_precip), format_val(diff_precip, "mm"), 'white', 15)

    plt.text(0.5, 0.95, title, ha='center', va='center', fontsize=18, fontweight='bold', color='#333333')
    plt.tight_layout()
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    plt.close()

def get_max_streak(s):
    if not s.any(): return 0
    return int(s.groupby((~s).cumsum()).sum().max())

# --- MOTORE DI CALCOLO ---
def process_period(period_type, target_year, target_month=None, target_season=None):
    if period_type == 'month':
        mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        nome_periodo = f"{mesi[target_month-1]} {target_year}"
        start_date = f"{target_year}-{target_month:02d}-01"
        last_day = calendar.monthrange(target_year, target_month)[1]
        end_date = f"{target_year}-{target_month:02d}-{last_day:02d}"
        months_to_filter = [target_month]
        lock_id = f"month_{target_year}_{target_month:02d}"
        
    elif period_type == 'season':
        stagioni = {'winter': 'Inverno', 'spring': 'Primavera', 'summer': 'Estate', 'autumn': 'Autunno'}
        if target_season == 'winter':
            nome_periodo = f"Inverno {target_year-1}/{target_year}"
            start_date, end_date = f"{target_year-1}-12-01", f"{target_year}-02-{calendar.monthrange(target_year, 2)[1]:02d}"
            months_to_filter = [12, 1, 2]
        else:
            nome_periodo = f"{stagioni[target_season]} {target_year}"
            if target_season == 'spring':
                start_date, end_date = f"{target_year}-03-01", f"{target_year}-05-31"
                months_to_filter = [3, 4, 5]
            elif target_season == 'summer':
                start_date, end_date = f"{target_year}-06-01", f"{target_year}-08-31"
                months_to_filter = [6, 7, 8]
            elif target_season == 'autumn':
                start_date, end_date = f"{target_year}-09-01", f"{target_year}-11-30"
                months_to_filter = [9, 10, 11]
        lock_id = f"season_{target_year}_{target_season}"
            
    elif period_type == 'year':
        nome_periodo = f"Anno {target_year}"
        start_date, end_date = f"{target_year}-01-01", f"{target_year}-12-31"
        months_to_filter = list(range(1, 13))
        lock_id = f"year_{target_year}"

    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            inviati = f.read().splitlines()
        if lock_id in inviati:
            print(f"⏭️ Il report {nome_periodo} ({lock_id}) è già stato inviato. Salto.")
            return

    print(f"\n🚀 Elaborazione {nome_periodo} in corso...")

    # Aggiornate le coordinate per Torino centro (Lat 45.0703, Lon 7.6869)
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude=45.0703&longitude=7.6869&start_date={start_date}&end_date={end_date}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&models=era5_seamless&timezone=auto"
    try:
        res = requests.get(url)
        res.raise_for_status()
        api_df = pd.DataFrame(res.json()['daily'])
        api_df['date'] = pd.to_datetime(api_df['time'])
        api_df['year'] = api_df['date'].dt.year
        api_df['month'] = api_df['date'].dt.month
        api_df.rename(columns={'temperature_2m_max': 'tmax', 'temperature_2m_min': 'tmin', 'precipitation_sum': 'precip'}, inplace=True)
    except Exception as e:
        print(f"❌ Errore API: {e}") 
        return

    try:
        # Assicurati di scaricare questo nuovo CSV e caricarlo su GitHub
        df_storico = pd.read_csv('open-meteo-torino-centro_1940_2025.csv', skiprows=3)
        df_storico.columns = ['date', 'tmax', 'tmin', 'precip']
        df_storico['date'] = pd.to_datetime(df_storico['date'])
        df_storico['year'] = df_storico['date'].dt.year
        df_storico['month'] = df_storico['date'].dt.month

        df_storico = df_storico[~((df_storico['year'] == target_year) | (df_storico['year'] == target_year-1))]
        full_df = pd.concat([df_storico, api_df[['date', 'year', 'month', 'tmax', 'tmin', 'precip']]], ignore_index=True)

        df_filt = full_df[full_df['month'].isin(months_to_filter)].copy()
        
        if period_type == 'season' and target_season == 'winter':
            df_filt['group_year'] = np.where(df_filt['month'] == 12, df_filt['year'] + 1, df_filt['year'])
        else:
            df_filt['group_year'] = df_filt['year']

        df_filt = df_filt.sort_values('date')

        stats_list = []
        for yr, group in df_filt.groupby('group_year'):
            stats_list.append({
                'year': yr,
                'tmax': group['tmax'].mean(),
                'tmin': group['tmin'].mean(),
                'precip': group['precip'].sum(),
                'trop_n': (group['tmin'] >= 20).sum(),
                'trop_s': get_max_streak(group['tmin'] >= 20),
                'hot_d': (group['tmax'] >= 30).sum(),
                'hot_s': get_max_streak(group['tmax'] >= 30),
                'frost_d': (group['tmin'] < 0).sum(),
                'frost_s': get_max_streak(group['tmin'] < 0),
                'ice_d': (group['tmax'] <= 0).sum(),
                'ice_s': get_max_streak(group['tmax'] <= 0),
            })
            
        totale_anni = pd.DataFrame(stats_list)

        if period_type == 'season' and target_season == 'winter':
            totale_anni = totale_anni[totale_anni['year'] > totale_anni['year'].min()]

        baseline = totale_anni[(totale_anni['year'] >= 1991) & (totale_anni['year'] <= 2020)].mean()
        curr = totale_anni[totale_anni['year'] == target_year].iloc[0]

        diff_tmax = curr['tmax'] - baseline['tmax']
        diff_tmin = curr['tmin'] - baseline['tmin']
        diff_precip = curr['precip'] - baseline['precip']

        testo_tmax = genera_dettaglio_classifica(totale_anni, target_year, 'tmax', diff_tmax, "°C")
        testo_tmin = genera_dettaglio_classifica(totale_anni, target_year, 'tmin', diff_tmin, "°C")
        testo_precip = genera_dettaglio_classifica(totale_anni, target_year, 'precip', diff_precip, "mm")

        testo_classifica = (f"\n\n🏆 **Classifica Storica (su {len(totale_anni)} anni)**\n"
                            f"🌡 T. Massima: {testo_tmax}\n"
                            f"❄️ T. Minima: {testo_tmin}\n"
                            f"🌧 Precipitazioni: {testo_precip}")
                            
        # --- PICCHI GIORNALIERI ASSOLUTI (TOP 5) ---
        txt_picco_max = check_daily_extreme(df_filt, target_year, 'tmax', is_hot=True)
        txt_picco_min = check_daily_extreme(df_filt, target_year, 'tmin', is_hot=False)
        
        if txt_picco_max or txt_picco_min:
            testo_classifica += f"\n\n📈 **Record Giornalieri Raggiunti**\n{txt_picco_max}{txt_picco_min}"
                            
        # --- ESTREMI AGGIORNATI ---
        txt_trop = format_extreme("🥵 Notti tropicali", curr['trop_n'], curr['trop_s'], totale_anni, target_year, 'trop_s')
        txt_hot = format_extreme("☀️ Giorni roventi", curr['hot_d'], curr['hot_s'], totale_anni, target_year, 'hot_s')
        
        if txt_trop or txt_hot:
            testo_classifica += f"\n\n🏖 **Estremi di Caldo**\n{txt_trop}{txt_hot}"

        txt_frost = format_extreme("🥶 Notti gelide", curr['frost_d'], curr['frost_s'], totale_anni, target_year, 'frost_s')
        txt_ice = format_extreme("🧊 Giorni di ghiaccio", curr['ice_d'], curr['ice_s'], totale_anni, target_year, 'ice_s')
        
        if txt_frost or txt_ice:
            testo_classifica += f"\n\n❄️ **Estremi di Freddo**\n{txt_frost}{txt_ice}"

    except Exception as e:
        print(f"⚠️ Errore con storico: {e}")
        testo_classifica = ""
        diff_tmax = diff_tmin = diff_precip = 0
        curr = {'tmax': api_df['tmax'].mean(), 'tmin': api_df['tmin'].mean(), 'precip': api_df['precip'].sum()}

    title = f"Report Climatico: {nome_periodo} vs Storico 1991-2020"
    filename = f"report_{lock_id}.png"
    generate_dashboard(curr['tmax'], curr['tmin'], curr['precip'], diff_tmax, diff_tmin, diff_precip, title, filename)

    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_STORIA") 
    
    if token and chat_id:
        caption = f"📊 **Report Climatico: {nome_periodo}**\n {testo_classifica}"
        payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
        if thread_id: payload["message_thread_id"] = thread_id
        try:
            with open(filename, "rb") as photo:
                res_tg = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data=payload, files={"photo": photo})
                res_tg.raise_for_status()
            print(f"✅ Inviato con successo su Telegram: {nome_periodo}")
            
            with open(LOCK_FILE, "a") as f:
                f.write(f"{lock_id}\n")
            print(f"🔒 Lock salvato per {lock_id}.")
            
        except Exception as e:
            print(f"❌ Eccezione Telegram: {e}")

# --- ESECUZIONE 100% AUTOMATICA (Calendario Perpetuo) ---
def main():
    oggi = datetime.now()
    data_target = oggi - timedelta(days=15)
    m_target, y_target = data_target.month, data_target.year
    
    process_period('month', y_target, target_month=m_target)
    
    if m_target == 2: 
        process_period('season', y_target, target_season='winter')
    elif m_target == 5: 
        process_period('season', y_target, target_season='spring')
    elif m_target == 8: 
        process_period('season', y_target, target_season='summer')
    elif m_target == 11: 
        process_period('season', y_target, target_season='autumn')
    
    if m_target == 12: 
        process_period('year', y_target)

if __name__ == "__main__":
    main()
