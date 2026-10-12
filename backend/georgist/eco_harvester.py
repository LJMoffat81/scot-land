import json
import logging
from paths import PROCESSED_DIR
from georgist.eco_rent import calculator

logger = logging.getLogger(__name__)

# PLACEHOLDER: the features below are MOCKS, not harvested data. Every output
# is tagged quality="placeholder" and the aggregator excludes it from totals.
# The rent factors in eco_rent.py are unsourced. Do not publish.
QUALITY = "placeholder"
COMMONS_CLASS = "eco"
VALUE_TIER = "shadow"  # intended tier once real data exists (rules 3)
OUTPUT_FILE = PROCESSED_DIR / "eco_wealth.geojson"

def build_eco_features() -> dict:
    """
    Eco Harvester: Connects to NatureScot and MET Office data
    to fetch polygons for peatlands, woodlands, and solar/wind potential.
    """
    logger.info("Starting eco-atmospheric wealth harvest...")

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
        feat["properties"].update({
            "quality": QUALITY,
            "commons_class": COMMONS_CLASS,
            "value_tier": VALUE_TIER,
            "crosswalk_method": "footprint_area",
            "publish_level": "internal",
            "in_totals": False,
        })
        processed_features.append(feat)

    geojson = {
        "type": "FeatureCollection",
        "meta": {"source": "NatureScot / MET Office (MOCK — not harvested)", "quality": QUALITY, "in_totals": False, "calc": "Georgist Eco Engine"},
        "features": processed_features
    }

    return geojson


def harvest_eco_wealth() -> dict:
    """Write the placeholder collection to DATA_DIR/processed (CLI only; the API never writes)."""
    geojson = build_eco_features()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)
    logger.info(f"Placeholder eco harvest written to {OUTPUT_FILE} (mock data, excluded from totals)")
    return geojson


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    harvest_eco_wealth()
