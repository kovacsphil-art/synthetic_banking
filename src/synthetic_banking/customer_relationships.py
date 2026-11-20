"""Explicit customer graph generation from aggregate SOURCE evidence."""

from collections import Counter
import heapq
import json
import math

import numpy as np

from synthetic_banking.relationship_profiles import FROM, TO, FORWARD, REVERSE, TABLE


IMPLEMENTATION_VERSION = "customer_relationships_v1"
AUDIT_TABLE = "customer_relationship_generation_log"
METADATA_COLUMNS = {"LAST_UPDT_CHANNEL_CD", "LAST_UPDT_TRANSIT_NUM", "ORIGINATING_APP_CD"}
_TEMPORAL = {"DATE", "TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ"}
_NUMERIC = {"BYTE", "TINYINT", "SHORT", "SMALLINT", "INT", "INTEGER", "LONG", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"}


def _canonical(rows):
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))


def _allocation(rows, field, n, rng):
    if not n:
        return []
    rows = _canonical(rows)
    if not rows or any(row[field] <= 0 for row in rows):
        raise ValueError("Missing/invalid SOURCE customer relationship histogram.")
    weights = np.asarray([row[field] for row in rows], dtype=float)
    expected = n * weights / weights.sum()
    counts = np.floor(expected).astype(int)
    counts[np.argsort(-(expected - counts), kind="stable")[:n - int(counts.sum())]] += 1
    indexes = np.repeat(np.arange(len(rows)), counts)
    rng.shuffle(indexes)
    return [rows[index] for index in indexes]


def _trim(degrees, total, rng):
    if total < 0 or total > int(degrees.sum()):
        raise ValueError("Invalid graph degree reconciliation target.")
    extra = int(degrees.sum()) - total
    if extra:
        stubs = np.repeat(np.arange(len(degrees)), degrees)
        rng.shuffle(stubs)
        degrees -= np.bincount(stubs[:extra], minlength=len(degrees))


def _mutual_graph(degrees, rng):
    heap = [(-int(degree), float(rng.random()), i) for i, degree in enumerate(degrees) if degree]
    heapq.heapify(heap)
    edges = []
    while heap:
        negative, _, node = heapq.heappop(heap)
        neighbors = [heapq.heappop(heap) for _ in range(min(-negative, len(heap)))]
        for count, tie, other in neighbors:
            edges.append((node, other))
        for count, tie, other in neighbors:
            if count + 1 < 0:
                heapq.heappush(heap, (count + 1, tie, other))
    return edges


def _directed_graph(outgoing, incoming, mutual, rng):
    size = min(int(outgoing.sum()), int(incoming.sum()))
    _trim(outgoing, size, rng)
    _trim(incoming, size, rng)
    origins = np.repeat(np.arange(len(outgoing)), outgoing)
    targets = np.repeat(np.arange(len(incoming)), incoming)
    rng.shuffle(origins)
    rng.shuffle(targets)
    edges = list(zip(origins.tolist(), targets.tolist()))
    counts = Counter(edges)
    blocked = {frozenset(pair) for pair in mutual}

    def available(a, b):
        return a != b and frozenset((a, b)) not in blocked and not counts[a, b] and not counts[b, a]

    for _ in range(3):
        bad = [i for i, (a, b) in enumerate(edges) if a == b or counts[a, b] > 1 or counts[b, a] or frozenset((a, b)) in blocked]
        if not bad:
            break
        rng.shuffle(bad)
        for i in bad:
            a, b = edges[i]
            counts[a, b] -= 1
            if available(a, b):
                counts[a, b] += 1
                continue
            fixed = False
            for j in rng.integers(0, max(len(edges), 1), size=100):
                if j == i:
                    continue
                c, d = edges[j]
                counts[c, d] -= 1
                if (available(a, d) and available(c, b) and (a, d) != (c, b) and (a, d) != (b, c)):
                    edges[i], edges[j] = (a, d), (c, b)
                    counts[a, d] += 1
                    counts[c, b] += 1
                    fixed = True
                    break
                counts[c, d] += 1
            if not fixed:
                counts[a, b] += 1
    accepted = set()
    result = []
    for a, b in edges:
        if a != b and (a, b) not in accepted and (b, a) not in accepted and frozenset((a, b)) not in blocked:
            accepted.add((a, b))
            result.append((a, b))
    return result


def _numeric(row, n, rng):
    names = ("min_value", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "max_value")
    if row is None or any(row.get(field) is None or not math.isfinite(float(row[field])) for field in names):
        raise ValueError("Non-null relationship values need finite measured SOURCE quantiles.")
    values = np.asarray([row[field] for field in names], dtype=float)
    if np.any(np.diff(values) < 0):
        raise ValueError("Relationship SOURCE quantiles are not monotonic.")
    return np.interp(rng.random(n), [0, .01, .05, .25, .5, .75, .95, .99, 1], values)


def generate_customer_relationships(person_ids, profile, seed, date_sampler, *, max_rows=1_000_000,
                                    max_adjustment_fraction=.05):
    """Generate only from synthetic PERSON IDs; return data arrays and an aggregate audit plan.

    Degree histograms use unique directed/reciprocal neighbors; separately sampled
    dyad multiplicities reproduce repeated relationship records. Small finite
    populations can require logged stub reductions. Large reductions fail closed.
    """
    ids = list(person_ids)
    if len(set(ids)) != len(ids) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("CUSTOMER_RELATIONSHIP requires unique non-null generated PERSON IDs.")
    if date_sampler.source_run_id != profile["source_run_id"] or date_sampler.seed != seed:
        raise ValueError("Relationship attributes and dates must use the same SOURCE run and seed.")
    if max_rows < 0 or not 0 <= max_adjustment_fraction <= 1:
        raise ValueError("Set a nonnegative row budget and a degree adjustment fraction between zero and one.")
    summaries = profile["customer_relationship_summary"]
    if len(summaries) != 1:
        raise ValueError("One SOURCE customer relationship summary is required.")
    summary = summaries[0]
    source = profile["source_run_id"]
    for name, rows in profile.items():
        if isinstance(rows, list):
            for row in rows:
                if row.get("run_id") != source or row.get("profile_type") not in (None, "SOURCE"):
                    raise ValueError("Relationship generation cannot consume another run or GENERATED evidence.")
    schema = {row["column_name"].upper(): row for row in profile["column_quality"]}
    if not {FROM, TO, FORWARD, REVERSE} <= schema.keys():
        raise ValueError("Pinned SOURCE relationship schema is missing endpoints/directional type codes.")
    fields = {row["column_name"].upper(): row for row in profile["customer_relationship_field_profile"]}
    if set(fields) != set(schema) - {FROM, TO}:
        raise ValueError("Relationship field profiles must cover the exact pinned SOURCE schema.")
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 0xC0570]))
    n = len(ids)
    if summary["person_count"] and n * summary["valid_rows"] / summary["person_count"] > max_rows:
        raise ValueError("Projected CUSTOMER_RELATIONSHIP population exceeds the configured row budget.")
    degree_rows = profile["customer_relationship_degree_profile"]
    if sum(row["party_count"] for row in degree_rows) != summary["person_count"]:
        raise ValueError("SOURCE relationship degree profile must include all PERSON records, including zero-degree parties.")
    if summary["valid_rows"] and not summary["person_count"]:
        raise ValueError("SOURCE relationships need a nonempty PERSON population.")
    sampled = _allocation(degree_rows, "party_count", n, rng) if summary["person_count"] else []
    if sampled:
        desired = np.asarray([[row[field] for field in ("outgoing_count", "incoming_count", "reciprocal_count", "self_count")] for row in sampled], dtype=int)
    else:
        desired = np.zeros((n, 4), dtype=int)
    if np.any(desired < 0) or np.any(desired[:, 3] > 1):
        raise ValueError("Invalid SOURCE degree components.")
    original_stubs = int(desired[:, :3].sum())
    if original_stubs > 2 * max_rows:
        raise ValueError("Relationship degree allocation exceeds the configured graph memory/row budget.")
    capacity = max(0, n - 1)
    mutual_degrees = np.minimum(desired[:, 2], capacity)
    if int(mutual_degrees.sum()) % 2:
        positives = np.flatnonzero(mutual_degrees)
        mutual_degrees[int(rng.choice(positives))] -= 1
    mutual = _mutual_graph(mutual_degrees, rng)
    mutual_counts = np.bincount([node for edge in mutual for node in edge], minlength=n)
    outgoing = np.minimum(desired[:, 0], capacity - mutual_counts)
    incoming = np.minimum(desired[:, 1], capacity - mutual_counts)
    directed = _directed_graph(outgoing.copy(), incoming.copy(), mutual, rng)
    self_edges = [(i, i) for i in np.flatnonzero(desired[:, 3])]
    if self_edges and not summary["self_rows"]:
        raise ValueError("Self relationships are unsupported by this SOURCE run.")
    adjusted = original_stubs - 2 * (len(directed) + len(mutual))
    if adjusted < 0 or adjusted > max(2, math.ceil(max_adjustment_fraction * original_stubs)):
        raise ValueError(f"Generated PERSON population cannot realize the SOURCE degree patterns within the {max_adjustment_fraction:.0%} adjustment budget; increase population or review the profile.")
    dyads = profile["customer_relationship_dyad_profile"]
    templates = profile["customer_relationship_type_profile"]
    core = {name: [] for name in (FROM, TO, FORWARD, REVERSE)}
    null_masks = {name: [] for name in fields}

    def append(a, b, first, second, nulls):
        mask = set((nulls or "").split("|")) - {""}
        if not mask <= fields.keys() or ((first is None) != (FORWARD in mask)) or ((second is None) != (REVERSE in mask)):
            raise ValueError("Relationship SOURCE null masks/type codes are inconsistent.")
        core[FROM].append(ids[a])
        core[TO].append(ids[b])
        core[FORWARD].append(first)
        core[REVERSE].append(second)
        for name in fields:
            null_masks[name].append(name in mask)
        if len(core[FROM]) > max_rows:
            raise ValueError("CUSTOMER_RELATIONSHIP row budget exceeded; review source density/multiplicity.")

    for kind, edges in (("DIRECTED", directed), ("RECIPROCAL", mutual), ("SELF", self_edges)):
        multiplicities = _allocation([row for row in dyads if row["edge_kind"] == kind], "dyad_count", len(edges), rng)
        # Templates couple both directional code pairs and both null masks for reciprocal rows.
        counts = [(int(row["forward_count"]), int(row["reverse_count"])) for row in multiplicities]
        if any(a < 1 or b < (1 if kind == "RECIPROCAL" else 0) for a, b in counts):
            raise ValueError("Invalid SOURCE dyad multiplicity.")
        template_count = len(edges) if kind == "RECIPROCAL" else sum(a for a, b in counts)
        paired_templates = iter(_allocation([row for row in templates if row["edge_kind"] == kind], "record_count", template_count, rng))
        for (a, b), (forward_n, reverse_n) in zip(edges, counts):
            if kind == "RECIPROCAL":
                template = next(paired_templates)
            elif reverse_n:
                raise ValueError("One-way/self SOURCE dyads cannot have reverse multiplicities.")
            if kind == "RECIPROCAL" and rng.random() < .5:
                a, b = b, a
            for _ in range(forward_n):
                if kind != "RECIPROCAL":
                    template = next(paired_templates)
                append(a, b, template["forward_from_to"], template["forward_to_from"], template["forward_nulls"])
            for _ in range(reverse_n):
                append(b, a, template["reverse_from_to"], template["reverse_to_from"], template["reverse_nulls"])
    count = len(core[FROM])
    data = {schema[name]["column_name"]: np.asarray(values, dtype=object) for name, values in core.items()}
    masks = {name: np.asarray(values, dtype=bool) for name, values in null_masks.items()}
    ownership = {(row["from_to"], row["to_from"]): row for row in profile["customer_relationship_ownership_profile"]}
    if any(row["invalid_count"] for row in ownership.values()):
        raise ValueError("SOURCE ownership percentages outside [0, 100] must be reviewed before generation.")
    numeric = {row["column_name"].upper(): row for row in profile["numeric_profile"]}
    categories = {}
    for row in profile["category_profile"]:
        categories.setdefault(row["column_name"].upper(), []).append(row)
    for name, field in fields.items():
        if name in (FORWARD, REVERSE):
            continue
        kind = field["data_type"].upper().split("(")[0]
        if kind in _TEMPORAL:
            continue
        values = np.full(count, None, dtype=object)
        indexes = np.flatnonzero(~masks[name])
        if len(indexes):
            if name == "OWNERSHIP_PERCENTAGE":
                groups = {}
                for i in indexes:
                    groups.setdefault((core[FORWARD][i], core[REVERSE][i]), []).append(i)
                for key, positions in groups.items():
                    values[positions] = _numeric(ownership.get(key), len(positions), rng)
            elif name in METADATA_COLUMNS:
                if kind in _NUMERIC:
                    draws = _numeric(numeric.get(name), len(indexes), rng)
                    values[indexes] = np.rint(draws).astype("int64") if kind in ("INT", "INTEGER", "BIGINT", "LONG", "SHORT", "SMALLINT") else draws
                else:
                    available = [row for row in categories.get(name, []) if row["category_value"] is not None]
                    if available:
                        available = _canonical(available)
                        weights = np.asarray([row["record_count"] for row in available], dtype=float)
                        values[indexes] = rng.choice([row["category_value"] for row in available], size=len(indexes), p=weights / weights.sum())
                    elif (field["digit_count"] == field["non_null_count"] and field["min_length"] == field["max_length"]
                          and field["max_length"] is not None and 1 <= field["max_length"] <= 12):
                        draws = rng.integers(int(field["numeric_min"]), int(field["numeric_max"]) + 1, size=len(indexes))
                        values[indexes] = [str(value).zfill(field["max_length"]) for value in draws]
                    else:
                        raise ValueError(f"{TABLE}.{name} needs a predefined metadata implementation or measured categories.")
            else:
                raise ValueError(f"Unsupported non-null {TABLE} column {name}; add an explicit implementation.")
        data[field["column_name"]] = values
    date_masks = {field["column_name"]: masks[name] for name, field in fields.items() if field["data_type"].upper().split("(")[0] in _TEMPORAL}
    data.update(date_sampler.generate_table(TABLE, count, null_masks=date_masks))
    for name, field in fields.items():
        column = field["column_name"]
        if column not in data:
            raise ValueError(f"Missing SOURCE date profile for {TABLE}.{column}.")
        actual = np.asarray([value is None or (isinstance(value, np.datetime64) and np.isnat(value)) for value in data[column]])
        if not np.array_equal(actual, masks[name]):
            raise ValueError(f"{TABLE}.{column} changed the profiled relationship null pattern.")
    plan = {
        "implementation_version": IMPLEMENTATION_VERSION, "source_run_id": source, "seed": int(seed),
        "profile_signature": profile["profile_signature"], "source_person_count": summary["person_count"],
        "source_valid_rows": summary["valid_rows"], "source_excluded_endpoint_rows": summary["invalid_endpoint_rows"],
        "generated_person_count": n, "row_count": count, "self_allowed": bool(summary["self_rows"]),
        "self_rows": sum(a == b for a, b in zip(core[FROM], core[TO])),
        "directed_dyads": len(directed), "reciprocal_dyads": len(mutual), "self_dyads": len(self_edges),
        "requested_neighbor_stubs": original_stubs, "removed_neighbor_stubs": adjusted,
        "max_adjustment_fraction": max_adjustment_fraction, "row_budget": max_rows,
        "null_counts": {schema[name]["column_name"]: int(mask.sum()) for name, mask in masks.items()},
        "endpoints_non_null": True,
    }
    return data, plan
