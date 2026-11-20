"""Marginal samplers extracted from Notebook 03; preserve formulas and RNG consumption."""

import numpy as np
import pandas as pd


class ProfileGenerators:
    def __init__(self, profiles, rng):
        self.category_stats = profiles.category_stats
        self.numeric_stats = profiles.numeric_stats
        self.column_quality = profiles.column_quality
        self.structural_stats = profiles.structural_stats
        self.rng = rng
        self.delinquency_rates = {}

    def generate_categorical(self, table_name, column_name, n):
        profile = self.category_stats[(self.category_stats['logical_table_name'] == table_name) & (self.category_stats['column_name'] == column_name)].copy()
        profile = profile[profile['category_value'].notna()]
        if profile.empty:
            return np.array([None] * n, dtype=object)
        values = profile['category_value'].to_numpy()
        probabilities = profile['proportion'].astype(float).to_numpy()
        probabilities = probabilities / probabilities.sum()
        return self.rng.choice(values, size=n, p=probabilities)

    def generate_numeric(self, table_name, column_name, n):
        profile = self.numeric_stats[(self.numeric_stats['logical_table_name'] == table_name) & (self.numeric_stats['column_name'] == column_name)]
        if profile.empty:
            return np.full(n, np.nan)
        row = profile.iloc[0]
        percentile_points = np.array([0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0])
        values = np.array([row['min_value'], row['p01'], row['p05'], row['p25'], row['p50'], row['p75'], row['p95'], row['p99'], row['max_value']], dtype=float)
        valid = ~np.isnan(values)
        percentile_points = percentile_points[valid]
        values = values[valid]
        if len(values) == 0:
            return np.full(n, np.nan)
        if len(values) == 1:
            return np.full(n, values[0])
        random_percentiles = self.rng.random(n)
        return np.interp(random_percentiles, percentile_points, values)

    def get_null_probability(self, table_name, column_name):
        profile = self.column_quality[(self.column_quality['logical_table_name'] == table_name) & (self.column_quality['column_name'] == column_name)]
        if profile.empty:
            return 0.0
        null_pct = profile.iloc[0]['null_pct']
        if pd.isna(null_pct):
            return 0.0
        return float(null_pct) / 100

    def apply_profiled_nulls(self, dataframe, table_name, protected_columns=None):
        if protected_columns is None:
            protected_columns = []
        for column_name in dataframe.columns:
            if column_name in protected_columns:
                continue
            null_probability = self.get_null_probability(table_name, column_name)
            if null_probability <= 0:
                continue
            mask = self.rng.random(len(dataframe)) < null_probability
            dataframe.loc[mask, column_name] = None
        return dataframe

    def generate_cardinality(self, relationship_name, n, fallback=1):
        profile = self.structural_stats[self.structural_stats['relationship_name'] == relationship_name].copy()
        if profile.empty:
            return np.full(n, fallback, dtype=int)
        values = profile['cardinality'].astype(int).to_numpy()
        probabilities = profile['proportion'].astype(float).to_numpy()
        probabilities = probabilities / probabilities.sum()
        return self.rng.choice(values, size=n, p=probabilities)

    def get_delinquency_probability(self, utilization):
        if utilization < 0.3:
            bucket = '0-30%'
        elif utilization < 0.6:
            bucket = '30-60%'
        elif utilization < 0.8:
            bucket = '60-80%'
        elif utilization <= 1.0:
            bucket = '80-100%'
        else:
            bucket = '100%+'
        if bucket in self.delinquency_rates:
            return self.delinquency_rates[bucket]
        return 0.05

    def fill_profiled_fields(self, dataframe, table_name, protected_columns=None):
        if protected_columns is None:
            protected_columns = []
        n = len(dataframe)
        cat_columns = self.category_stats[self.category_stats['logical_table_name'] == table_name]['column_name'].unique()
        for column_name in cat_columns:
            if column_name in protected_columns or column_name in dataframe.columns:
                continue
            dataframe[column_name] = self.generate_categorical(table_name, column_name, n)
        num_columns = self.numeric_stats[self.numeric_stats['logical_table_name'] == table_name]['column_name'].unique()
        for column_name in num_columns:
            if column_name in protected_columns or column_name in dataframe.columns:
                continue
            dataframe[column_name] = self.generate_numeric(table_name, column_name, n)
        dataframe = self.apply_profiled_nulls(dataframe, table_name, protected_columns)
        return dataframe
