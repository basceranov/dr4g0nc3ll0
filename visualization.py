# visualization.py
import os
import matplotlib.pyplot as plt
from config import ASSETS_DIR

os.makedirs(ASSETS_DIR, exist_ok=True)

def chart_source_mix(counts: dict, filename="source_mix.png"):
    labels = list(counts.keys())
    values = [counts.get(k, 0) for k in labels]
    plt.figure()
    plt.bar(labels, values)
    plt.title("Distribuzione tipologie di fonte")
    plt.ylabel("Conteggio")
    out = os.path.join(ASSETS_DIR, filename)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=144)
    plt.close()
    # normalizza per Markdown: sempre slash
    return out.replace("\\", "/")

def chart_indicator_timeseries(series, filename="indicator_series.png", title="Indicatore"):
    """
    series: list of tuples [(date_iso, value), ...] già ordinati
    """
    dates = [d for d,_ in series]
    vals = [v for _,v in series]
    plt.figure()
    plt.plot(dates, vals, marker="o")
    plt.title(title)
    plt.xlabel("Data")
    plt.ylabel("Valore")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    out = os.path.join(ASSETS_DIR, filename)
    plt.savefig(out, dpi=144)
    plt.close()
    return out

def map_events(events, filename="events_map.html"):
    """
    events: [{ 'date': 'YYYY-MM-DD', 'event': '...', 'lat': float, 'lon': float, 'url': '...' }]
    Se non hai lat/lon, salta la mappa.
    """
    try:
        import folium
    except Exception:
        return None
    pts = [ (e["lat"], e["lon"]) for e in events if "lat" in e and "lon" in e ]
    if not pts:
        return None
    mean_lat = sum([p[0] for p in pts]) / len(pts)
    mean_lon = sum([p[1] for p in pts]) / len(pts)
    m = folium.Map(location=[mean_lat, mean_lon], zoom_start=5, tiles="OpenStreetMap")
    for e in events:
        if "lat" in e and "lon" in e:
            popup = f"{e['date']}: {e['event']}<br><a href='{e.get('url','#')}' target='_blank'>Fonte</a>"
            folium.Marker([e["lat"], e["lon"]], popup=popup).add_to(m)
    out = os.path.join(ASSETS_DIR, filename)
    m.save(out)
    return out
