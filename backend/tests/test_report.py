from agr.report import build_assessment_report, render_report_markdown
from validation.ratio_study import ratio_study_points


def test_assessment_report_structure():
    report = build_assessment_report(55.9533, -3.1883, scenario="full_agr")
    assert report["not_statutory"] is True
    assert report["status"] == "research_estimate"
    assert "report_id" in report
    assert report["roll_lines"]["grid_cell_annual_gbp"] > 0
    assert report["place"]["grid"] == "what3words_3m"
    assert "markdown" in report
    assert "Scot-LAND Assessment Report" in report["markdown"]
    assert "Research estimate" in report["markdown"]


def test_markdown_render_standalone():
    report = build_assessment_report(55.857, -4.198, include_sales=True)
    md = render_report_markdown(report)
    assert report["report_id"] in md
    assert "Sales cross-check" in md or "synthetic" in md.lower() or "Place" in md


def test_ratio_study_ward_points():
    points = [(55.857, -4.198), (55.8565, -4.1975), (55.8572, -4.199)]
    study = ratio_study_points(points)
    assert study["samples"] == 3
    assert "rows" in study
    # Fixture sales nearby → some ratios may exist
    assert study["ratios_available"] >= 0
