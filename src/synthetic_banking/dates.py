"""SOURCE-month date sampling with explicit null masks and temporal bounds.

Only aggregate profiles are inputs. No row-level SOURCE dates are loaded.
"""

from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
import heapq
import math
import re

import numpy as np

from synthetic_banking.profiling import PROFILE_SCHEMA, _rows
from synthetic_banking.temporal import TEMPORAL_ORDER


SNAPSHOT = "BUSINESSEFFECTIVEDATE"


class DateGenerationError(ValueError):
    """Aggregate SOURCE date support cannot satisfy the requested population."""


def _day(value):
    if value is None or str(value) in ("NaT", "None", "nan"):
        return None
    result = np.datetime64(str(value)[:10], "D")
    return None if np.isnat(result) else int(result.astype("int64"))


@dataclass(frozen=True)
class DateDistribution:
    table: str
    column: str
    starts: np.ndarray
    ends: np.ndarray
    weights: np.ndarray
    null_rate: float | None
    method: str

    def bounds(self, lo, hi, active):
        """Tighten intervals to the first/last actually supported day, including gaps."""
        positions = np.flatnonzero(active)
        if not len(positions):
            return
        if not len(self.starts):
            raise DateGenerationError(f"{self.table}.{self.column}: no non-null SOURCE date support.")
        first = np.searchsorted(self.ends, lo[positions], side="left")
        last = np.searchsorted(self.starts, hi[positions], side="right") - 1
        bad = (first >= len(self.starts)) | (last < 0) | (first > last) | (lo[positions] > hi[positions])
        if bad.any():
            raise DateGenerationError(f"{self.table}.{self.column}: no feasible SOURCE date for {int(bad.sum())} non-null rows; check temporal bounds.")
        lo[positions] = np.maximum(lo[positions], self.starts[first])
        hi[positions] = np.minimum(hi[positions], self.ends[last])

    def draw(self, rng, active, lo, hi):
        result = np.full(len(active), np.datetime64("NaT", "D"))
        self.bounds(lo, hi, active)
        positions = np.flatnonzero(active)
        widths = self.ends - self.starts + 1
        # Chunked conditional CDFs keep memory bounded for long date histories.
        for start in range(0, len(positions), 256):
            selected = positions[start:start + 256]
            left = np.maximum(lo[selected, None], self.starts[None, :])
            right = np.minimum(hi[selected, None], self.ends[None, :])
            overlap = np.maximum(right - left + 1, 0)
            mass = overlap * (self.weights / widths)[None, :]
            cdf = np.cumsum(mass, axis=1)
            totals = cdf[:, -1]
            if not np.all(totals > 0):
                raise DateGenerationError(f"{self.table}.{self.column}: empty conditional SOURCE support.")
            bins = (cdf <= (rng.random(len(selected)) * totals)[:, None]).sum(axis=1)
            last_nonzero = len(self.starts) - 1 - (mass[:, ::-1] > 0).argmax(axis=1)
            bins = np.minimum(bins, last_nonzero)
            a, b = left[np.arange(len(selected)), bins], right[np.arange(len(selected)), bins]
            days = a + np.floor(rng.random(len(selected)) * (b - a + 1)).astype("int64")
            result[selected] = days.astype("datetime64[D]")
        return result


class DateSampler:
    def __init__(self, source_run_id, seed, date_profiles, monthly_profiles, column_quality):
        if not source_run_id or int(seed) != seed or seed < 0:
            raise DateGenerationError("Select a SOURCE run and a nonnegative integer random seed.")
        self.source_run_id, self.seed = source_run_id, int(seed)
        self.models, self.expected_null_counts, self.diagnostics = {}, {}, []
        quality, monthly = {}, defaultdict(list)
        for row in column_quality:
            self._check_run(row)
            key = (row["logical_table_name"], row["column_name"].upper())
            if key in quality:
                raise DateGenerationError("Duplicate column quality in the pinned SOURCE run.")
            quality[key] = row
        for row in monthly_profiles:
            self._check_run(row)
            monthly[row["logical_table_name"], row["column_name"].upper()].append(row)
        for row in date_profiles:
            self._check_run(row)
            table, column = row["logical_table_name"], row["column_name"]
            key = (table, column.upper())
            if key in self.models or key not in quality:
                raise DateGenerationError("Date profiles need unique, matching SOURCE column quality.")
            q = quality[key]
            total, nulls, observed = q["row_count"], q["null_count"], row["non_null_count"]
            if total is None or nulls is None or observed is None or not 0 <= nulls <= total or total - nulls != observed:
                raise DateGenerationError(f"{table}.{column}: inconsistent SOURCE date/null counts.")
            null_rate = nulls / total if total else None
            earliest, latest = _day(row["earliest_date"]), _day(row["latest_date"])
            bins = monthly.get(key, [])
            starts, ends, weights = [], [], []
            method = "ALL_NULL" if total else "EMPTY_SOURCE"
            if observed:
                if earliest is None or latest is None or earliest > latest:
                    raise DateGenerationError(f"{table}.{column}: missing or invalid SOURCE date bounds.")
                if bins:
                    seen = set()
                    for bucket in sorted(bins, key=lambda b: b["month_bucket"]):
                        label, count = bucket["month_bucket"], bucket["record_count"]
                        if label in seen or re.fullmatch(r"\d{4}-\d{2}", label) is None or count is None or count <= 0 or int(count) != count:
                            raise DateGenerationError(f"{table}.{column}: invalid or duplicate SOURCE month bin.")
                        seen.add(label)
                        month = np.datetime64(label, "M")
                        first = int(month.astype("datetime64[D]").astype("int64"))
                        last = int((month + 1).astype("datetime64[D]").astype("int64")) - 1
                        first, last = max(first, earliest), min(last, latest)
                        if first > last or bucket["non_null_count"] != observed or not math.isclose(float(bucket["proportion"]), count / observed, rel_tol=1e-8, abs_tol=1e-10):
                            raise DateGenerationError(f"{table}.{column}: SOURCE month bins disagree with date bounds/counts.")
                        starts.append(first)
                        ends.append(last)
                        weights.append(float(count))
                    if sum(weights) != observed or starts[0] != earliest or ends[-1] != latest:
                        raise DateGenerationError(f"{table}.{column}: incomplete SOURCE monthly profile; re-profile SOURCE.")
                    method = "MONTHLY"
                else:
                    starts, ends, weights = [earliest], [latest], [1.0]
                    method = "RANGE_FALLBACK"
            elif bins:
                raise DateGenerationError(f"{table}.{column}: month counts exist for an all-null/empty SOURCE date.")
            weights = np.asarray(weights, dtype=float)
            if len(weights):
                weights /= weights.sum()
            self.models[key] = DateDistribution(table, column, np.asarray(starts, dtype="int64"),
                                                 np.asarray(ends, dtype="int64"), weights, null_rate, method)

    def _check_run(self, row):
        if row.get("run_id") != self.source_run_id or row.get("profile_type") not in (None, "SOURCE"):
            raise DateGenerationError("Date evidence must belong to the pinned SOURCE run.")

    def _rng(self, key):
        digest = hashlib.sha256((key[0] + "." + key[1]).encode("utf-8")).digest()
        words = [int.from_bytes(digest[i:i + 4], "little") for i in range(0, 16, 4)]
        return np.random.default_rng(np.random.SeedSequence([self.seed, *words]))

    def _generate(self, models, n, force_non_null=(), null_masks=None):
        if int(n) != n or n < 0:
            raise DateGenerationError("Date population size must be a nonnegative integer.")
        n = int(n)
        null_masks = null_masks or {}
        keys = sorted(models)
        rngs, active, lo, hi = {}, {}, {}, {}
        for key in keys:
            model = models[key]
            rngs[key] = self._rng(key)
            keep = np.ones(n, dtype=bool)
            if key in null_masks:
                mask = np.asarray(null_masks[key])
                if mask.shape != (n,) or mask.dtype != bool:
                    raise DateGenerationError("Profiled date null masks must be Boolean arrays matching the generated population.")
                keep = ~mask.copy()
                if key in force_non_null and mask.any():
                    raise DateGenerationError("Required snapshot keys cannot use a nullable override.")
            elif key not in force_non_null:
                count = int(np.rint(n * (model.null_rate if model.null_rate is not None else 1.0)))
                keep[rngs[key].permutation(n)[:count]] = False
            active[key] = keep
            lo[key] = np.full(n, model.starts[0] if len(model.starts) else 0, dtype="int64")
            hi[key] = np.full(n, model.ends[-1] if len(model.ends) else 0, dtype="int64")
        edges = [((table, parent.upper()), (table, child.upper()))
                 for table, rules in TEMPORAL_ORDER.items() for parent, child in rules
                 if (table, parent.upper()) in models and (table, child.upper()) in models]
        # Arc consistency accounts for actual month gaps before drawing parent dates.
        for _ in range(2 * len(keys) + 4):
            changed = False
            for key in keys:
                before_lo, before_hi = lo[key].copy(), hi[key].copy()
                models[key].bounds(lo[key], hi[key], active[key])
                changed |= not (np.array_equal(before_lo, lo[key]) and np.array_equal(before_hi, hi[key]))
            for parent, child in edges:
                together = active[parent] & active[child]
                new_lo = np.maximum(lo[child][together], lo[parent][together])
                new_hi = np.minimum(hi[parent][together], hi[child][together])
                changed |= not (np.array_equal(new_lo, lo[child][together]) and np.array_equal(new_hi, hi[parent][together]))
                lo[child][together], hi[parent][together] = new_lo, new_hi
            if not changed:
                break
        else:
            raise DateGenerationError("Temporal bounds did not converge.")
        parents, children = defaultdict(list), defaultdict(list)
        degree = dict.fromkeys(keys, 0)
        for first, second in edges:
            parents[second].append(first)
            children[first].append(second)
            degree[second] += 1
        queue = [key for key in keys if degree[key] == 0]
        heapq.heapify(queue)
        generated = {}
        while queue:
            key = heapq.heappop(queue)
            for parent in parents[key]:
                together = active[parent] & active[key]
                lo[key][together] = np.maximum(lo[key][together], generated[parent][together].astype("int64"))
            generated[key] = models[key].draw(rngs[key], active[key], lo[key], hi[key])
            for child in children[key]:
                degree[child] -= 1
                if degree[child] == 0:
                    heapq.heappush(queue, child)
        if len(generated) != len(keys):
            raise DateGenerationError("Temporal ordering rules contain a cycle.")
        for key, values in generated.items():
            model = models[key]
            null_count = int(np.isnat(values).sum())
            expected_nulls = int((~active[key]).sum())
            if null_count != expected_nulls:
                raise DateGenerationError(f"{key[0]}.{model.column}: generated dates changed the SOURCE null mask.")
            self.expected_null_counts.setdefault(key[0], {})[model.column] = expected_nulls
            constrained = active[key] & ((lo[key] > (model.starts[0] if len(model.starts) else 0))
                                        | (hi[key] < (model.ends[-1] if len(model.ends) else 0)))
            self.diagnostics.append({"source_run_id": self.source_run_id, "seed": self.seed, "table": key[0],
                                     "column": model.column, "method": model.method, "row_count": n,
                                     "source_null_rate": model.null_rate, "null_count": null_count, "expected_null_count": expected_nulls,
                                     "constrained_row_count": int(constrained.sum()), "required_non_null_key": key in force_non_null,
                                     "profiled_null_mask_override": key in null_masks})
        return generated

    def generate_table(self, table, n, *, null_masks=None):
        models = {key: model for key, model in self.models.items() if key[0] == table}
        overrides = {(table, column.upper()): mask for column, mask in (null_masks or {}).items()}
        if not overrides.keys() <= models.keys():
            raise DateGenerationError("Profiled relationship date null masks require matching SOURCE date profiles.")
        generated = self._generate(models, n, null_masks=overrides)
        return {models[key].column: value for key, value in generated.items()}

    def generate_accounts(self, account_ids, balance_ids):
        """Generate one shared snapshot by synthetic ID, including shuffled balance rows."""
        if len(set(account_ids)) != len(account_ids) or len(set(balance_ids)) != len(balance_ids) or set(account_ids) != set(balance_ids):
            raise DateGenerationError("Account/balance synthetic IDs must be unique and cover the same accounts.")
        account_key, balance_key = ("TKQ_ACCOUNT", SNAPSHOT), ("TKQ_ACCOUNT_BALANCE", SNAPSHOT)
        models = {key: model for key, model in self.models.items() if key[0] in ("TKQ_ACCOUNT", "TKQ_ACCOUNT_BALANCE")}
        candidates = [models[key] for key in (balance_key, account_key) if key in models and len(models[key].starts)]
        if not candidates:
            raise DateGenerationError("The pinned SOURCE needs usable account/balance effective date support.")
        primary = next((model for model in candidates if model.method == "MONTHLY"), candidates[0])
        starts, ends, weights = list(primary.starts), list(primary.ends), list(primary.weights)
        for other in candidates:
            if other is primary:
                continue
            new_starts, new_ends, new_weights = [], [], []
            for left, right, weight in zip(starts, ends, weights):
                for a, b in zip(other.starts, other.ends):
                    a, b = max(left, a), min(right, b)
                    if a <= b:
                        new_starts.append(a)
                        new_ends.append(b)
                        new_weights.append(weight * (b - a + 1) / (right - left + 1))
            starts, ends, weights = new_starts, new_ends, new_weights
        if not starts:
            raise DateGenerationError("SOURCE account/balance effective date supports do not overlap.")
        weights = np.asarray(weights, dtype=float)
        weights /= weights.sum()
        account_model, balance_model = self.models.get(account_key), self.models.get(balance_key)
        models[account_key] = replace(primary, table="TKQ_ACCOUNT", column=account_model.column if account_model else SNAPSHOT,
                                      starts=np.asarray(starts), ends=np.asarray(ends), weights=weights,
                                      method="SHARED_" + primary.method,
                                      null_rate=account_model.null_rate if account_model else None)
        models.pop(balance_key, None)
        generated = self._generate(models, len(account_ids), force_non_null=(account_key,))
        accounts = {models[key].column: values for key, values in generated.items() if key[0] == "TKQ_ACCOUNT"}
        index = {value: position for position, value in enumerate(account_ids)}
        order = [index[value] for value in balance_ids]
        balances = {models[key].column: values[order] for key, values in generated.items() if key[0] == "TKQ_ACCOUNT_BALANCE"}
        balance_column = balance_model.column if balance_model else SNAPSHOT
        balances[balance_column] = generated[account_key][order]
        self.expected_null_counts.setdefault("TKQ_ACCOUNT_BALANCE", {})[balance_column] = 0
        account_diagnostic = next(row for row in reversed(self.diagnostics)
                                  if row["table"] == "TKQ_ACCOUNT" and row["column"] == models[account_key].column)
        self.diagnostics.append({**account_diagnostic, "table": "TKQ_ACCOUNT_BALANCE", "column": balance_column,
                                 "method": "SHARED_BY_ACCOUNT_ID", "source_null_rate": balance_model.null_rate if balance_model else None,
                                 "null_count": 0, "required_non_null_key": True})
        return accounts, balances


def load_date_sampler(spark, source_run_id, seed):
    runs = _rows(spark, f"""
        SELECT run_id FROM {PROFILE_SCHEMA}.profile_runs
        WHERE run_id = :source AND profile_type = 'SOURCE' AND status = 'COMPLETED' AND completed_at IS NOT NULL
    """, {"source": source_run_id})
    if len(runs) != 1:
        raise DateGenerationError("Date generation requires the pinned completed SOURCE profiling run.")
    profiles = {}
    for name in ("date_profile", "date_distribution_profile", "column_quality"):
        table = f"{PROFILE_SCHEMA}.{name}"
        profiles[name] = _rows(spark, f"SELECT * FROM {table} WHERE run_id = :source", {"source": source_run_id}) if spark.catalog.tableExists(table) else []
    return DateSampler(source_run_id, seed, profiles["date_profile"], profiles["date_distribution_profile"], profiles["column_quality"])
