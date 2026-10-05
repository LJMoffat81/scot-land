"""Seabed notes state a published rule. They do not invent a yearly total."""

from pathlib import Path

from agr.seabed import agreement_lease, aquaculture_lease, seabed_record
from spatial.context_tiles import seabed_query_url


def _money_keys(record: dict) -> list[str]:
    return [key for key in record if "gbp" in key or key in {"annual", "rent", "mwh"}]


def test_finfish_states_the_rule_and_not_a_site_total():
    record = aquaculture_lease(
        {
            "Lease_Description": "AR4-27-6",
            "Property_Classification": "Finfish Farm",
            "Site_ID": 1022286,
            "Shape__Area": 578483,
            "Rent": 1500,
        }
    )
    assert record is not None
    assert record["name"] == "AR4-27-6"
    assert record["classification"] == "Finfish Farm"
    assert "1% of notional turnover" in record["note"]
    assert "does not state a yearly total" in record["note"]
    assert "£1,500 a year" in record["note"]
    assert "consented biomass" in record["note"]
    assert _money_keys(record) == []
    assert "1022286" not in record["note"]
    assert "578483" not in record["note"]


def test_shellfish_lists_the_tariffs_and_does_not_pick_one():
    record = aquaculture_lease(
        {"Lease_Description": "SH-96-5", "Property_Classification": "Shellfish Fm"}
    )
    assert record is not None
    note = record["note"]
    assert "£0.205" in note and "£200" in note
    assert "£0.265" in note and "£175" in note
    assert "£0.055" in note
    assert "does not name the species" in note
    assert "10%" not in note
    assert _money_keys(record) == []


def test_seaweed_farm_keeps_the_minimum_as_a_floor():
    record = aquaculture_lease(
        {"Lease_Description": "AR2-41-52", "Property_Classification": "Seaweed Farming"}
    )
    assert record is not None
    assert "£0.055" in record["note"]
    assert "£135" in record["note"]
    assert "published floor, not this site's rent" in record["note"]
    assert _money_keys(record) == []


def test_seaweed_harvest_does_not_take_the_farm_tariff():
    record = aquaculture_lease(
        {
            "Lease_Description": "IN6-78-3",
            "Property_Classification": "Seaweed Harvesting",
        }
    )
    assert record is not None
    assert "not applied" in record["note"]
    assert "£0.055" not in record["note"]
    assert "£135" not in record["note"]


def test_equipment_has_no_separate_published_rent():
    record = aquaculture_lease(
        {"Lease_Description": "AR3-18-25", "Property_Classification": "Aqua Equipment"}
    )
    assert record is not None
    assert record["note"].endswith("No separate rent is published for this class.")
    assert _money_keys(record) == []


def test_unknown_class_is_not_given_a_tariff():
    record = aquaculture_lease({"Property_Classification": "Kelp Trial"})
    assert record is not None
    assert "no published rent rule" in record["note"]
    assert "£" not in record["note"]


def test_wind_says_the_yearly_rent_is_unpublished():
    record = agreement_lease(
        {
            "Property_Description": "Robin Rigg East",
            "Tenant_Name": "RWE Renewables UK",
            "Lease_Type_Description": "Lease Marine",
            "Project_Phase": "Operational",
            "Option_Fee": 85900000,
        },
        "wind",
        "Offshore wind",
    )
    assert record is not None
    assert record["agreement"] == "Lease Marine"
    assert record["phase"] == "Operational"
    assert "yearly rent is not in the open file" in record["note"]
    assert "RWE" not in record["note"]
    assert "1.07" not in record["note"]
    assert "699" not in record["note"]
    assert "option" not in record["note"].lower()
    assert _money_keys(record) == []


def test_empty_and_blank_payloads_have_no_lease():
    assert seabed_record(None) == {"leases": []}
    assert seabed_record({}) == {"leases": []}
    assert seabed_record({"aquaculture": {"features": []}, "wind": {}}) == {"leases": []}
    assert aquaculture_lease({}) is None
    assert agreement_lease({"Tenant_Name": "Someone"}, "wave", "Wave lease") is None


def test_record_keeps_aquaculture_ahead_of_an_unpublished_agreement():
    body = seabed_record(
        {
            "wind": {
                "features": [
                    {
                        "attributes": {
                            "Property_Description": "Robin Rigg East",
                            "Lease_Type_Description": "Lease Marine",
                            "Project_Phase": "Operational",
                        }
                    }
                ]
            },
            "aquaculture": {
                "features": [
                    {
                        "attributes": {
                            "Lease_Description": "AR4-27-6",
                            "Property_Classification": "Finfish Farm",
                        }
                    }
                ]
            },
        }
    )
    assert [row["estate"] for row in body["leases"]] == ["aquaculture", "wind"]
    assert "annual" not in body
    joined = " ".join(row["note"] for row in body["leases"])
    assert "1.07" not in joined
    assert "10%" not in joined


def test_seabed_query_asks_the_lease_service_in_wgs84():
    url = seabed_query_url("aquaculture", 55.914394, -5.415866)
    assert url is not None
    assert url.startswith(
        "https://services3.arcgis.com/nGV4jiurzcahJ9LV/ArcGIS/rest/services/"
        "Aquaculture_Crown_Estate_Scotland/FeatureServer/0/query?"
    )
    assert "inSR=4326" in url
    assert "returnGeometry=false" in url
    assert "Property_Classification" in url
    assert "Tenant_Name" not in url
    assert seabed_query_url("aquaculture", 0, 0) is None
    wind = seabed_query_url("wind", 54.76, -3.70)
    assert wind is not None
    assert "Offshore_Wind_Crown_Estate_Scotland" in wind
    assert "Tenant_Name" not in wind
    assert seabed_query_url("minerals", 56.0, -4.0) is None


def test_engine_does_not_import_the_seabed_notes():
    engine = Path("agr/engine.py").read_text(encoding="utf-8")
    valuation = Path("agr/valuation.py").read_text(encoding="utf-8")
    assert "seabed" not in engine
    assert "seabed" not in valuation
