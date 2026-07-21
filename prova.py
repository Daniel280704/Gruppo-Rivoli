import os
import time
import requests
import metview as mv
from ecmwf.opendata import Client
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

FILENAME = "medium-z500-t850.grib"
PNG_OUTPUT = "medium-z500-t850"

def download_and_plot():
    client = Client("ecmwf", beta=False)
    
    parameters = ['gh', 't']
    
    try:
        # Scarica lo step a +12 ore dall'ultimo run 00z
        client.retrieve(
            time=0,
            step=12,
            stream="oper",
            type="fc",
            levtype="pl",
            levelist=[500, 850],
            param=parameters,
            target=FILENAME
        )
    except Exception as e:
        print(f"Errore download: {e}")
        return False

    if not os.path.exists(FILENAME):
        print("Errore: GRIB non scaricato.")
        return False

    # Leggi dati con Metview
    data = mv.read(FILENAME)
    
    t850 = data.select(shortName='t', level=850)
    gh500 = data.select(shortName='gh', level=500)
    
    # Converti geopotenziale m -> decametri
    gh500 /= 10
    
    # Visuale sull'Europa
    coast = mv.mcoast(
        map_coastline_colour="charcoal",
        map_coastline_resolution="medium",
        map_coastline_land_shade="on",
        map_coastline_land_shade_colour="cream",
        map_coastline_sea_shade="off",
        map_boundaries="on",
        map_boundaries_colour="charcoal",
        map_boundaries_thickness=1,
        map_disputed_boundaries="off",
        map_grid_colour="tan",
        map_label_height=0.35,
    )
    
    view = mv.geoview(
        map_area_definition="corners",
        area=[30, -30, 75, 45], # Sud, Ovest, Nord, Est
        coastlines=coast
    )

    # Nuovo stile Temperatura a 850 hPa (Dettaglio: 1°C)
    t850_shade = mv.mcont(
        legend="on",
        contour="off",
        contour_shade="on",
        contour_shade_technique="polygon_shading",
        contour_level_selection_type="interval",
        contour_interval=1.0,
        contour_shade_colour_method="calculate",
        contour_shade_min_level=-30.0,
        contour_shade_max_level=40.0,
        contour_shade_min_level_colour="purple",
        contour_shade_max_level_colour="red",
        contour_shade_colour_direction="clockwise"
    )
    
    # Stile Geopotenziale 500 hPa (ufficiale ECMWF)
    gh500_shade = mv.mcont(
        legend="on",
        contour_automatic_setting="style_name",
        contour_style_name="ct_blk_i4_t2"
    )
    
    title = mv.mtext(
        text_lines=["Geopotenziale 500 hPa e Temperatura 850 hPa - ECMWF Open Data"],
        text_font_size=0.4,
        text_colour='charcoal'
    )
    
    png = mv.png_output(
        output_name=PNG_OUTPUT,
        output_title="medium-z500-t850",
        output_width=1000
    )
    
    mv.setoutput(png)
    mv.plot(view, t850, t850_shade, gh500, gh500_shade, title)
    return True

def invia_telegram():
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    thread_id = os.getenv("TELEGRAM_THREAD_ID_ECMWF")
    
    if not token or not chat_id:
        print("Credenziali Telegram non fornite.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": "ECMWF T850 + Z500 - Europa (Risoluzione 1°C)"}
    
    if thread_id:
        payload["message_thread_id"] = thread_id
        
    file_path = f"{PNG_OUTPUT}.1.png"
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "rb") as photo:
                requests.post(url, data=payload, files={"photo": photo})
                print("Inviato su Telegram!")
        except Exception as e:
            print(f"Errore invio Telegram: {e}")
    else:
        print(f"File {file_path} non trovato.")

if __name__ == "__main__":
    if download_and_plot():
        invia_telegram()