"""Evaluate supplied request counters, never scrape or infer missing telemetry."""

from decimal import Decimal, InvalidOperation, localcontext

RULES = (("fast", "5m", "1h", Decimal("14.4")), ("slow", "30m", "6h", Decimal(6)))
WINDOWS = frozenset({"5m", "1h", "30m", "6h"})


class InputError(ValueError):
    """Malformed or incompatible counters."""


def decimal(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise InputError(f"{name} must be an exact decimal string or integer")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise InputError(f"{name} is not decimal") from exc
    if not result.is_finite():
        raise InputError(f"{name} must be finite")
    return result


def count(value, name):
    if type(value) is not int or value < 0:
        raise InputError(f"{name} must be a non-negative integer")
    return value


def evaluate(raw):
    """Evaluate fixed two-window burn rules using supplied, aligned snapshots.

    Each rule requires BOTH its short and long window to reach the threshold.
    Window counters must share the same end time and error definition; the caller
    establishes that assumption. Missing / zero-traffic windows are unknown.
    """
    if not isinstance(raw, dict) or set(raw) != {"target", "windows"}:
        raise InputError("input requires exactly target and windows")
    target = decimal(raw["target"], "target")
    if not Decimal(0) < target < Decimal(1):
        raise InputError("target must be strictly between 0 and 1")
    snapshots = raw["windows"]
    if not isinstance(snapshots, dict) or set(snapshots) - WINDOWS:
        raise InputError("windows must contain only 5m, 1h, 30m, 6h")
    metrics = {}
    rates = {}
    with localcontext() as ctx:
        ctx.prec = 40
        budget = 1 - target
        for name in sorted(WINDOWS):
            snapshot = snapshots.get(name)
            if snapshot is None:
                metrics[name] = {"state": "missing"}
                continue
            if not isinstance(snapshot, dict) or set(snapshot) != {"requests", "errors"}:
                raise InputError(f"{name} requires exactly requests and errors")
            requests = count(snapshot["requests"], f"{name}.requests")
            errors = count(snapshot["errors"], f"{name}.errors")
            if errors > requests:
                raise InputError(f"{name}: errors cannot exceed requests")
            if not requests:
                metrics[name] = {"state": "no_traffic", "requests": 0, "errors": 0}
                continue
            ratio = Decimal(errors) / Decimal(requests)
            burn = ratio / budget
            rates[name] = burn
            metrics[name] = {
                "state": "ok",
                "requests": requests,
                "errors": errors,
                "error_ratio": str(ratio),
                "burn_rate": str(burn),
            }
        rules = []
        for name, short, long, threshold in RULES:
            known = short in rates and long in rates
            state = (
                ("firing" if rates[short] >= threshold and rates[long] >= threshold else "clear")
                if known
                else "insufficient_data"
            )
            rules.append(
                {
                    "name": name,
                    "short_window": short,
                    "long_window": long,
                    "threshold": str(threshold),
                    "state": state,
                }
            )
        states = {rule["state"] for rule in rules}
        overall = (
            "firing"
            if "firing" in states
            else "insufficient_data"
            if "insufficient_data" in states
            else "clear"
        )
        return {
            "target": str(target),
            "allowed_error_ratio": str(budget),
            "state": overall,
            "windows": metrics,
            "rules": rules,
        }
