import json
import logging
from pathlib import Path
from georgist.eco_rent import calculator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PROCESSED_DIR = Path("data/processed")
OUTPUT_FILE = PROCESSED_DIR / "eco_wealth.geojson"

def harvest_eco_wealth():
    """
    Eco Harvester: Connects to NatureScot and MET Office data
    to fetch polygons for peatlands, woodlands, and solar/wind potential.
    """
    logger.info("Starting eco-atmospheric wealth harvest...")
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # MOCK DATA: Representing the results from NatureScot and MET Office
    mock_features = [
        {
            "type": "Feature",
            "properties": {"resource_type": "peatland_sequestration", "name": "Cairngorms Peatland", "area_ha": 5000.0},
            "geometry": {"type": "Polygon", "coordinates": [[[ -3.5, 57.0], [-3.6, 57.0], [-3.6, 57.1], [-3.5, 57.1], [-3.5, 57.0]]]}
        },
        {
            "type": "Feature",
            "properties": {"resource_type": "ancient_woodland", "name": "Caledonian Forest", "area_ha": 1200.0},
            "geometry": {"type": "Polygon", "coordinates": [[[ -3.0, 57.2], [-3.1, 57.2], [-3.1, 57.3], [-3.0, 57.3], [-3.0, 57.2]]]}
        }
    ]

    processed_features = []

    for feat in mock_features:
        props = feat["properties"]
        res_type = props.get("resource_type")
        area = props.get("area_ha", 0)

        rent = calculator.calculate(res_type, area)

        feat["properties"]["annual_rent_gbp"] = rent
        feat["properties"]["rent_per_ha"] = rent / area if area > 0 else 0
        processed_features.append(feat)

    geojson = {
        "type": "FeatureCollection",
        "meta": {"source": "NatureScot / MET Office", "calc": "Georgist Eco Engine"},
        "features": processed_features
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    logger.info(f"Eco wealth harvest complete. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    harvest_eco_wealth()
