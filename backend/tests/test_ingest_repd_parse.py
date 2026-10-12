"""Unit tests for REPD CSV Scotland filter (no network, no PostGIS)."""

from __future__ import annotations

from pathlib import Path

from etl.ingest_repd import _scotland_rows

FIXTURE = """\
Old Ref ID,Ref ID,Record Last Updated (dd/mm/yyyy),Operator (or Applicant),Site Name,Technology Type,Storage Type,Storage Co-location REPD Ref ID,Installed Capacity (MWelec),Share Community Scheme,CHP Enabled,CfD Allocation Round,RO Banding (ROC/MWh),FiT Tariff (p/kWh),CfD Capacity (MW),Turbine Capacity (MW),No. of Turbines,Height of Turbines (m),Mounting Type for Solar,Development Status,Development Status (short),Are they re-applying (New REPD Ref),Are they re-applying (Old REPD Ref) ,Address,County,Region,Country,Post Code,X-coordinate,Y-coordinate,Planning Authority,Planning Application Reference,Appeal Reference,Secretary of State Reference,Type of Secretary of State Intervention,Judicial Review,Offshore Wind Round,Planning Application Submitted,Planning Application Withdrawn,Planning Permission Refused,Appeal Lodged,Appeal Withdrawn,Appeal Refused,Appeal Granted,Planning Permission  Granted,Secretary of State - Intervened,Secretary of State - Refusal,Secretary of State - Granted,Planning Permission Expired,Under Construction,Operational,Heat Network Ref,Solar Site Area (sqm)
AA1,100,01/01/2024,Test Op,Glasgow Fixture Wind,Wind Onshore,,,10,,No,,,,,,,,,Operational,Operational,,,Somewhere,Lanarkshire,Scotland,Scotland,G1 1AA,259273,665216,Glasgow City,,,,,,,,,,,,,,,,,,,,,,,,,
AA2,101,01/01/2024,Test Op,England Fixture,Wind Onshore,,,5,,No,,,,,,,,,Operational,Operational,,,Somewhere,Devon,South West,England,EX1 1AA,292000,72000,Devon,,,,,,,,,,,,,,,,,,,,,,,,,
"""


def test_scotland_rows_filters_and_reprojects(tmp_path: Path):
    csv_path = tmp_path / "repd_sample.csv"
    csv_path.write_text(FIXTURE, encoding="cp1252")
    rows = _scotland_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["ref_id"] == "100"
    assert rows[0]["country"] == "Scotland"
    assert 55.7 < rows[0]["lat"] < 56.0
    assert -4.4 < rows[0]["lng"] < -4.1
