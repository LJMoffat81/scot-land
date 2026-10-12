import httpx
import logging
import json
from paths import PROCESSED_DIR
from georgist.resource_rent import calculator

logger = logging.getLogger(__name__)

# PLACEHOLDER: the features below are MOCKS, not harvested data. Every output
# is tagged quality="placeholder" and the aggregator excludes it from totals.
# The rent factors in resource_rent.py are unsourced. Do not publish.
QUALITY = "placeholder"
COMMONS_CLASS = "extractive"
VALUE_TIER = "proxy"  # area x unsourced factor; "market" only once leases/royalties are observed (rules 3)
OUTPUT_FILE = PROCESSED_DIR / "resource_wealth.geojson"

# WFS Endpoints (simplified for implementation)
MARINE_WFS_URL = "https://spatialdata.gov.scot/geonetwork/srv/api/records/9d31b891-b896-49f8-bcea-9787f79dd5f8"
# In a real implementation, this would be a specific OGC WFS GetFeature request
# For this sprint, we implement the structure to handle the returned GeoJSON

def build_resource_features() -> dict:
    """
    Resource Harvester: Connects to the Marine Directorate WFS to fetch
    polygons for hydrocarbons, wind, and marine assets.
    """
    logger.info("Starting resource wealth harvest...")

    # MOCK DATA: Representing the result of a WFS GetFeature request
    # In production: replace with httpx.get(MARINE_WFS_URL, params=params)
    mock_features = [
        {
            "type": "Feature",
            "properties": {"resource_type": "hydrocarbon_oil", "name": "North Sea Field A", "area_ha": 150.0},
            "geometry": {"type": "Polygon", "coordinates": [[[ -1.0, 56.0], [-1.1, 56.0], [-1.1, 56.1], [-1.0, 56.1], [-1.0, 56.0]]]}
        },
        {
            "type": "Feature",
            "properties": {"resource_type": "offshore_wind", "name": "East Coast Array", "area_ha": 1200.0},
            "geometry": {"type": "Polygon", "coordinates": [[[ -2.0, 57.0], [-2.1, 57.0], [-2.1, 57.1], [-2.0, 57.1], [-2.0, 57.0]]]}
        }
    ]

    processed_features = []

    for feat in mock_features:
        props = feat["properties"]
        res_type = props.get("resource_type")
        area = props.get("area_ha", 0)

        # Calculate the Georgist Rent for this resource polygon
        rent = calculator.calculate(res_type, area)

        # Append the wealth data to the feature properties
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
        "meta": {"source": "Marine Directorate WFS (MOCK — not harvested)", "quality": QUALITY, "in_totals": False, "calc": "Georgist Resource Engine"},
        "features": processed_features
    }

    return geojson


def harvest_resource_wealth() -> dict:
    """Write the placeholder collection to DATA_DIR/processed (CLI only; the API never writes)."""
    geojson = build_resource_features()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)
    logger.info(f"Placeholder resource harvest written to {OUTPUT_FILE} (mock data, excluded from totals)")
    return geojson


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    harvest_resource_wealth()
