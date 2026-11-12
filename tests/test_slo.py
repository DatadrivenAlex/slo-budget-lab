import copy
import json
from decimal import Decimal

import pytest

from slolab.cli import main
from slolab.core import InputError, evaluate


def sample(errors=0, requests=10000):
    return {
        "target": "0.999",
        "windows": {
            name: {"requests": requests, "errors": errors} for name in ["5m", "1h", "30m", "6h"]
        },
    }


def test_clear():
    report = evaluate(sample(1))
    assert report["state"] == "clear"
    assert Decimal(report["windows"]["5m"]["burn_rate"]) == Decimal("0.1")


def test_fast_boundary_inclusive():
    report = evaluate(sample(144))
    assert report["rules"][0]["state"] == "firing"
    assert Decimal(report["windows"]["5m"]["burn_rate"]) == Decimal("14.4")


def test_slow_boundary():
    report = evaluate(sample(60))
    assert report["rules"][0]["state"] == "clear"
    assert report["rules"][1]["state"] == "firing"


def test_short_spike_alone_does_not_fire():
    raw = sample(0)
    raw["windows"]["5m"]["errors"] = 1000
    assert evaluate(raw)["state"] == "clear"


def test_long_window_alone_does_not_fire():
    raw = sample(0)
    raw["windows"]["1h"]["errors"] = 1000
    assert evaluate(raw)["state"] == "clear"


def test_missing_not_healthy():
    raw = sample()
    del raw["windows"]["5m"]
    report = evaluate(raw)
    assert report["state"] == "insufficient_data"
    assert report["windows"]["5m"]["state"] == "missing"


def test_empty_windows():
    assert evaluate({"target": "0.99", "windows": {}})["state"] == "insufficient_data"


def test_no_traffic_unknown():
    report = evaluate(sample(0, 0))
    assert report["state"] == "insufficient_data"
    assert report["windows"]["1h"]["state"] == "no_traffic"


def test_known_alert_survives_other_missing_rule():
    raw = sample(200)
    del raw["windows"]["30m"]
    assert evaluate(raw)["state"] == "firing"


def test_input_unchanged():
    raw = sample(3)
    previous = copy.deepcopy(raw)
    evaluate(raw)
    assert raw == previous


@pytest.mark.parametrize(
    "target", ["0", "1", "-0.1", "1.1", "NaN", "Infinity", "oops", True, 0.999, None]
)
def test_invalid_target(target):
    raw = sample()
    raw["target"] = target
    with pytest.raises(InputError):
        evaluate(raw)


@pytest.mark.parametrize("value", [-1, True, 1.5, "10", None])
@pytest.mark.parametrize("field", ["requests", "errors"])
def test_invalid_counts(field, value):
    raw = sample()
    raw["windows"]["5m"][field] = value
    with pytest.raises(InputError):
        evaluate(raw)


def test_errors_exceed_requests():
    with pytest.raises(InputError):
        evaluate(sample(2, 1))


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {},
        {
            "target": "0.9",
            "windows": [],
        },
        {"target": "0.9", "windows": {"1d": {}}},
        {"target": "0.9", "windows": {"5m": {}}},
    ],
)
def test_invalid_structure(raw):
    with pytest.raises(InputError):
        evaluate(raw)


def test_decimal_precision_not_global():
    from decimal import getcontext

    before = getcontext().prec
    evaluate(sample(1, 3))
    assert getcontext().prec == before


def test_all_errors():
    report = evaluate(sample(10000))
    assert Decimal(report["windows"]["1h"]["error_ratio"]) == 1
    assert report["state"] == "firing"


@pytest.mark.parametrize("errors,requests,code", [(1, 10000, 0), (200, 10000, 1), (0, 0, 3)])
def test_cli_status(tmp_path, capsys, errors, requests, code):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(sample(errors, requests)))
    assert main([str(path)]) == code
    assert "state" in json.loads(capsys.readouterr().out)


def test_cli_bad_json(tmp_path, capsys):
    path = tmp_path / "input.json"
    path.write_text("{")
    assert main([str(path)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_cli_missing_file(tmp_path, capsys):
    assert main([str(tmp_path / "missing")]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
