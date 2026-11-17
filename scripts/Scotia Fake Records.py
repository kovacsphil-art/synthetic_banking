# Databricks notebook source
# MAGIC %pip install openpyxl

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

from pathlib import Path
from typing import Dict
import math

import numpy as np
import pandas as pd


SNAPSHOT_DATE = pd.Timestamp("2026-09-30")


# -----------------------------
# Generic helpers
# -----------------------------

def random_date(rng, start, end):
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if pd.isna(start) or pd.isna(end) or end < start:
        return pd.NaT
    days = (end - start).days
    return start + pd.Timedelta(days=int(rng.integers(0, max(days, 0) + 1)))


def weighted_choice(rng, values, probs, size=None):
    return rng.choice(values, size=size, p=np.array(probs) / np.sum(probs))


def clamp(x, low, high):
    return max(low, min(high, x))


def load_schema(schema_path: str) -> dict:
    """Read the uploaded workbook and return exact column names/types by sheet."""
    xls = pd.ExcelFile(schema_path)
    schema = {}
    for sheet in xls.sheet_names:
        d = pd.read_excel(schema_path, sheet_name=sheet)
        schema[sheet] = {
            row["Source Column"]: str(row["Data type"]).upper()
            for _, row in d.iterrows()
        }
    return schema


def _fallback_column(name, dtype, n, rng):
    """
    Safe fallback for fields not explicitly modelled.
    It intentionally favours 0/NULL over inventing strong business semantics.
    """
    u = name.upper()

    if dtype == "DATE":
        return pd.Series([pd.NaT] * n, dtype="datetime64[ns]")

    if dtype in {"NUMERIC", "FLOAT", "DOUBLE", "DECIMAL", "INTEGER", "INT", "BIGINT"}:
        if "CNT" in u or "COUNT" in u:
            return rng.poisson(0.2, n)
        if "APR" in u:
            return np.round(rng.normal(20.0, 2.5, n).clip(8, 30), 3)
        if "SCORE" in u:
            return np.round(rng.normal(710, 55, n).clip(300, 900))
        if "PERCENT" in u:
            return np.round(rng.uniform(1, 100, n), 2)
        if "AMT" in u or "BAL" in u or "LIMIT" in u:
            active = rng.random(n) < 0.25
            vals = np.zeros(n)
            vals[active] = np.round(rng.gamma(2.0, 250.0, active.sum()), 2)
            return vals
        return np.zeros(n)

    # Strings
    if any(x in u for x in ["FLAG", "INDICATOR", "_IND"]):
        return weighted_choice(rng, ["N", "Y"], [0.9, 0.1], size=n)
    if u.endswith("_CD") or "CODE" in u:
        return weighted_choice(rng, ["A", "B", "C"], [0.7, 0.2, 0.1], size=n)
    if "NUM" in u or "NBR" in u:
        return [f"{int(x):04d}" for x in rng.integers(1, 9999, n)]
    return pd.Series([None] * n, dtype="object")


def finalize_to_schema(df: pd.DataFrame, sheet: str, schema: dict, rng) -> pd.DataFrame:
    """Guarantee exact workbook columns, exact order, and no extras."""
    required = schema[sheet]
    out = df.copy()

    for col, dtype in required.items():
        if col not in out.columns:
            out[col] = _fallback_column(col, dtype, len(out), rng)

    return out[list(required.keys())]


# -----------------------------
# PERSON
# -----------------------------

def generate_people(n_people: int, schema: dict, rng) -> pd.DataFrame:
    rows = []

    occupations = {
        "PRO": ["Engineer", "Analyst", "Teacher", "Nurse", "Accountant"],
        "MGT": ["Manager", "Director", "Supervisor"],
        "TRD": ["Electrician", "Plumber", "Technician", "Mechanic"],
        "SRV": ["Retail Associate", "Server", "Customer Service"],
        "RET": ["Retired"],
        "STU": ["Student"],
    }

    for i in range(n_people):
        party_id = f"P{i+1:010d}"

        age = int(np.clip(rng.normal(46, 16), 18, 90))
        birth_dt = SNAPSHOT_DATE - pd.DateOffset(years=age) - pd.Timedelta(days=int(rng.integers(0, 365)))

        # Most customers joined after adulthood and before the snapshot.
        earliest_since = max(pd.Timestamp(birth_dt) + pd.DateOffset(years=16), pd.Timestamp("1985-01-01"))
        since_dt = random_date(rng, earliest_since, SNAPSHOT_DATE)

        deceased = rng.random() < 0.004
        deceased_dt = random_date(rng, max(pd.Timestamp(birth_dt) + pd.DateOffset(years=18), since_dt), SNAPSHOT_DATE) if deceased else pd.NaT

        left = (not deceased) and (rng.random() < 0.07)
        left_dt = random_date(rng, since_dt, SNAPSHOT_DATE) if left else pd.NaT

        bankruptcy = rng.random() < 0.018
        bankruptcy_dt = random_date(
            rng,
            max(pd.Timestamp(birth_dt) + pd.DateOffset(years=18), pd.Timestamp("2000-01-01")),
            SNAPSHOT_DATE
        ) if bankruptcy else pd.NaT

        if age >= 67:
            emp = weighted_choice(rng, ["RET", "FT", "PT"], [0.78, 0.15, 0.07])
        elif age <= 24:
            emp = weighted_choice(rng, ["STU", "FT", "PT"], [0.45, 0.35, 0.20])
        else:
            emp = weighted_choice(rng, ["FT", "PT", "SELF", "UNEMP"], [0.72, 0.12, 0.11, 0.05])

        if emp == "RET":
            occup_cat = "RET"
        elif emp == "STU":
            occup_cat = "STU"
        else:
            occup_cat = weighted_choice(rng, ["PRO", "MGT", "TRD", "SRV"], [0.38, 0.18, 0.22, 0.22])

        occup_desc = str(weighted_choice(rng, occupations[occup_cat], [1] * len(occupations[occup_cat])))

        client_stat = "D" if deceased else ("C" if left else "A")

        # KYC refresh normally occurs after customer start and within recent years.
        kyc_start = max(pd.Timestamp(since_dt), SNAPSHOT_DATE - pd.DateOffset(years=5))
        kyc_refresh = random_date(rng, kyc_start, SNAPSHOT_DATE)

        rows.append({
            "BANKRUPTCY_DT": bankruptcy_dt,
            "BIRTH_DT": birth_dt,
            "CLIENT_STAT_CD": client_stat,
            "CUST_TYPE_CD": "IND",
            "DECEASED_DT": deceased_dt,
            "DOMICILE_TRANSIT_NUM": f"{int(rng.integers(1, 99999)):05d}",
            "EMP_TYPE_CD": emp,
            "GENDER_CD": weighted_choice(rng, ["F", "M", "X"], [0.495, 0.495, 0.01]),
            "KYC_REFRESH_DT": kyc_refresh,
            "LEFT_DT": left_dt,
            "MARITAL_STAT_CD": weighted_choice(rng, ["S", "M", "C", "D", "W"], [0.34, 0.45, 0.05, 0.12, 0.04]),
            "OCCUP_CAT_CD": occup_cat,
            "OCCUP_DESC": occup_desc,
            "PARTY_ID": party_id,
            "PARTY_SUBSYS_MNEMONIC_CD": "CIS",
            "PREF_LANG_CD": weighted_choice(rng, ["EN", "FR"], [0.88, 0.12]),
            "SENSITIVITY_CD": weighted_choice(rng, ["N", "R"], [0.985, 0.015]),
            "SINCE_DT": since_dt,
            "SRC_IDENTITY_CD": "CIS",
        })

    return finalize_to_schema(pd.DataFrame(rows), "PERSON", schema, rng)


# -----------------------------
# Customer-to-customer relationships
# -----------------------------

def generate_customer_relationships(people: pd.DataFrame, schema: dict, rng) -> pd.DataFrame:
    active = people.loc[people["CLIENT_STAT_CD"] == "A", "PARTY_ID"].tolist()
    rng.shuffle(active)

    rows = []

    # Create spouse/partner pairs for a modest subset of customers.
    n_pairs = min(len(active) // 2, int(len(active) * 0.12))
    for i in range(n_pairs):
        a = active[2 * i]
        b = active[2 * i + 1]
        rows.append({
            "FROM_PARTY_ID": a,
            "TO_PARTY_ID": b,
            "LAST_UPDT_CHANNEL_CD": weighted_choice(rng, ["BR", "DIG", "CC"], [0.35, 0.50, 0.15]),
            "LAST_UPDT_TRANSIT_NUM": f"{int(rng.integers(1, 99999)):05d}",
            "ORIGINATING_APP_CD": "CIS",
            "OWNED_BUS_SINCE_DT": pd.NaT,
            "ownership_percentage": np.nan,
            "TO_FROM_CUST_RELATN_CD": "SPOUSE",
            "FROM_TO_CUST_RELATN_CD": "SPOUSE",
        })

    return finalize_to_schema(pd.DataFrame(rows), "CUSTOMER_RELATIONSHIP", schema, rng)


# -----------------------------
# Internal credit-card accounts
# -----------------------------

def _customer_risk_inputs(person_row, rng):
    age = int((SNAPSHOT_DATE - pd.Timestamp(person_row["BIRTH_DT"])).days / 365.25)
    emp = person_row["EMP_TYPE_CD"]

    score = rng.normal(715, 55)
    if emp == "UNEMP":
        score -= 45
    if pd.notna(person_row["BANKRUPTCY_DT"]):
        score -= 100
    if age < 25:
        score -= 20
    score = int(np.clip(score, 420, 880))
    return age, score


def generate_accounts(people: pd.DataFrame, schema: dict, rng):
    acct_rows = []
    rel_rows = []
    balance_rows = []

    active_people = people[people["CLIENT_STAT_CD"] == "A"].reset_index(drop=True)

    account_counter = 1

    for _, person in active_people.iterrows():
        age, score = _customer_risk_inputs(person, rng)

        # 0-4 revolving accounts, weighted toward 1-2.
        n_accts = int(weighted_choice(rng, [0, 1, 2, 3, 4], [0.04, 0.50, 0.31, 0.11, 0.04]))

        for _ in range(n_accts):
            account_id = f"A{account_counter:012d}"
            account_counter += 1

            product = weighted_choice(rng, ["VISA", "MC"], [0.58, 0.42])
            tier = weighted_choice(rng, ["CLASSIC", "GOLD", "PLAT"], [0.55, 0.30, 0.15])

            # Open date cannot predate customer relationship or plausible adult age.
            open_start = max(pd.Timestamp(person["SINCE_DT"]), pd.Timestamp(person["BIRTH_DT"]) + pd.DateOffset(years=18))
            open_end = SNAPSHOT_DATE - pd.Timedelta(days=30)
            if open_start > open_end:
                continue
            open_dt = random_date(rng, open_start, open_end)

            months_open = max(1, int((SNAPSHOT_DATE - open_dt).days / 30.4))

            # Credit limit depends on score, age, and product tier.
            limit_base = 1500 + max(score - 550, 0) * 55 + max(age - 21, 0) * 70
            tier_mult = {"CLASSIC": 0.65, "GOLD": 1.0, "PLAT": 1.45}[tier]
            credit_limit = round(clamp(rng.normal(limit_base * tier_mult, 2500), 500, 50000) / 100) * 100
            original_limit = max(500, round(credit_limit * rng.uniform(0.45, 1.0) / 100) * 100)

            # Utilization is correlated with risk/score.
            risk_shift = max(0, (700 - score) / 300)
            utilization = float(np.clip(rng.beta(1.5 + 2.5 * risk_shift, 3.5), 0, 1.35))
            balance = round(credit_limit * utilization, 2)

            # Delinquency probability increases with utilization and lower score.
            logit = -4.0 + 3.2 * utilization + max(0, (680 - score) / 55)
            p_dq = 1 / (1 + math.exp(-logit))
            delinquent = rng.random() < p_dq

            if delinquent:
                severity = weighted_choice(rng, [30, 60, 90, 120, 180], [0.55, 0.22, 0.12, 0.07, 0.04])
                delinquency_cnt = int(rng.integers(1, 5))
                first_dlq = random_date(rng, open_dt, SNAPSHOT_DATE - pd.Timedelta(days=int(severity)))
                last_past_due = random_date(rng, first_dlq, SNAPSHOT_DATE)
                past_due_total = round(min(balance, max(25, balance * rng.uniform(0.05, 0.40))), 2)
            else:
                severity = 0
                delinquency_cnt = 0
                first_dlq = pd.NaT
                last_past_due = pd.NaT
                past_due_total = 0.0

            charge_off = severity >= 180 and score < 600 and rng.random() < 0.40
            charge_off_dt = random_date(rng, last_past_due, SNAPSHOT_DATE) if charge_off else pd.NaT

            closed = (not charge_off) and (months_open > 12) and (rng.random() < 0.07)
            close_dt = random_date(rng, open_dt + pd.Timedelta(days=90), SNAPSHOT_DATE) if closed else pd.NaT
            effective_dt = SNAPSHOT_DATE

            # Closed revolving accounts carry no current balance/past-due amount.
            # Historical delinquency fields can still remain populated.
            current_delinquent = delinquent and not closed
            if closed:
                balance = 0.0
                utilization = 0.0
                past_due_total = 0.0

            activity_end = close_dt if closed else SNAPSHOT_DATE
            last_payment_dt = random_date(rng, max(open_dt, pd.Timestamp(activity_end) - pd.Timedelta(days=120)), activity_end)
            last_purchase_dt = random_date(rng, max(open_dt, pd.Timestamp(activity_end) - pd.Timedelta(days=180)), activity_end)
            first_use_dt = random_date(rng, open_dt, min(open_dt + pd.Timedelta(days=45), pd.Timestamp(activity_end)))

            purchase_apr = round(float(np.clip(rng.normal(20.99, 2.1), 12.0, 29.99)), 3)
            cash_apr = round(min(32.99, purchase_apr + rng.uniform(1.0, 4.0)), 3)
            min_payment = round(max(10.0, balance * rng.uniform(0.02, 0.035)), 2) if balance > 0 else 0.0

            last_statement_balance = round(max(0, balance + rng.normal(0, max(50, balance * 0.12))), 2)

            acct_rows.append({
                "ACCOUNT_ID": account_id,
                "ACCOUNT_TYPE_CD": product,
                "BUSINESSEFFECTIVEDATE": effective_dt,
                "CLIENT_PRODUCT_CD": f"{product}_{tier}",
                "TSYS_PRODUCT_CD": f"{product[0]}{ {'CLASSIC':'01','GOLD':'02','PLAT':'03'}[tier] }",
                "OPEN_DT": open_dt,
                "CLOSE_DT": close_dt,
                "CLOSE_STATUS_DT": close_dt,
                "CARD_EXPIRY_DT": SNAPSHOT_DATE + pd.DateOffset(years=int(rng.integers(1, 5))),
                "CREDIT_LIMIT_AMT": float(credit_limit),
                "ORIGINAL_CREDIT_LIMIT_AMT": float(original_limit),
                "CURRENT_CREDIT_SCORE": score,
                "CURRENT_CREDIT_SCORE_DT": effective_dt,
                "PURCHASE_APR": purchase_apr,
                "CASH_APR": cash_apr,
                "DELINQUENCY_CNT": delinquency_cnt,
                "FIRST_DLQ_DATE": first_dlq,
                "LAST_PAST_DUE_DT": last_past_due,
                "PAST_DUE_INDICATO_CD": "Y" if current_delinquent else "N",
                "CONSECUTIVE_PAST_DUE_BILL_DAYS_CNT": int(severity),
                "CONSECUTIVE_PAST_DUE_BILL_TIMES_CNT": int(1 if delinquent else 0),
                "AVERAGE_DELINQUENCY_MONTHLY_AMT": round(past_due_total / max(delinquency_cnt, 1), 2) if delinquent else 0.0,
                "CHARGE_OFF_DT": charge_off_dt,
                "CREDIT_REVOKE_DT": charge_off_dt,
                "CREDIT_REVOKE_STATUS_DT": charge_off_dt,
                "FIRST_USE_DT": first_use_dt,
                "LAST_PAYMENT_DT": last_payment_dt,
                "LAST_PURCHASE_DT": last_purchase_dt,
                "LAST_FINANCIAL_ACTIVITY_DT": max(last_payment_dt, last_purchase_dt),
                "LAST_PAID_AMT": round(max(0, rng.normal(max(35, balance * 0.08), max(15, balance * 0.04))), 2) if balance > 0 else 0.0,
                "LAST_STATEMENT_BALANCE_AMT": last_statement_balance,
                "PREVIOUS_STATEMENT_BALANCE_AMT": round(max(0, last_statement_balance + rng.normal(0, 150)), 2),
                "MINIMUM_PAYMENT_DUE_AMT": min_payment,
                "HIGH_BALANCE_AMT": round(max(balance, credit_limit * rng.uniform(0.25, 1.05)), 2),
                "HIGH_BALANCE_DT": random_date(rng, open_dt, SNAPSHOT_DATE),
                "CURRENT_OUT_CASH_AMT": round(balance * rng.uniform(0, 0.10), 2),
                "LAST_CASH_ADVANCE_AMT": round(balance * rng.uniform(0, 0.05), 2) if rng.random() < 0.15 else 0.0,
                "LAST_CASH_ADVANCE_DT": random_date(rng, open_dt, SNAPSHOT_DATE) if rng.random() < 0.15 else pd.NaT,
                "AUTO_LIMIT_INCREASE_IND": weighted_choice(rng, ["Y", "N"], [0.25, 0.75]),
                "AUTO_PAYMENT_METHOD_CD": weighted_choice(rng, ["NONE", "MIN", "FULL"], [0.60, 0.25, 0.15]),
                "STATEMENT_CNT": months_open,
                "SUFFIX_NUM": "00",
                "ST_PROV_RES_PRIM_CD": weighted_choice(rng, ["ON", "BC", "AB", "QC", "MB", "SK", "NS"], [0.40, 0.16, 0.15, 0.17, 0.04, 0.03, 0.05]),
                "TRANSFER_FROM_ACCOUNT_INDICATOR_FLAG": "N",
            })

            rel_rows.append({
                "ACCT_ID": account_id,
                "ACCT_SUBSYS_MNEMONIC_CD": "TSYS",
                "PARTY_ID": person["PARTY_ID"],
                "PRIMARY_OWNERSHIP_FLAG": "Y",
                "PROD_CD": product,
                "RELATN_TYPE_CD": "PRIMARY",
            })

            # Build age bucket amounts so past-due total never exceeds balance.
            past_due = {30: 0.0, 60: 0.0, 90: 0.0, 120: 0.0, 150: 0.0, 180: 0.0, 210: 0.0, 240: 0.0, 270: 0.0, 271: 0.0}
            if current_delinquent:
                bucket = 30 if severity <= 30 else 60 if severity <= 60 else 90 if severity <= 90 else 120 if severity <= 120 else 180
                past_due[bucket] = past_due_total

            available = round(max(0.0, credit_limit - balance), 2)
            overlimit = round(max(0.0, balance - credit_limit), 2)
            cash_limit = round(credit_limit * rng.uniform(0.20, 0.40), 2)

            payments_ytd = round(max(0, rng.normal(max(balance * 1.3, 500), max(250, balance * 0.6))), 2)
            purchases_ytd = round(max(0, rng.normal(max(balance * 1.5, 800), max(300, balance * 0.7))), 2)

            balance_rows.append({
                "ACCOUNT_ID": account_id,
                "BUSINESSEFFECTIVEDATE": effective_dt,
                "CURRENT_BALANCE_AMT": balance,
                "AVAILABLE_TO_BUY_AMT": available,
                "OVERLIMIT_AMT": overlimit,
                "AVERAGE_DAILY_BAL_AMT": round(max(0, balance * rng.uniform(0.75, 1.10)), 2),
                "CASH_LIMIT_AMT": cash_limit,
                "CASH_AVAILABLE_AMT": round(max(0, cash_limit - min(balance * 0.1, cash_limit)), 2),
                "AMT_PDUE_1_30": past_due[30],
                "AMT_PDUE_31_60": past_due[60],
                "AMT_PDUE_61_90": past_due[90],
                "AMT_PDUE_91_120": past_due[120],
                "AMT_PDUE_121_150": past_due[150],
                "AMT_PDUE_151_180": past_due[180],
                "AMT_PDUE_181_210": past_due[210],
                "AMT_PDUE_211_240": past_due[240],
                "AMT_PDUE_241_270": past_due[270],
                "AMT_PDUE_271_UP": past_due[271],
                "NUM_PDUE_1_30": 1 if past_due[30] else 0,
                "NUM_PDUE_31_60": 1 if past_due[60] else 0,
                "NUM_PDUE_61_90": 1 if past_due[90] else 0,
                "NUM_PDUE_91_120": 1 if past_due[120] else 0,
                "NUM_PDUE_121_150": 1 if past_due[150] else 0,
                "NUM_PDUE_151_180": 1 if past_due[180] else 0,
                "NUM_PDUE_181_210": 1 if past_due[210] else 0,
                "NUM_PDUE_211_240": 1 if past_due[240] else 0,
                "NUM_PDUE_241_270": 1 if past_due[270] else 0,
                "NUM_PDUE_271_UP": 1 if past_due[271] else 0,
                "CHARGED_OFF_AMT": balance if charge_off else 0.0,
                "PRINCIPAL_BAL_CHARGEOFF_AMT": balance if charge_off else 0.0,
                "PAYMENT_CTD_AMT": round(payments_ytd / 12 * rng.uniform(0.5, 1.5), 2),
                "PAYMENT_YTD_AMT": payments_ytd,
                "PAYMENTS_CTD_CNT": int(rng.integers(0, 4)),
                "PAYMENTS_YTD_CNT": int(rng.integers(1, 25)),
                "PURCHASE_CTD_CNT": int(rng.integers(0, 20)),
                "PURCHASE_YTD_AMT": purchases_ytd,
                "PURCHASE_YTD_CNT": int(rng.integers(1, 100)),
                "PURCHASED_AMT": round(max(0, purchases_ytd / 12 * rng.uniform(0.5, 1.5)), 2),
                "LIFETIME_PURCHASE_CNT": int(max(months_open, 1) * rng.uniform(1, 8)),
                "OUTSTANDING_AUTH_CNT": int(rng.integers(0, 6)),
                "OUTSTANDING_AUTHORIZATION_AMT": round(rng.uniform(0, min(500, available + 1)), 2),
            })

    account_df = finalize_to_schema(pd.DataFrame(acct_rows), "TKQ_ACCOUNT", schema, rng)
    rel_df = finalize_to_schema(pd.DataFrame(rel_rows), "CUSTOMER_ACCOUNT_REL", schema, rng)
    bal_df = finalize_to_schema(pd.DataFrame(balance_rows), "TKQ_ACCOUNT_BALANCE", schema, rng)

    return account_df, rel_df, bal_df


# -----------------------------
# TransUnion-style tradelines
# -----------------------------

def generate_tradelines(people: pd.DataFrame, schema: dict, rng) -> pd.DataFrame:
    rows = []
    counter = 1

    active_people = people[people["CLIENT_STAT_CD"] == "A"]

    for _, person in active_people.iterrows():
        _, score = _customer_risk_inputs(person, rng)

        n_trades = int(np.clip(rng.poisson(5) + 1, 1, 12))

        for _ in range(n_trades):
            trade_type = weighted_choice(
                rng,
                ["CC", "LOC", "AUTO", "MTG", "INST"],
                [0.42, 0.15, 0.16, 0.17, 0.10]
            )

            birth_dt = pd.Timestamp(person["BIRTH_DT"])
            earliest_open = max(birth_dt + pd.DateOffset(years=18), pd.Timestamp("1995-01-01"))
            open_end = SNAPSHOT_DATE - pd.Timedelta(days=30)
            if earliest_open > open_end:
                continue
            open_dt = random_date(rng, earliest_open, open_end)
            age_months = max(1, int((SNAPSHOT_DATE - open_dt).days / 30.4))

            if trade_type == "MTG":
                high_credit = round(rng.uniform(120_000, 900_000), -2)
                limit_amt = high_credit
                util = rng.uniform(0.15, 0.95)
            elif trade_type == "AUTO":
                high_credit = round(rng.uniform(8_000, 80_000), -2)
                limit_amt = high_credit
                util = rng.uniform(0.05, 0.95)
            elif trade_type == "INST":
                high_credit = round(rng.uniform(1_000, 35_000), -2)
                limit_amt = high_credit
                util = rng.uniform(0.05, 0.90)
            else:
                high_credit = round(rng.uniform(1_000, 40_000), -2)
                limit_amt = high_credit
                risk_shift = max(0, (700 - score) / 300)
                util = float(np.clip(rng.beta(1.4 + 2 * risk_shift, 3.5), 0, 1.2))

            closed = age_months > 12 and rng.random() < 0.20
            current_balance = 0.0 if closed else round(max(0, limit_amt * util), 2)
            close_dt = random_date(rng, open_dt + pd.Timedelta(days=90), SNAPSHOT_DATE) if closed else pd.NaT

            p_late = clamp(0.03 + max(0, (680 - score) / 700), 0.02, 0.35)
            late30 = int(rng.poisson(0.8 if rng.random() < p_late else 0.05))
            late60 = int(rng.binomial(late30, 0.30)) if late30 else 0
            late90 = int(rng.binomial(late60, 0.35)) if late60 else 0

            amount_past_due = 0.0
            if late30 > 0 and not closed:
                amount_past_due = round(min(current_balance, max(25, current_balance * rng.uniform(0.02, 0.15))), 2)

            if late90 > 0:
                mop = "5"
            elif late60 > 0:
                mop = "3"
            elif late30 > 0:
                mop = "2"
            else:
                mop = "1"

            if trade_type == "MTG":
                payment = current_balance * rng.uniform(0.004, 0.007)
            elif trade_type in {"AUTO", "INST"}:
                payment = current_balance / max(6, rng.integers(12, 60))
            else:
                payment = max(25, current_balance * rng.uniform(0.02, 0.05))

            trade_activity_end = close_dt if closed else SNAPSHOT_DATE
            last_activity = random_date(
                rng,
                max(open_dt, pd.Timestamp(trade_activity_end) - pd.Timedelta(days=180)),
                trade_activity_end
            )

            rows.append({
                "account_closed_date": close_dt,
                "account_closed_indicator": "Y" if closed else "N",
                "account_designator_code": "I",
                "account_number": f"TU{counter:014d}",
                "account_open_date": open_dt,
                "account_paid_out_date": close_dt if closed else pd.NaT,
                "account_type_code": trade_type,
                # Workbook marks this STRING, so store formatted numeric text.
                "amount_past_due": f"{amount_past_due:.2f}",
                "collateral_text": {"MTG": "REAL ESTATE", "AUTO": "VEHICLE"}.get(trade_type),
                "credit_limit_amount": float(limit_amt),
                "currency_code": "CAD",
                "current_balance_amount": current_balance,
                "current_manner_of_payment_code": mop,
                "high_credit_amount": float(high_credit),
                "historical_counters_verification_indicator": "Y",
                "industry_code": {
                    "CC": "BANK",
                    "LOC": "BANK",
                    "AUTO": "AUTO",
                    "MTG": "MTG",
                    "INST": "FIN"
                }[trade_type],
                "ingest_timestamp": SNAPSHOT_DATE + pd.Timedelta(hours=2),
                "last_activity_date": last_activity,
                "months_reviewed_count": min(age_months, 99),
                "narrative_code_1": None,
                "narrative_code_2": None,
                "payment_amount": round(payment, 2),
                "payment_frequency_code": "M",
                "payment_pattern": ("1" * min(age_months, 24)) if mop == "1" else None,
                "payment_pattern_start_date": max(open_dt, SNAPSHOT_DATE - pd.DateOffset(months=24)),
                "segment_type": "T",
                "snapshot_date": SNAPSHOT_DATE,
                "source_extract_timestamp": SNAPSHOT_DATE + pd.Timedelta(hours=1),
                "subscriber_code": f"S{int(rng.integers(1, 250)):04d}",
                "subscriber_name": weighted_choice(
                    rng,
                    ["BANK_A", "BANK_B", "CREDIT_UNION", "AUTO_FINANCE", "MORTGAGE_CO"],
                    [0.30, 0.25, 0.15, 0.15, 0.15]
                ),
                "terms_duration_months": {
                    "MTG": 300,
                    "AUTO": int(rng.choice([48, 60, 72, 84])),
                    "INST": int(rng.choice([12, 24, 36, 48])),
                    "CC": 0,
                    "LOC": 0,
                }[trade_type],
                "times_30_days_late_count": late30,
                "times_60_days_late_count": late60,
                "times_90_days_late_count": late90,
                "trade_last_verified_date": SNAPSHOT_DATE,
                "trade_verification_indicator": "Y",
                # Synthetic convention: link bureau customer key to PARTY_ID.
                "REQ-CIF-KEY": person["PARTY_ID"],
                "REQ-CIF-TIE-BREAKER": "00",
            })
            counter += 1

    return finalize_to_schema(pd.DataFrame(rows), "TRADELINES", schema, rng)


# -----------------------------
# Main generator
# -----------------------------

def generate_fake_banking_data(
    n_people: int,
    schema_path: str,
    seed: int = 42
) -> Dict[str, pd.DataFrame]:
    """
    Generate synthetic-only records.

    n_people is the exact number of PERSON rows.
    Related-table row counts are generated from realistic one-to-many relationships.
    """
    if n_people <= 0:
        raise ValueError("n_people must be > 0")

    rng = np.random.default_rng(seed)
    schema = load_schema(schema_path)

    people = generate_people(n_people, schema, rng)
    customer_relationships = generate_customer_relationships(people, schema, rng)
    accounts, customer_account_rel, balances = generate_accounts(people, schema, rng)
    tradelines = generate_tradelines(people, schema, rng)

    tables = {
        "CUSTOMER_ACCOUNT_REL": customer_account_rel,
        "CUSTOMER_RELATIONSHIP": customer_relationships,
        "PERSON": people,
        "TKQ_ACCOUNT": accounts,
        "TKQ_ACCOUNT_BALANCE": balances,
        "TRADELINES": tradelines,
    }

    return tables


def validate_relationships(tables: Dict[str, pd.DataFrame]) -> None:
    """Basic structural checks before the fake data is used anywhere else."""
    people = tables["PERSON"]
    rel = tables["CUSTOMER_ACCOUNT_REL"]
    acct = tables["TKQ_ACCOUNT"]
    bal = tables["TKQ_ACCOUNT_BALANCE"]
    tu = tables["TRADELINES"]

    assert people["PARTY_ID"].is_unique
    assert acct["ACCOUNT_ID"].is_unique
    assert bal["ACCOUNT_ID"].is_unique

    assert set(rel["PARTY_ID"]).issubset(set(people["PARTY_ID"]))
    assert set(rel["ACCT_ID"]).issubset(set(acct["ACCOUNT_ID"]))
    assert set(bal["ACCOUNT_ID"]) == set(acct["ACCOUNT_ID"])
    assert set(tu["REQ-CIF-KEY"]).issubset(set(people["PARTY_ID"]))

    # Core accounting-style relationships.
    merged = acct[["ACCOUNT_ID", "CREDIT_LIMIT_AMT"]].merge(
        bal[["ACCOUNT_ID", "CURRENT_BALANCE_AMT", "AVAILABLE_TO_BUY_AMT", "OVERLIMIT_AMT"]],
        on="ACCOUNT_ID",
        how="inner",
    )

    expected_available = (merged["CREDIT_LIMIT_AMT"] - merged["CURRENT_BALANCE_AMT"]).clip(lower=0)
    expected_overlimit = (merged["CURRENT_BALANCE_AMT"] - merged["CREDIT_LIMIT_AMT"]).clip(lower=0)

    assert np.allclose(merged["AVAILABLE_TO_BUY_AMT"], expected_available, atol=0.02)
    assert np.allclose(merged["OVERLIMIT_AMT"], expected_overlimit, atol=0.02)


def save_tables_to_volume(
    tables,
    output_dir="/Volumes/workspace/default/scotia",
    prefix="RCAR_synthetic"
):
    saved_paths = {}

    for table_name, df in tables.items():

        output_path = (
            f"{output_dir}/{prefix}_{table_name}.parquet"
        )

        df.to_parquet(
            output_path,
            index=False,
            engine="pyarrow",
            coerce_timestamps="us",
            allow_truncated_timestamps=True
        )

        saved_paths[table_name] = output_path

    return saved_paths


if __name__ == "__main__":
    # Your Databricks Volume locations.
    SCHEMA_XLSX = "/Volumes/workspace/default/scotia/RCAR_source_column_list.xlsx"
    OUTPUT_DIR = "/Volumes/workspace/default/scotia"

    # N is the exact number of synthetic PERSON records.
    # Related tables will contain the appropriate one-to-many row counts.
    N = 1_000

    tables = generate_fake_banking_data(
        n_people=N,
        schema_path=SCHEMA_XLSX,
        seed=42,
    )

    validate_relationships(tables)

    for name, df in tables.items():
        print(f"{name}: {len(df):,} rows x {len(df.columns)} columns")
        display(df.head(5))   # Databricks display()

    # Write the six generated datasets back to the same Databricks Volume.
    saved_paths = save_tables_to_volume(
        tables=tables,
        output_dir=OUTPUT_DIR,
        prefix="RCAR_synthetic",
    )

    print("\nGenerated files:")
    for name, path in saved_paths.items():
        print(f"  {name}: {path}")

    # Example Spark read after saving:
    # person_sdf = spark.read.parquet(saved_paths["PERSON"])
    # display(person_sdf)
