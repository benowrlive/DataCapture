"""Native statistical analysis (jamovi-style, pure Python — no R, offline).

Builds a tidy table from a project's data and runs the common analyses:
descriptives, frequencies, independent t-test, one-way ANOVA, correlation,
linear & logistic regression, and contingency tables (chi-square).

Results are returned as plain dicts of tables so the template can render them
without any charting library.
"""
from flask import Blueprint, render_template, request, g
from .db import q, pivot_values
from .auth import project_access
from .validators import effective_choices

try:  # heavy scientific stack — installed on first launch via requirements.txt
    import numpy as np
    import pandas as pd
    HAVE_STATS = True
except ImportError:  # keep the app running even if libs aren't installed yet
    np = pd = None
    HAVE_STATS = False

bp = Blueprint("analysis", __name__)

CONTINUOUS = {"integer", "number", "slider"}
CATEGORICAL = {"dropdown", "radio", "yesno", "truefalse"}

ANALYSES = [
    ("tableone", "Table One (baseline characteristics)"),
    ("summary", "Summary table (all variables)"),
    ("descriptives", "Descriptive statistics"),
    ("frequencies", "Frequencies (one variable)"),
    ("ttest", "Independent samples t-test"),
    ("anova", "One-way ANOVA"),
    ("correlation", "Correlation matrix"),
    ("linear", "Linear regression"),
    ("logistic", "Logistic regression"),
    ("contingency", "Cross table (chi-square / Fisher)"),
]


def field_role(f):
    if f["field_type"] in CONTINUOUS or f["validation"] in ("integer", "number"):
        return "continuous"
    if f["field_type"] in CATEGORICAL:
        return "categorical"
    return None


def get_dataframe(pid, project):
    """Return (fields, DataFrame). Continuous columns are floats; categorical
    columns hold human labels; blanks become NaN. One row per record (per event
    for longitudinal projects)."""
    fields = [f for f in q(
        "SELECT f.* FROM fields f JOIN instruments i ON f.instrument_id=i.id"
        " WHERE i.project_id=? ORDER BY i.position, f.position", (pid,))
        if field_role(f)]
    events = (q("SELECT * FROM events WHERE project_id=? ORDER BY position", (pid,))
              if project["is_longitudinal"] else [])
    data, recs = pivot_values(pid)
    label_maps = {f["name"]: dict(effective_choices(f))
                  for f in fields if field_role(f) == "categorical"}
    event_ids = [e["id"] for e in events] or [0]

    rows = []
    for rec in recs:
        for eid in event_ids:
            present = any((rec["record_name"], eid, f["name"]) in data
                          for f in fields)
            if events and not present:
                continue
            row = {}
            for f in fields:
                v = data.get((rec["record_name"], eid, f["name"]), "")
                if v == "" or v is None:
                    row[f["name"]] = None
                elif field_role(f) == "continuous":
                    try:
                        row[f["name"]] = float(v)
                    except (TypeError, ValueError):
                        row[f["name"]] = None
                else:
                    row[f["name"]] = label_maps.get(f["name"], {}).get(v, v)
            rows.append(row)
    cols = [f["name"] for f in fields]
    df = pd.DataFrame(rows, columns=cols)
    for f in fields:
        if field_role(f) == "continuous":
            df[f["name"]] = pd.to_numeric(df[f["name"]], errors="coerce")
    return fields, df


# ---------------------------------------------------------------- helpers

def _r(x, n=3):
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "—"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    try:
        return f"{float(x):.{n}f}"
    except (TypeError, ValueError):
        return str(x)


def _p(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "—"
    return "<.001" if p < 0.001 else f"{p:.3f}"


def _pretty_term(t):
    """Turn statsmodels term names into human-readable labels."""
    import re
    if t == "Intercept":
        return "Intercept"
    m = re.match(r"C\(Q\('([^']+)'\)\)\[T\.(.+)\]$", t)
    if m:
        return f"{m.group(1)}: {m.group(2)}"
    m = re.match(r"Q\('([^']+)'\)$", t)
    if m:
        return m.group(1)
    return t


def _table(title, columns, rows, note=None):
    return {"title": title, "columns": columns, "rows": rows, "note": note}


def _err(msg):
    return {"error": msg}


# ------------------------------------------------ Table One / summary helpers

def _clean(vals):
    v = np.asarray(vals, dtype=float)
    return v[~np.isnan(v)]


def _mean_sd(vals):
    v = _clean(vals)
    if v.size == 0:
        return "—"
    if v.size == 1:
        return f"{v.mean():.1f}"
    return f"{v.mean():.1f} ± {v.std(ddof=1):.1f}"


def _med_iqr(vals):
    v = _clean(vals)
    if v.size == 0:
        return "—"
    q1, q2, q3 = np.percentile(v, [25, 50, 75])
    return f"{q2:.1f} [{q1:.1f}–{q3:.1f}]"


def _is_nonparametric(groups_vals):
    """True if any group is small or fails a Shapiro–Wilk normality check —
    then Table One reports median [IQR] and a rank-based test."""
    from scipy import stats
    for vals in groups_vals:
        v = _clean(vals)
        if v.size < 3:
            return True
        if len(np.unique(v)) < 2:
            continue
        try:
            if stats.shapiro(v)[1] < 0.05:
                return True
        except Exception:
            return True
    return False


def _cont_test(groups_vals, parametric):
    """p-value + test name comparing a continuous variable across groups."""
    from scipy import stats
    gv = [_clean(v) for v in groups_vals]
    usable = [v for v in gv if v.size >= 2]
    if len(usable) < 2:
        return None, "—"
    k = len(usable)
    try:
        if parametric:
            if k == 2:
                return stats.ttest_ind(usable[0], usable[1], equal_var=True)[1], "t-test"
            return stats.f_oneway(*usable)[1], "ANOVA"
        if k == 2:
            return stats.mannwhitneyu(usable[0], usable[1],
                                      alternative="two-sided")[1], "Mann–Whitney"
        return stats.kruskal(*usable)[1], "Kruskal–Wallis"
    except Exception:
        return None, "—"


def _cat_test(ct):
    """p-value + test name for a counts crosstab (rows=levels, cols=groups)."""
    from scipy import stats
    if ct.shape[0] < 2 or ct.shape[1] < 2 or ct.values.sum() == 0:
        return None, "—"
    try:
        chi2, p, dof, expected = stats.chi2_contingency(ct.values)
        if ct.shape == (2, 2) and (expected < 5).any():
            return stats.fisher_exact(ct.values)[1], "Fisher's exact"
        return p, "Chi-square"
    except Exception:
        return None, "—"


def run_tableone(df, names, group, labels):
    """Publication-ready baseline-characteristics table grouped by `group`."""
    if not group:
        return _err("Choose a grouping variable — the column to compare across "
                    "(e.g. Outcome, Sex, Treatment arm).")
    if pd.api.types.is_numeric_dtype(df[group]):
        return _err(f"The grouping variable '{labels.get(group, group)}' looks "
                    "continuous. Pick a categorical group (e.g. Sex, Outcome).")
    names = [n for n in (names or []) if n != group]
    if not names:
        return _err("Pick one or more variables to summarise (other than the group).")

    gclean = df[group].dropna().astype(str)
    glevels = sorted(gclean.unique())
    if len(glevels) < 2:
        return _err(f"'{labels.get(group, group)}' needs at least 2 groups with data.")
    gcounts = gclean.value_counts()
    overall_n = int(gclean.shape[0])

    columns = ["Characteristic", f"Overall (N={overall_n})"]
    columns += [f"{lv} (N={int(gcounts.get(lv, 0))})" for lv in glevels]
    columns += ["p", "Test"]

    rows = []
    for name in names:
        label = labels.get(name, name)
        base = df[[name, group]].dropna(subset=[group]).copy()
        base[group] = base[group].astype(str)
        if pd.api.types.is_numeric_dtype(df[name]):
            groups_vals = [base.loc[base[group] == lv, name].values for lv in glevels]
            overall_vals = base[name].values
            nonparam = _is_nonparametric(groups_vals)
            if nonparam:
                cells = [_med_iqr(overall_vals)] + [_med_iqr(v) for v in groups_vals]
                p, test = _cont_test(groups_vals, parametric=False)
                rows.append([f"{label}, median [IQR]", *cells, _p(p), test])
            else:
                cells = [_mean_sd(overall_vals)] + [_mean_sd(v) for v in groups_vals]
                p, test = _cont_test(groups_vals, parametric=True)
                rows.append([f"{label}, mean ± SD", *cells, _p(p), test])
        else:
            cat = base.dropna(subset=[name])
            s = cat[name].astype(str)
            ct = pd.crosstab(s, cat[group])
            for lv in glevels:
                if lv not in ct.columns:
                    ct[lv] = 0
            ct = ct[glevels]
            p, test = _cat_test(ct)
            rows.append([f"{label}, n (%)", "", *["" for _ in glevels], _p(p), test])
            overall_counts = s.value_counts()
            overall_total = int(overall_counts.sum()) or 1
            for lvl in ct.index:
                oc = int(overall_counts.get(lvl, 0))
                cells = [f"{oc} ({100 * oc / overall_total:.1f})"]
                for gl in glevels:
                    c = int(ct.loc[lvl, gl])
                    tot = int(ct[gl].sum()) or 1
                    cells.append(f"{c} ({100 * c / tot:.1f})")
                rows.append([" " + str(lvl), *cells, "", ""])

    note = (f"Grouped by {labels.get(group, group)}. Continuous variables are "
            "auto-summarised as mean ± SD with t-test/ANOVA, or median [IQR] with "
            "Mann–Whitney/Kruskal–Wallis when a normality check fails; categorical "
            "variables use chi-square, or Fisher's exact for small 2×2 tables. "
            "Percentages are within each column (group).")
    return {"tables": [_table("Table 1. Baseline characteristics",
                              columns, rows, note=note)]}


def run_summary(df, names, labels):
    """One journal-style table summarising every chosen variable, no grouping."""
    if not names:
        return _err("Pick one or more variables (or leave the list empty for all).")
    rows = []
    for name in names:
        label = labels.get(name, name)
        s = df[name]
        if pd.api.types.is_numeric_dtype(s):
            v = _clean(s.values)
            n = int(v.size)
            if n == 0:
                rows.append([f"{label}, mean ± SD", 0, "—"])
                continue
            parts = [_mean_sd(v),
                     "median " + _med_iqr(v),
                     f"range {v.min():.1f}–{v.max():.1f}"]
            rows.append([f"{label}, mean ± SD", n, "; ".join(parts)])
        else:
            s2 = s.dropna().astype(str)
            counts = s2.value_counts()
            total = int(counts.sum()) or 1
            rows.append([f"{label}, n (%)", int(s2.shape[0]), ""])
            for k, c in counts.items():
                rows.append([" " + str(k), "", f"{int(c)} ({100 * c / total:.1f})"])
    return {"tables": [_table("Summary of variables",
                              ["Characteristic", "N", "Summary"], rows,
                              note="Continuous: mean ± SD, median [IQR], range. "
                                   "Categorical: n (%) of non-missing values.")]}


# ---------------------------------------------------------------- analyses

def run_descriptives(df, names):
    if not names:
        return _err("Pick one or more variables.")
    cont_rows, tables = [], []
    for name in names:
        s = df[name]
        if pd.api.types.is_numeric_dtype(s):
            v = s.dropna()
            cont_rows.append([name, len(v), int(s.isna().sum()),
                              _r(v.mean()), _r(v.std(ddof=1)), _r(v.median()),
                              _r(v.min()), _r(v.max())])
        else:
            counts = s.dropna().value_counts()
            total = int(counts.sum()) or 1
            frows = [[str(k), int(c), _r(100 * c / total, 1)]
                     for k, c in counts.items()]
            tables.append(_table(
                f"Frequencies — {name}", ["Level", "Count", "%"], frows,
                note=f"{int(s.isna().sum())} missing"))
    out = []
    if cont_rows:
        out.append(_table("Descriptive statistics",
                          ["Variable", "N", "Missing", "Mean", "SD", "Median",
                           "Min", "Max"], cont_rows))
    out.extend(tables)
    if not out:
        return _err("No summarisable data in the chosen variables.")
    return {"tables": out}


def run_frequencies(df, name):
    if not name:
        return _err("Pick a variable.")
    s = df[name]
    counts = s.dropna().value_counts()
    if counts.empty:
        return _err(f"No data recorded for {name}.")
    total = int(counts.sum())
    n_all = len(s)
    rows, cum = [], 0
    for k, c in counts.items():
        cum += c
        rows.append([str(k), int(c), _r(100 * c / total, 1),
                     _r(100 * cum / total, 1)])
    return {"tables": [_table(
        f"Frequencies — {name}",
        ["Level", "Count", "Valid %", "Cumulative %"], rows,
        note=f"N = {total} valid, {n_all - total} missing")]}


def run_ttest(df, dep, group):
    from scipy import stats
    if not dep or not group:
        return _err("Choose an outcome (number) and a grouping variable.")
    sub = df[[dep, group]].dropna()
    if not pd.api.types.is_numeric_dtype(sub[dep]):
        return _err(f"'{dep}' must be a numeric variable.")
    levels = list(sub[group].unique())
    if len(levels) != 2:
        return _err(f"'{group}' must have exactly 2 groups with data "
                    f"(found {len(levels)}). Try ANOVA for 3+ groups.")
    a = sub[sub[group] == levels[0]][dep]
    b = sub[sub[group] == levels[1]][dep]
    if len(a) < 2 or len(b) < 2:
        return _err("Each group needs at least 2 observations.")
    t, p = stats.ttest_ind(a, b, equal_var=True)
    dfree = len(a) + len(b) - 2
    desc = _table("Group descriptives", ["Group", "N", "Mean", "SD"],
                  [[str(levels[0]), len(a), _r(a.mean()), _r(a.std(ddof=1))],
                   [str(levels[1]), len(b), _r(b.mean()), _r(b.std(ddof=1))]])
    test = _table("Independent samples t-test (Student's)",
                  ["Statistic", "Value"],
                  [["t", _r(t)], ["df", dfree], ["p", _p(p)],
                   ["Mean difference", _r(a.mean() - b.mean())]],
                  note=f"Outcome: {dep} · Groups: {group}")
    return {"tables": [desc, test]}


def run_anova(df, dep, group):
    from scipy import stats
    if not dep or not group:
        return _err("Choose an outcome (number) and a grouping variable.")
    sub = df[[dep, group]].dropna()
    if not pd.api.types.is_numeric_dtype(sub[dep]):
        return _err(f"'{dep}' must be a numeric variable.")
    groups = [g_[dep].values for _, g_ in sub.groupby(group) if len(g_) >= 1]
    levels = [str(k) for k, _ in sub.groupby(group)]
    if len(groups) < 2:
        return _err(f"'{group}' must have at least 2 groups with data.")
    if any(len(g_) < 2 for g_ in groups):
        return _err("Each group needs at least 2 observations.")
    F, p = stats.f_oneway(*groups)
    k = len(groups)
    n = sum(len(g_) for g_ in groups)
    desc = _table("Group descriptives", ["Group", "N", "Mean", "SD"],
                  [[str(k_), len(v), _r(np.mean(v)), _r(np.std(v, ddof=1))]
                   for k_, v in zip(levels, groups)])
    test = _table("One-way ANOVA",
                  ["Statistic", "Value"],
                  [["F", _r(F)], ["df (between)", k - 1],
                   ["df (within)", n - k], ["p", _p(p)]],
                  note=f"Outcome: {dep} · Groups: {group}")
    return {"tables": [desc, test]}


def run_correlation(df, names):
    from scipy import stats
    cont = [n for n in names if pd.api.types.is_numeric_dtype(df[n])]
    if len(cont) < 2:
        return _err("Pick at least 2 numeric variables.")
    header = ["", *cont]
    rrows, prows = [], []
    for a in cont:
        rrow, prow = [a], [a]
        for b in cont:
            pair = df[[a, b]].dropna()
            if a == b:
                rrow.append("1.000")
                prow.append("—")
            elif len(pair) >= 3:
                r, p = stats.pearsonr(pair[a], pair[b])
                rrow.append(_r(r))
                prow.append(_p(p))
            else:
                rrow.append("—")
                prow.append("—")
        rrows.append(rrow)
        prows.append(prow)
    return {"tables": [
        _table("Pearson correlation (r)", header, rrows,
               note="Pairwise complete observations"),
        _table("p-values", header, prows)]}


def run_regression(df, dep, preds, logistic=False):
    import statsmodels.formula.api as smf
    if not dep or not preds:
        return _err("Choose an outcome and at least one predictor.")
    preds = [p for p in preds if p != dep]
    if not preds:
        return _err("Choose at least one predictor different from the outcome.")
    work = df[[dep] + preds].copy()
    terms = []
    for p_ in preds:
        terms.append(p_ if pd.api.types.is_numeric_dtype(work[p_])
                     else f"C(Q('{p_}'))")
    dep_t = f"Q('{dep}')"
    formula = f"{dep_t} ~ " + " + ".join(terms)
    work = work.dropna()
    if len(work) < len(preds) + 2:
        return _err("Not enough complete rows for this model.")
    try:
        if logistic:
            y = work[dep]
            levels = list(pd.Series(y).unique())
            if len(levels) != 2:
                return _err(f"Logistic regression needs a binary outcome; "
                            f"'{dep}' has {len(levels)} levels.")
            mapping = {levels[0]: 0, levels[1]: 1}
            work[dep] = work[dep].map(mapping)
            model = smf.logit(formula, data=work).fit(disp=0)
            rows = []
            for term in model.params.index:
                rows.append([_pretty_term(term), _r(model.params[term]),
                             _r(np.exp(model.params[term])),
                             _r(model.bse[term]), _p(model.pvalues[term])])
            tbl = _table("Logistic regression coefficients",
                         ["Term", "b", "Odds ratio", "SE", "p"], rows,
                         note=f"Outcome: {dep} (1 = {levels[1]}), N = {len(work)}")
            fit = _table("Model fit", ["Statistic", "Value"],
                         [["Pseudo R² (McFadden)", _r(model.prsquared)],
                          ["Log-likelihood", _r(model.llf)],
                          ["N", len(work)]])
            return {"tables": [tbl, fit]}
        else:
            if not pd.api.types.is_numeric_dtype(work[dep]):
                return _err(f"Linear regression needs a numeric outcome; "
                            f"'{dep}' is categorical. Try logistic regression.")
            model = smf.ols(formula, data=work).fit()
            rows = []
            for term in model.params.index:
                rows.append([_pretty_term(term), _r(model.params[term]),
                             _r(model.bse[term]), _r(model.tvalues[term]),
                             _p(model.pvalues[term])])
            tbl = _table("Linear regression coefficients",
                         ["Term", "b", "SE", "t", "p"], rows,
                         note=f"Outcome: {dep}, N = {len(work)}")
            fit = _table("Model fit", ["Statistic", "Value"],
                         [["R²", _r(model.rsquared)],
                          ["Adjusted R²", _r(model.rsquared_adj)],
                          ["F", _r(model.fvalue)],
                          ["p (model)", _p(model.f_pvalue)],
                          ["N", len(work)]])
            return {"tables": [tbl, fit]}
    except Exception as e:  # keep the app alive on singular models etc.
        return _err(f"Could not fit the model: {e}")


def run_contingency(df, rowv, colv):
    from scipy import stats
    if not rowv or not colv or rowv == colv:
        return _err("Choose two different categorical variables.")
    sub = df[[rowv, colv]].dropna().astype(str)
    if sub.empty:
        return _err("No overlapping data for these two variables.")
    ct = pd.crosstab(sub[rowv], sub[colv])
    if ct.shape[0] < 2 or ct.shape[1] < 2:
        return _err("Each variable needs at least 2 levels with data.")
    chi2, p, dof, expected = stats.chi2_contingency(ct.values)
    n_small = int((expected < 5).sum())

    # cells show count (column %) — the distribution within each column group
    coltot = {c: int(ct[c].sum()) or 1 for c in ct.columns}
    header = [f"{rowv} \\ {colv}", *[str(c) for c in ct.columns], "Total"]
    rows = []
    for idx, r in ct.iterrows():
        cells = [f"{int(r[c])} ({100 * int(r[c]) / coltot[c]:.1f})" for c in ct.columns]
        rows.append([str(idx), *cells, int(r.sum())])
    rows.append(["Total", *[f"{int(ct[c].sum())} (100.0)" for c in ct.columns],
                 int(ct.values.sum())])

    use_fisher = ct.shape == (2, 2) and (expected < 5).any()
    test_rows = [["χ²", _r(chi2)], ["df", int(dof)], ["p (chi-square)", _p(p)]]
    if use_fisher:
        oddsr, pf = stats.fisher_exact(ct.values)
        test_rows += [["Fisher's exact p", _p(pf)], ["Odds ratio", _r(oddsr)]]
    test_rows.append(["N", int(ct.values.sum())])

    note = "Cells show count (column %)."
    if n_small:
        note += (f" {n_small} cell(s) have an expected count below 5 — "
                 + ("Fisher's exact test is preferred and shown below."
                    if use_fisher else
                    "interpret chi-square with caution (Fisher's exact applies "
                    "only to 2×2 tables)."))
    primary = "Fisher's exact test" if use_fisher else "Chi-square test of independence"
    return {"tables": [
        _table("Contingency table — count (column %)", header, rows, note=note),
        _table(primary, ["Statistic", "Value"], test_rows)]}


DISPATCH = {
    "tableone": lambda df, F: run_tableone(df, F["vars"], F["group"], F["labels"]),
    "summary": lambda df, F: run_summary(df, F["vars"] or F["all_names"], F["labels"]),
    "descriptives": lambda df, F: run_descriptives(df, F["vars"]),
    "frequencies": lambda df, F: run_frequencies(df, F["dep"] or (F["vars"][0] if F["vars"] else "")),
    "ttest": lambda df, F: run_ttest(df, F["dep"], F["group"]),
    "anova": lambda df, F: run_anova(df, F["dep"], F["group"]),
    "correlation": lambda df, F: run_correlation(df, F["vars"]),
    "linear": lambda df, F: run_regression(df, F["dep"], F["preds"], logistic=False),
    "logistic": lambda df, F: run_regression(df, F["dep"], F["preds"], logistic=True),
    "contingency": lambda df, F: run_contingency(df, F["dep"], F["group"]),
}


@bp.route("/p/<int:pid>/analysis")
@project_access("read_only")
def analysis(pid):
    if not HAVE_STATS:
        return render_template("analysis.html", variables=[], analyses=ANALYSES,
                               atype="descriptives", form={}, result=None,
                               n_rows=0, stats_missing=True)
    fields, df = get_dataframe(pid, g.project)
    variables = [{"name": f["name"], "label": f["label"], "role": field_role(f)}
                 for f in fields]
    atype = request.args.get("type", "tableone")
    form = {
        "vars": request.args.getlist("vars"),
        "dep": request.args.get("dep", ""),
        "group": request.args.get("group", ""),
        "preds": request.args.getlist("preds"),
        "labels": {f["name"]: f["label"] for f in fields},
        "all_names": [f["name"] for f in fields],
    }
    has_input = (form["vars"] or form["dep"] or form["group"]
                 or form["preds"] or atype == "summary")
    result = None
    if atype in DISPATCH and variables and has_input:
        try:
            result = DISPATCH[atype](df, form)
        except Exception as e:
            result = _err(f"Analysis failed: {e}")
    return render_template("analysis.html", variables=variables, analyses=ANALYSES,
                           atype=atype, form=form, result=result,
                           n_rows=len(df))
