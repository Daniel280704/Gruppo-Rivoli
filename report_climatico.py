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

def format_extreme(name, count, streak, df_storico, year_target, count_col, streak_col):
    # 1. CLASSIFICA CONTEGGIO TOTALE ASSOLUTO (COUNT)
    better_high_c = df_storico[df_storico[count_col] > count].sort_values(by=count_col, ascending=False)
    pos_desc_c = len(better_high_c) + 1
    
    better_low_c = df_storico[df_storico[count_col] < count].sort_values(by=count_col, ascending=True)
    pos_asc_c = len(better_low_c) + 1

    count_text = f"{int(count)}"
    
    # Controllo Top 5 Maggior Numero
    if pos_desc_c <= 5 and count > 0:
        if pos_desc_c == 1:
            count_text += " [🏆 Maggior numero dal 1940!]"
        else:
            details = [f"{int(row['year'])} ({int(row[count_col])})" for _, row in better_high_c.iterrows()]
            details_str = ", ".join(details[:5]) + (f", ...e altri {len(details)-5}" if len(details)>5 else "")
            count_text += f" [- {pos_desc_c}° maggior numero dietro al {details_str} -]"
            
    # Controllo Top 5 Minor Numero (Segnalato solo se mediamente ci si aspetta almeno 1 evento in quel periodo)
    elif pos_asc_c <= 5 and df_storico[count_col].mean() >= 1.0: 
        if pos_asc_c == 1:
            count_text += " [🏆 Minor numero dal 1940!]"
        else:
            details = [f"{int(row['year'])} ({int(row[count_col])})" for _, row in better_low_c.iterrows()]
            details_str = ", ".join(details[:5]) + (f", ...e altri {len(details)-5}" if len(details)>5 else "")
            count_text += f" [- {pos_asc_c}° minor numero dietro al {details_str} -]"

    # Anti-Spam: Se il conteggio è 0 e non rientra in nessun record, saltiamo la riga
    if count == 0 and "[" not in count_text:
        return ""

    # 2. CLASSIFICA SERIE CONSECUTIVA (STREAK)
    streak_text = ""
    if streak > 0:
        better_high_s = df_storico[df_storico[streak_col] > streak].sort_values(by=streak_col, ascending=False)
        pos_desc_s = len(better_high_s) + 1
        
        base_streak = f"max {int(streak)} consecutivi"
        
        if pos_desc_s <= 10:
            if pos_desc_s == 1:
                streak_text = f"({base_streak}, 🏆 Record dal 1940!)"
            elif pos_desc_s <= 5:
                details = [f"{int(row['year'])} ({int(row[streak_col])})" for _, row in better_high_s.iterrows()]
                details_str = ", ".join(details[:5]) + (f", ...e altri {len(details)-5}" if len(details)>5 else "")
                streak_text = f"({base_streak}, {pos_desc_s}° serie più lunga [dietro al {details_str}])"
            else:
                streak_text = f"({base_streak}, {pos_desc_s}° serie più lunga)"
        else:
            streak_text = f"({base_streak})"

    if streak_text:
        return f"{name}: {count_text} {streak_text}\n"
    else:
        return f"{name}: {count_text}\n"

# --- LOGICA PICCHI GIORNALIERI (TOP 5 ESTESA AI 4 POLI) ---
def check_daily_extreme(df_daily, target_year, metric, is_highest):
    if df_daily.empty: return ""
    
    # Isola i dati dell'anno target per trovare il picco
    df_target = df_daily[df_daily['group_year'] == target_year]
    if df_target.empty: return ""
    
    curr_val = df_target[metric].max() if is_highest else df_target[metric].min()
    # Prende la prima data in caso di picchi identici nello stesso anno
    curr_date = df_target[df_target[metric] == curr_val]['date'].iloc[0]
    
    # Ordina l'intero database storico (tutti i giorni dal 1940)
    df_sorted = df_daily.sort_values(by=metric, ascending=not is_highest).reset_index(drop=True)
    idx = df_sorted[df_sorted['date'] == curr_date].index[0]
    pos = idx + 1
    
    # Escludi se non è in Top 5
    if pos > 5:
        return ""
        
    tipo = "T. Massima" if metric == 'tmax' else "T. Minima"
    termine = "più alta" if is_highest else "più bassa"
    base_text = f"**{pos}°** {tipo} {termine} di sempre ({curr_val:.1f} °C il {curr_date.strftime('%d/%m/%Y')})"
    
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
        df_storico = pd.read_csv('open-meteo-torino-centro_1940_2025.csv', skiprows=3)
        df_storico.columns = ['date', 'tmax', 'tmin', 'precip']
        df_storico['date'] = pd.to_datetime(df_storico['date'])
        df_storico['year'] = df_storico['date'].dt.year
        df_storico['month'] = df_storico['date'].dt.month

        # Unisce il CSV (fino al 2025 o anni successivi) con i giorni scaricati dall'API per il report attuale
        full_df = pd.concat([df_storico, api_df[['date', 'year', 'month', 'tmax', 'tmin', 'precip']]], ignore_index=True)
        
        # Elimina eventuali giorni sovrapposti tenendo validi i dati più recenti dell'API
        full_df = full_df.drop_duplicates(subset=['date'], keep='last')

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
                            
        # --- PICCHI GIORNALIERI ASSOLUTI (I 4 POLI ESTREMI) ---
        txt_tmax_alta = check_daily_extreme(df_filt, target_year, 'tmax', is_highest=True)
        txt_tmax_bassa = check_daily_extreme(df_filt, target_year, 'tmax', is_highest=False)
        txt_tmin_alta = check_daily_extreme(df_filt, target_year, 'tmin', is_highest=True)
        txt_tmin_bassa = check_daily_extreme(df_filt, target_year, 'tmin', is_highest=False)
        
        picchi = [txt_tmax_alta, txt_tmin_alta, txt_tmax_bassa, txt_tmin_bassa]
        testo_picchi = "".join(p for p in picchi if p)
        
        if testo_picchi:
            testo_classifica += f"\n\n📈 **Record Giornalieri Raggiunti**\n{testo_picchi}"
                            
        # --- ESTREMI AGGIORNATI (CONTEGGIO ASSOLUTO + STRISCIA) ---
        txt_trop = format_extreme("🥵 Notti tropicali", curr['trop_n'], curr['trop_s'], totale_anni, target_year, 'trop_n', 'trop_s')
        txt_hot = format_extreme("☀️ Giorni roventi", curr['hot_d'], curr['hot_s'], totale_anni, target_year, 'hot_d', 'hot_s')
        
        if txt_trop or txt_hot:
            testo_classifica += f"\n\n🏖 **Estremi di Caldo**\n{txt_trop}{txt_hot}"

        txt_frost = format_extreme("🥶 Notti gelide", curr['frost_d'], curr['frost_s'], totale_anni, target_year, 'frost_d', 'frost_s')
        txt_ice = format_extreme("🧊 Giorni di ghiaccio", curr['ice_d'], curr['ice_s'], totale_anni, target_year, 'ice_d', 'ice_s')
        
        if txt_frost or txt_ice:
            testo_classifica += f"\n\n❄️ **Estremi di Freddo**\n{txt_frost}{txt_ice}"

    except Exception as e:
        print(f"⚠️ Errore con storico: {e}")
        testo_classifica = ""
        diff_tmax = diff_tmin = diff_precip = 0
        curr = {'tmax': api_df['tmax'].mean(), 'tmin': api_df['tmin'].mean(), 'precip': api_df['precip'].sum()}

    title = f"Report Torino Centro: {nome_periodo} vs Storico 1991-2020"
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

# --- ESECUZIONE 100% AUTOMATICA E DINAMICA ---
def main():
    # 1. Prende la data esatta di oggi
    oggi = datetime.now()
    
    # 2. Torna al 1° giorno del mese in corso e toglie 1 giorno per cadere esattamente alla fine del mese scorso
    mese_scorso = oggi.replace(day=1) - timedelta(days=1)
    
    # 3. Estrae il mese e l'anno target
    m_target = mese_scorso.month
    y_target = mese_scorso.year
    
    print(f"Data odierna: {oggi.strftime('%d/%m/%Y')}. Calcolo automatico report per: Mese {m_target:02d}, Anno {y_target}")

    # Lancia SEMPRE il report del mese appena concluso
    process_period('month', y_target, target_month=m_target)
    
    # Riconoscimento automatico chiusura stagioni
    if m_target == 2: 
        process_period('season', y_target, target_season='winter')
    elif m_target == 5: 
        process_period('season', y_target, target_season='spring')
    elif m_target == 8: 
        process_period('season', y_target, target_season='summer')
    elif m_target == 11: 
        process_period('season', y_target, target_season='autumn')
    
    # Riconoscimento automatico chiusura anno
    if m_target == 12: 
        process_period('year', y_target)

if __name__ == "__main__":
    main()