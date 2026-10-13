"""Unit tests for REPD onshore-wind CSV filter (no network, no PostGIS)."""

from __future__ import annotations

from pathlib import Path

from etl.ingest_repd_onshore_wind import classify_row, scotland_onshore_wind_rows

# SYNTHETIC REPD-shaped rows (cp1252). Not real DESNZ figures.
FIXTURE = """\
Old Ref ID,Ref ID,Record Last Updated (dd/mm/yyyy),Operator (or Applicant),Site Name,Technology Type,Storage Type,Storage Co-location REPD Ref ID,Installed Capacity (MWelec),Share Community Scheme,CHP Enabled,CfD Allocation Round,RO Banding (ROC/MWh),FiT Tariff (p/kWh),CfD Capacity (MW),Turbine Capacity (MW),No. of Turbines,Height of Turbines (m),Mounting Type for Solar,Development Status,Development Status (short),Are they re-applying (New REPD Ref),Are they re-applying (Old REPD Ref) ,Address,County,Region,Country,Post Code,X-coordinate,Y-coordinate,Planning Authority,Planning Application Reference,Appeal Reference,Secretary of State Reference,Type of Secretary of State Intervention,Judicial Review,Offshore Wind Round,Planning Application Submitted,Planning Application Withdrawn,Planning Permission Refused,Appeal Lodged,Appeal Withdrawn,Appeal Refused,Appeal Granted,Planning Permission  Granted,Secretary of State - Intervened,Secretary of State - Refusal,Secretary of State - Granted,Planning Permission Expired,Under Construction,Operational,Heat Network Ref,Solar Site Area (sqm)
AA1,100,01/01/2024,Test Op,Glasgow Fixture Wind,Wind Onshore,,,10,,No,,,,,,,,,Operational,Operational,,,Somewhere,Lanarkshire,Scotland,Scotland,G1 1AA,259273,665216,Glasgow City,,,,,,,,,,,,,,,,,,,,,,,,,
AA2,101,01/01/2024,Test Op,England Fixture,Wind Onshore,,,5,,No,,,,,,,,,Operational,Operational,,,Somewhere,Devon,South West,England,EX1 1AA,292000,72000,Devon,,,,,,,,,,,,,,,,,,,,,,,,,
AA3,102,01/01/2024,Test Op,Offshore Fixture,Wind Offshore,,,50,,No,,,,,,,,,Operational,Operational,,,Somewhere,Highland,Scotland,Scotland,IV1 1AA,265000,830000,Highland,,,,,,,,,,,,,,,,,,,,,,,,,
"""


def test_scotland_onshore_wind_filters_reprojects_and_tags(tmp_path: Path):
    csv_path = tmp_path / "repd_sample.csv"
    csv_path.write_text(FIXTURE, encoding="cp1252")
    rows = scotland_onshore_wind_rows(csv_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["ref_id"] == "100"
    assert row["technology_type"] == "Wind Onshore"
    assert row["installed_capacity_mw"] == 10.0
    assert row["development_status_short"] == "Operational"
    assert row["value_tier"] == "market"
    assert row["publication_status"] == "ok"
    assert row["country"] == "Scotland"
    assert 55.7 < row["lat"] < 56.0
    assert -4.4 < row["lng"] < -4.1


def test_classify_row_market_ok_and_blocked():
    assert classify_row(
        technology="Wind Onshore",
        capacity_mw=12.0,
        status="Operational",
        status_short="Operational",
    ) == ("market", "ok")
    assert classify_row(
        technology="Wind Onshore",
        capacity_mw=None,
        status="Under Construction",
        status_short="Under Construction",
    ) == ("market", "ok")
    assert classify_row(
        technology="Wind Onshore",
        capacity_mw=None,
        status=None,
        status_short=None,
    ) == ("market", "blocked")
