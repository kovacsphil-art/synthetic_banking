"""Bounded aggregate-backed sampling implementations; no proposal-text interpretation."""

import hashlib
import math
import numpy as np


class DependencyEvidenceError(ValueError):
    """A selected implementation cannot safely use the supplied measured evidence."""


def _fail(reason):
    raise DependencyEvidenceError(reason)


def _number(value):
    if isinstance(value, (bool, str)) or value is None:
        _fail("invalid_dependency_profile")
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        _fail("invalid_dependency_profile")
    if not math.isfinite(value):
        _fail("invalid_dependency_profile")
    return value


def _count(value):
    number = _number(value)
    if number < 0 or number != int(number):
        _fail("invalid_dependency_profile")
    return int(number)


def _rng(seed, name):
    if isinstance(seed, bool) or int(seed) != seed or seed < 0:
        raise ValueError("Use a nonnegative integer generation seed.")
    words = np.frombuffer(hashlib.sha256(name.encode()).digest()[:16], dtype="<u4")
    return np.random.default_rng(np.random.SeedSequence([int(seed), *map(int, words)]))


def _missing(value):
    return value is None or isinstance(value, (float, np.floating)) and np.isnan(value)


def conditional_categorical_v1(source, table, parent, child, parent_values, child_values,
                               summaries, cells, seed):
    """Sample complete-case SOURCE cross-tabs; retain existing generated null masks.

    Sparse/incomplete/unsupported evidence skips the whole proposal. No smoothing,
    borrowing across parents or extrapolation to unobserved parent values occurs.
    """
    identity = dict(run_id=source, profile_type="SOURCE", logical_table_name=table,
                    parent_column=parent, child_column=child)
    selected = [r for r in summaries if all(r.get(k) == v for k, v in identity.items())]
    if len(selected) != 1:
        _fail("missing_categorical_profile")
    summary = selected[0]
    n = _count(summary.get("sample_size"))
    if (summary.get("profile_status") != "PROFILED" or n < 100
            or not .95 <= _number(summary.get("complete_case_fraction")) <= 1
            or not .1 <= _number(summary.get("cramers_v")) <= 1 + 1e-8):
        _fail("insufficient_categorical_support")
    selected = [r for r in cells if all(r.get(k) == v for k, v in identity.items())]
    expected = _count(summary.get("cell_count"))
    if not 1 <= expected <= 200 or len(selected) != expected:
        _fail("incomplete_categorical_profile")
    counts, parents, children = {}, {}, {}
    for row in selected:
        p, c = row.get("parent_value"), row.get("child_value")
        if not isinstance(p, str) or not isinstance(c, str) or (p, c) in counts:
            _fail("invalid_categorical_profile")
        count = _count(row.get("record_count"))
        counts[p, c] = count
        parents[p] = parents.get(p, 0) + count
        children[c] = children.get(c, 0) + count
    if (sum(counts.values()) != n or len(parents) * len(children) != expected
            or len(parents) != _count(summary.get("parent_cardinality"))
            or len(children) != _count(summary.get("child_cardinality"))
            or set(counts) != {(p, c) for p in parents for c in children}):
        _fail("incomplete_categorical_profile")
    if min(parents.values()) < 30:
        _fail("sparse_categorical_parent")
    for row in selected:
        p, c = row["parent_value"], row["child_value"]
        if (_count(row.get("parent_count")) != parents[p]
                or _count(row.get("child_count")) != children[c]
                or not math.isclose(_number(row.get("conditional_proportion")), counts[p, c] / parents[p], abs_tol=1e-8)):
            _fail("invalid_categorical_profile")
    p, original = np.asarray(parent_values, dtype=object), np.asarray(child_values, dtype=object)
    if p.ndim != 1 or p.shape != original.shape:
        raise ValueError("Categorical parent and child rows must be aligned.")
    eligible = np.array([not _missing(a) and not _missing(b) for a, b in zip(p, original)])
    if any(value not in parents for value in p[eligible]):
        _fail("unsupported_categorical_parent")
    output = original.copy()
    rng = _rng(seed, f"{table}.{parent}->{child}:conditional_categorical_v1")
    values = np.array(sorted(children), dtype=object)
    for parent_value in sorted(parents):
        mask = eligible & (p == parent_value)
        probabilities = np.array([counts[parent_value, c] / parents[parent_value] for c in values])
        output[mask] = rng.choice(values, int(mask.sum()), p=probabilities)
    return output, int(eligible.sum())


def conditional_numeric_rank_v1(source, parent_values, child_values, evidence, seed):
    """Couple existing balance draws to measured credit-limit quartile distributions.

    Conditional quantiles supply ordering scores, not replacement marginal values.
    Reordering preserves the complete finite child multiset before existing caps.
    """
    identity = dict(run_id=source, profile_type="SOURCE", entity_name="ACCOUNT",
                    variable_1="TKQ_ACCOUNT.CREDIT_LIMIT_AMT",
                    variable_2="TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT")
    selected = [r for r in evidence if all(r.get(k) == v for k, v in identity.items())]
    globals_ = [r for r in selected if r.get("scope") == "GLOBAL"]
    if len(globals_) != 1:
        _fail("missing_numeric_dependency_profile")
    g = globals_[0]
    if (g.get("profile_status") != "PROFILED" or _count(g.get("pair_count")) < 200
            or not .95 <= _number(g.get("pair_fraction")) <= 1
            or not .1 <= abs(_number(g.get("pearson_correlation"))) <= 1 + 1e-8):
        _fail("insufficient_numeric_support")
    cuts = [_number(g.get(k)) for k in ("x_p25", "x_p50", "x_p75")]
    x_min, x_max = _number(g.get("x_min")), _number(g.get("x_max"))
    y_min, y_max = _number(g.get("y_min")), _number(g.get("y_max"))
    if not x_min <= cuts[0] < cuts[1] < cuts[2] <= x_max or y_min > y_max:
        _fail("invalid_numeric_boundaries")
    groups = [r for r in selected if r.get("scope") == "X_QUARTILE"]
    if len(groups) != 4 or {r.get("segment_value") for r in groups} != {"Q1", "Q2", "Q3", "Q4"}:
        _fail("incomplete_numeric_dependency_profile")
    groups.sort(key=lambda r: r["segment_value"])
    if sum(_count(r.get("pair_count")) for r in groups) != _count(g["pair_count"]):
        _fail("incomplete_numeric_dependency_profile")
    knots = []
    for i, row in enumerate(groups):
        if row.get("profile_status") not in ("PROFILED", "CONSTANT") or _count(row.get("pair_count")) < 30:
            _fail("sparse_numeric_segment")
        if row.get("lower_bound") != (cuts[i-1] if i else None) or row.get("upper_bound") != (cuts[i] if i < 3 else None):
            _fail("invalid_numeric_boundaries")
        values = [_number(row.get(k)) for k in ("y_min", "y_p25", "y_p50", "y_p75", "y_max")]
        if any(a > b for a, b in zip(values, values[1:])) or values[0] < y_min or values[-1] > y_max:
            _fail("invalid_numeric_quantiles")
        knots.append(values)
    x, original = np.asarray(parent_values, dtype=float), np.asarray(child_values, dtype=float)
    if x.ndim != 1 or x.shape != original.shape:
        raise ValueError("Numeric parent and child rows must be aligned.")
    eligible = np.isfinite(x) & np.isfinite(original)
    if np.any(np.isinf(x)) or np.any(np.isinf(original)):
        _fail("unsupported_numeric_value")
    if np.any((x[eligible] < _number(g.get("x_min"))) | (x[eligible] > _number(g.get("x_max")))):
        _fail("unsupported_numeric_parent")
    if np.any((original[eligible] < max(0, _number(g.get("y_min"))))) or np.any(original[eligible] > _number(g.get("y_max"))):
        _fail("unsupported_numeric_value")
    n = int(eligible.sum())
    if n < 2:
        _fail("insufficient_generated_pairs")
    bins = np.searchsorted(cuts, x[eligible], side="left")
    draws = _rng(seed, "credit_limit->balance:conditional_numeric_rank_v1").random(n)
    scores = np.empty(n)
    for i, values in enumerate(knots):
        mask = bins == i
        scores[mask] = np.interp(draws[mask], [0, .25, .5, .75, 1], values)
    coupled = np.empty(n)
    coupled[np.argsort(scores, kind="stable")] = np.sort(original[eligible], kind="stable")
    output = original.copy()
    output[eligible] = coupled
    return output, n


def mean_matched_quantile_candidate(values, probabilities, quantiles, source_mean):
    """Offline candidate: match an inverse-CDF mean while retaining every knot.

    Within each quantile interval replace linear t by t**exponent. The implied
    population mean is A + B/(exponent+1). This function is deliberately NOT in
    the active registry: final caps and other derived amounts need joint review.
    It draws no random numbers, extrapolates no tails, and retains NaN masks.
    """
    p, q = np.asarray(probabilities, dtype=float), np.asarray(quantiles, dtype=float)
    x = np.asarray(values, dtype=float)
    target = _number(source_mean)
    if (p.ndim != 1 or q.shape != p.shape or len(p) < 2 or x.ndim != 1
            or not np.all(np.isfinite(p)) or not np.all(np.isfinite(q))
            or p[0] != 0 or p[-1] != 1 or np.any(np.diff(p) <= 0) or np.any(np.diff(q) < 0)):
        raise ValueError("Use finite ordered quantiles and increasing probabilities spanning zero to one.")
    finite = np.isfinite(x)
    if np.any(np.isinf(x)) or np.any(x[finite] < q[0]) or np.any(x[finite] > q[-1]):
        raise ValueError("Candidate values must remain within the measured quantile support.")
    widths = np.diff(p)
    lower, span = float(np.dot(widths, q[:-1])), float(np.dot(widths, np.diff(q)))
    if span == 0:
        if target != q[0]:
            raise ValueError("The measured mean is inconsistent with constant quantiles.")
        exponent = 1.
    elif not lower < target < lower + span:
        raise ValueError("The measured mean is outside the feasible quantile-interval bounds.")
    else:
        exponent = span/(target-lower)-1
    if not math.isfinite(exponent) or exponent <= 0:
        raise ValueError("The fitted interpolation exponent must be finite and positive.")
    indices = np.clip(np.searchsorted(q, x[finite], side="right")-1, 0, len(q)-2)
    a, b = q[indices], q[indices+1]
    t = np.divide(x[finite]-a, b-a, out=np.zeros_like(a), where=b>a)
    output = x.copy()
    output[finite] = a+(b-a)*np.clip(t, 0, 1)**exponent
    return output, dict(exponent=exponent, implied_linear_mean=lower+span/2,
                        target_mean=target, implied_calibrated_mean=lower+span/(exponent+1))
