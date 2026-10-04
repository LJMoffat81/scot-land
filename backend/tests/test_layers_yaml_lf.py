"""layers.yaml stamp hash ignores CRLF."""

from agr.config import load_config
from agr.layers import LAYERS_PATH, _file_sha12_lf, engine_stamp


def test_file_sha12_lf_matches_for_lf_and_crlf(tmp_path):
    text = "valuation:\n  keys:\n    - a\n"
    lf_path = tmp_path / "lf.yaml"
    crlf_path = tmp_path / "crlf.yaml"
    lf_path.write_bytes(text.encode("utf-8"))
    crlf_path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert _file_sha12_lf(str(lf_path)) == _file_sha12_lf(str(crlf_path))
    assert len(_file_sha12_lf(str(lf_path))) == 12


def test_layers_yaml_sha256_is_the_lf_normalised_hash():
    stamp = engine_stamp(load_config())
    assert stamp["config"]["layers_yaml_sha256"] == _file_sha12_lf(str(LAYERS_PATH))
