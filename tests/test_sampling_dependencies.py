"""Fabricated aggregate evidence only; no SOURCE records or live credentials."""

from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from synthetic_banking.dependency_sampling import (
    DependencyEvidenceError, conditional_categorical_v1, conditional_numeric_rank_v1,
)
from synthetic_banking.profiling import categorical_statistics
from synthetic_banking.rules import (
    RuleProposal, partition_sampling_proposals, apply_categorical_dependency_rules,
    apply_numeric_dependency_rule,
)

SOURCE = "fabricated-sampling-source"


def categorical_evidence(source=SOURCE):
    summaries, cells = [], []
    pairs = (("ACCOUNT_TYPE_CD", "CLIENT_PRODUCT_CD", (("A", "C", 400), ("A", "D", 100), ("B", "D", 100), ("B", "E", 400))),
             ("CLIENT_PRODUCT_CD", "TSYS_PRODUCT_CD", (("C", "T1", 400), ("D", "T2", 200), ("E", "T3", 400))))
    for parent, child, counts in pairs:
        summary, grid = categorical_statistics([dict(parent_value=p, child_value=c, record_count=n) for p,c,n in counts], 1000)
        identity = dict(run_id=source, profile_type="SOURCE", logical_table_name="TKQ_ACCOUNT", parent_column=parent, child_column=child)
        summaries.append(dict(summary, **identity)); cells.extend(dict(r, **identity) for r in grid)
    return summaries, cells


def numeric_evidence(source=SOURCE):
    common = dict(run_id=source, profile_type="SOURCE", entity_name="ACCOUNT", variable_1="TKQ_ACCOUNT.CREDIT_LIMIT_AMT",
                  variable_2="TKQ_ACCOUNT_BALANCE.CURRENT_BALANCE_AMT", profile_status="PROFILED")
    result = [dict(common, scope="GLOBAL", pair_count=1000, pair_fraction=1., pearson_correlation=.6,
                   x_min=500., x_max=5000., x_p25=2000., x_p50=3000., x_p75=4000., y_min=100., y_max=8000.)]
    cuts = [2000., 3000., 4000.]
    for i, knots in enumerate(([100,200,400,800,1500], [100,1000,2000,3000,4000],
                               [100,2000,3500,5000,6500], [100,3000,5000,6500,8000])):
        result.append(dict(common, scope="X_QUARTILE", segment_value=f"Q{i+1}", pair_count=250,
                           lower_bound=cuts[i-1] if i else None, upper_bound=cuts[i] if i<3 else None,
                           **dict(zip(("y_min","y_p25","y_p50","y_p75","y_max"),knots))))
    return result


def proposals(source=SOURCE):
    p = RuleProposal("client", source, "TKQ_ACCOUNT", "CLIENT_PRODUCT_CD", "CONDITIONAL",
                     ("ACCOUNT_TYPE_CD",), "APPROVED", "fabricated-batch", True)
    return (p, replace(p, proposal_id="tsys", target_column="TSYS_PRODUCT_CD", parent_columns=("CLIENT_PRODUCT_CD",)),
            replace(p, proposal_id="balance", target_table="TKQ_ACCOUNT_BALANCE", target_column="CURRENT_BALANCE_AMT",
                    rule_type="CORRELATED", parent_columns=("TKQ_ACCOUNT.CREDIT_LIMIT_AMT",)))


class DependencySamplerTests(unittest.TestCase):
    def test_categorical_probabilities_zero_cells_and_null_masks(self):
        summary, cells = categorical_evidence()
        parent = np.array(["A"]*5000+["B"]*5000+[None,"A"],object)
        original = np.array(["old"]*10001+[None],object)
        result, n = conditional_categorical_v1(SOURCE,"TKQ_ACCOUNT","ACCOUNT_TYPE_CD","CLIENT_PRODUCT_CD",parent,original,summary,cells,42)
        self.assertEqual(n,10000);self.assertEqual(result[-2],"old");self.assertIsNone(result[-1])
        self.assertTrue(set(result[:5000]) <= {"C","D"});self.assertTrue(set(result[5000:10000]) <= {"D","E"})
        self.assertAlmostEqual(np.mean(result[:5000]=="C"),.8,delta=.02)
        repeated,_=conditional_categorical_v1(SOURCE,"TKQ_ACCOUNT","ACCOUNT_TYPE_CD","CLIENT_PRODUCT_CD",parent,original,list(reversed(summary)),list(reversed(cells)),42)
        np.testing.assert_array_equal(result,repeated)

    def test_categorical_rejects_sparse_incomplete_and_unobserved_parents(self):
        summary,cells=categorical_evidence()
        for mutate in (lambda s,c:c.pop(0), lambda s,c:c.append(c[0]),
                       lambda s,c:s[0].update(profile_type="GENERATED"),
                       lambda s,c:s[0].update(complete_case_fraction=.5),
                       lambda s,c:c[0].update(conditional_proportion=.99)):
            s,c=copy.deepcopy(summary),copy.deepcopy(cells);mutate(s,c)
            with self.assertRaises(DependencyEvidenceError):
                conditional_categorical_v1(SOURCE,"TKQ_ACCOUNT","ACCOUNT_TYPE_CD","CLIENT_PRODUCT_CD",["A"],["old"],s,c,42)
        with self.assertRaisesRegex(DependencyEvidenceError,"unsupported_categorical_parent"):
            conditional_categorical_v1(SOURCE,"TKQ_ACCOUNT","ACCOUNT_TYPE_CD","CLIENT_PRODUCT_CD",["UNSEEN"],["old"],summary,cells,42)
        s, c = categorical_statistics([dict(parent_value="A", child_value="C", record_count=20),
                                      dict(parent_value="B", child_value="D", record_count=980)], 1000)
        identity = dict(run_id=SOURCE, profile_type="SOURCE", logical_table_name="TKQ_ACCOUNT", parent_column="ACCOUNT_TYPE_CD", child_column="CLIENT_PRODUCT_CD")
        with self.assertRaisesRegex(DependencyEvidenceError,"sparse_categorical_parent"):
            conditional_categorical_v1(SOURCE,"TKQ_ACCOUNT","ACCOUNT_TYPE_CD","CLIENT_PRODUCT_CD",["A"],["old"],[dict(s,**identity)],[dict(r,**identity) for r in c],42)

    def test_numeric_preserves_marginal_values_missingness_and_reproducibility(self):
        rng=np.random.default_rng(42); x=rng.uniform(500,5000,20000); y=rng.uniform(100,8000,len(x));x[-1]=np.nan;y[-2]=np.nan
        evidence=numeric_evidence();result,n=conditional_numeric_rank_v1(SOURCE,x,y,evidence,42)
        mask=np.isfinite(x)&np.isfinite(y)
        np.testing.assert_array_equal(np.sort(result[mask]),np.sort(y[mask]));np.testing.assert_array_equal(np.isnan(result),np.isnan(y))
        self.assertEqual(result[-1],y[-1]);self.assertEqual(n,int(mask.sum()))
        self.assertGreater(np.corrcoef(x[mask],result[mask])[0,1],.3)
        self.assertLess(abs(np.corrcoef(x[mask],result[mask])[0,1]-.6), abs(np.corrcoef(x[mask],y[mask])[0,1]-.6))
        repeated,_=conditional_numeric_rank_v1(SOURCE,x,y,list(reversed(evidence)),42)
        np.testing.assert_array_equal(result,repeated)

    def test_numeric_skips_invalid_bounds_sparse_segments_and_outliers(self):
        for mutate in (lambda r:r.pop(),lambda r:r[1].update(pair_count=1),
                       lambda r:r[1].update(upper_bound=123),lambda r:r[1].update(y_p50=float("inf")),
                       lambda r:r[0].update(profile_type="GENERATED"),lambda r:r[0].update(pair_fraction=.5)):
            evidence=numeric_evidence();mutate(evidence)
            with self.assertRaises(DependencyEvidenceError):conditional_numeric_rank_v1(SOURCE,[1000,4500],[200,7000],evidence,42)
        for x,y in (([0,5000],[200,7000]),([1000,5000],[200,9000]),([1000,np.inf],[200,7000])):
            with self.assertRaises(DependencyEvidenceError):conditional_numeric_rank_v1(SOURCE,x,y,numeric_evidence(),42)

    def test_rank_coupling_preserves_raw_mean_but_downstream_cap_changes_saved_marginal(self):
        rng = np.random.default_rng(42)
        limits = rng.uniform(500, 5000, 20000)
        raw = rng.uniform(100, 8000, len(limits))
        coupled, _ = conditional_numeric_rank_v1(SOURCE, limits, raw, numeric_evidence(), 42)
        np.testing.assert_array_equal(np.sort(raw), np.sort(coupled))
        self.assertAlmostEqual(raw.mean(), coupled.mean(), places=9)
        independent_final = np.minimum(raw, 1.25 * limits)
        coupled_final = np.minimum(coupled, 1.25 * limits)
        independent_loss = (raw - independent_final).mean()
        coupled_loss = (coupled - coupled_final).mean()
        self.assertLess(coupled_loss, independent_loss)
        self.assertGreater(coupled_final.mean(), independent_final.mean())
        self.assertAlmostEqual(coupled_final.mean() - independent_final.mean(),
                               independent_loss - coupled_loss, places=9)

    def test_registry_checks_approvals_provenance_and_conflicts(self):
        summaries,cells=categorical_evidence(); profiles=SimpleNamespace(categorical_relationship_stats=summaries,categorical_conditional_stats=cells,numeric_dependency_stats=numeric_evidence())
        for changes,reason in ((dict(approval_status="PENDING"),"not_approved"),(dict(approval_status="REJECTED"),"not_approved"),
                               (dict(has_review_provenance=False),"unverified_approval"),(dict(source_run_id="other"),"source_run_mismatch"),
                               (dict(rule_type="DERIVED"),"no_implementation"),(dict(parent_columns=("OTHER",)),"parent_mismatch")):
            with self.subTest(changes=changes):
                data={"ACCOUNT_TYPE_CD":np.array(["A"],object),"CLIENT_PRODUCT_CD":np.array(["old"],object)}
                events=apply_categorical_dependency_rules(SOURCE,[replace(proposals()[0],**changes)],data,profiles,42)
                self.assertEqual(events[0].reason,reason);self.assertEqual(data["CLIENT_PRODUCT_CD"][0],"old")
        p=proposals()[2]; _,events=apply_numeric_dependency_rule(SOURCE,[p,replace(p,proposal_id="duplicate")],[1000,4500],[200,7000],profiles,42)
        self.assertEqual([e.reason for e in events],["conflicting_approvals"]*2)
        _,events=apply_numeric_dependency_rule(SOURCE,[p],[1000,4500],[200,7000],SimpleNamespace(),42)
        self.assertEqual(events[0].reason,"missing_numeric_dependency_profile");self.assertTrue(events[0].implemented);self.assertFalse(events[0].applied)
        data={"ACCOUNT_TYPE_CD":np.array(["A"],object),"CLIENT_PRODUCT_CD":np.array(["old"],object)}
        events=apply_categorical_dependency_rules(SOURCE,[proposals()[0]],data,SimpleNamespace(),42)
        self.assertEqual(events[0].reason,"missing_categorical_profile");self.assertFalse(events[0].applied)
        self.assertEqual(data["CLIENT_PRODUCT_CD"][0],"old")

    def test_parent_first_chain_and_single_proposal_audit(self):
        summaries,cells=categorical_evidence(); profiles=SimpleNamespace(categorical_relationship_stats=summaries,categorical_conditional_stats=cells,numeric_dependency_stats=numeric_evidence())
        categorical,numeric,remaining=partition_sampling_proposals(reversed(proposals()))
        data={"ACCOUNT_TYPE_CD":np.array(["A","B"]*1000,object),"CLIENT_PRODUCT_CD":np.array(["old"]*2000,object),"TSYS_PRODUCT_CD":np.array(["old"]*2000,object)}
        events=apply_categorical_dependency_rules(SOURCE,categorical,data,profiles,42)
        self.assertFalse(remaining);self.assertEqual(len(numeric),1)
        self.assertEqual([e.proposal_id for e in events],["client","tsys"]);self.assertEqual([e.execution_order for e in events],[-2,-1])
        self.assertTrue(all(e.applied and e.approved and e.rows_processed==2000 for e in events))
        self.assertTrue(all({"C":"T1","D":"T2","E":"T3"}[p]==c for p,c in zip(data["CLIENT_PRODUCT_CD"],data["TSYS_PRODUCT_CD"])))


class GenerationSamplingTests(unittest.TestCase):
    def test_full_generator_keeps_rng_other_tables_and_constraints(self):
        import pandas as pd
        from generation_fixtures import fabricated_profiles
        from synthetic_banking.config import GenerationSettings
        from synthetic_banking.generation import generate_dataset
        profiles,dates=fabricated_profiles();source=profiles.source_run_id
        summaries,cells=categorical_evidence(source)
        profiles.categorical_relationship_stats=summaries;profiles.categorical_conditional_stats=cells
        profiles.numeric_dependency_stats=numeric_evidence(source)
        profiles.category_stats=profiles.category_stats[~((profiles.category_stats.logical_table_name=="TKQ_ACCOUNT")&(profiles.category_stats.column_name=="CLIENT_PRODUCT_CD"))]
        categories=[];quality=[]
        for column,values,ps in (("ACCOUNT_TYPE_CD",["A","B"],[.5,.5]),("CLIENT_PRODUCT_CD",["C","D","E"],[.4,.2,.4]),("TSYS_PRODUCT_CD",["T1","T2","T3"],[.4,.2,.4])):
            categories.extend(dict(logical_table_name="TKQ_ACCOUNT",column_name=column,category_value=value,proportion=p) for value,p in zip(values,ps))
            if column!="CLIENT_PRODUCT_CD":quality.append(dict(run_id=source,logical_table_name="TKQ_ACCOUNT",column_name=column,data_type="STRING",row_count=100,null_count=0,null_pct=0))
        profiles.category_stats=pd.concat([profiles.category_stats,pd.DataFrame(categories)],ignore_index=True)
        profiles.column_quality=pd.concat([profiles.column_quality,pd.DataFrame(quality)],ignore_index=True)
        def run(choices):
            with patch("synthetic_banking.generation.load_rule_proposals",return_value=choices),redirect_stdout(StringIO()):
                return generate_dataset(SimpleNamespace(),profiles,GenerationSettings(1000,42),date_sampler=dates(42))
        previous=run(());updated=run(proposals(source))
        self.assertEqual(previous.rng_state,updated.rng_state)
        for table in ("PERSON","CUSTOMER_ACCOUNT_REL","CUSTOMER_RELATIONSHIP","TRADELINES"):
            pd.testing.assert_frame_equal(previous.tables[table],updated.tables[table])
        a,b=updated.tables["TKQ_ACCOUNT"],updated.tables["TKQ_ACCOUNT_BALANCE"]
        unchanged = [c for c in a.columns if c not in {"CLIENT_PRODUCT_CD", "TSYS_PRODUCT_CD", "_UTILIZATION_RATE", "PAST_DUE_INDICATO_CD", "DELINQUENCY_CNT"}]
        pd.testing.assert_frame_equal(a[unchanged],previous.tables["TKQ_ACCOUNT"][unchanged])
        unchanged = [c for c in b.columns if c not in {"CURRENT_BALANCE_AMT", "AVAILABLE_TO_BUY_AMT", "OVERLIMIT_AMT"}]
        pd.testing.assert_frame_equal(b[unchanged],previous.tables["TKQ_ACCOUNT_BALANCE"][unchanged])
        self.assertTrue(a.ACCOUNT_ID.equals(b.ACCOUNT_ID));self.assertTrue(a.BUSINESSEFFECTIVEDATE.equals(b.BUSINESSEFFECTIVEDATE))
        self.assertTrue((b.CURRENT_BALANCE_AMT<=1.25*a.CREDIT_LIMIT_AMT).all())
        np.testing.assert_array_equal(b.AVAILABLE_TO_BUY_AMT,np.maximum(a.CREDIT_LIMIT_AMT-b.CURRENT_BALANCE_AMT,0))
        np.testing.assert_array_equal(b.OVERLIMIT_AMT,np.maximum(b.CURRENT_BALANCE_AMT-a.CREDIT_LIMIT_AMT,0))
        self.assertEqual([e.execution_order for e in updated.rule_events if e.applied],[-2,-1,0])
        for status in ("PENDING","REJECTED"):
            skipped=run(tuple(replace(p,approval_status=status) for p in proposals(source)))
            for table in previous.tables:pd.testing.assert_frame_equal(previous.tables[table],skipped.tables[table])


if __name__ == "__main__":unittest.main()
