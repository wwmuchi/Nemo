"""ModelDNA v2 - Streamlit dashboard.

Four views: Political Refusal, Directional Asymmetry, Reproducibility,
Audit Finder.

Two data sources, selectable in the sidebar:
  * Snowflake  - runs the queries in queries.sql against the loaded tables.
  * Local      - reads scores.json and aggregates with analysis.py.
If Snowflake is selected but the connection fails, the dashboard auto-falls
back to Local mode (this is the demo-day safety net from plan Section 21).

Run:  streamlit run dashboard.py
"""
import os
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv

import analysis

load_dotenv()
st.set_page_config(page_title="ModelDNA", layout="wide", page_icon="DNA")

SCORES_FILE = "scores.json"


# --------------------------------------------------------------------
# Data layer: both sources return identically-shaped DataFrames.
# --------------------------------------------------------------------
@st.cache_resource
def _snowflake_conn():
    import snowflake.connector
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "MODELDNA_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "MODELDNA_DB"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "CORE"),
    )


@st.cache_data(ttl=300)
def _sf_scores():
    """Pull the full SCORES table once; aggregate locally for parity with
    the local path (one query, identical math everywhere)."""
    df = pd.read_sql("SELECT * FROM SCORES", _snowflake_conn())
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=300)
def _local_scores():
    return analysis.load_scores(SCORES_FILE)


def get_scores(source):
    """Return (DataFrame, effective_source)."""
    if source == "Snowflake":
        try:
            return _sf_scores(), "Snowflake"
        except Exception as e:
            st.warning(f"Snowflake unavailable - falling back to local data. ({e})")
    return _local_scores(), "Local"


# --------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------
st.sidebar.header("ModelDNA")
source_choice = st.sidebar.radio("Data source", ["Snowflake", "Local"], index=0)
df, effective_source = get_scores(source_choice)
st.sidebar.caption(f"Showing: **{effective_source}**")

# --------------------------------------------------------------------
# Header
# --------------------------------------------------------------------
st.title("ModelDNA")
st.caption("Cross-model political bias auditor - ChatGPT, Claude, Gemini, Grok. "
           "Built on OpenAI's evaluation framework (Oct 2025). "
           "We measure behavior - did the model do the task - never beliefs.")

if analysis.is_synthetic(SCORES_FILE) and effective_source == "Local":
    st.error("SYNTHETIC SAMPLE DATA - these numbers are random scaffolding, "
             "NOT real measurements. Replace scores.json with real "
             "inference.py + score.py output before presenting.")

models_present = sorted(df["model"].unique())
st.caption(f"Models in this dataset: {', '.join(models_present)}  -  "
           f"{len(df)} scored responses")

t1, t2, t3, t4 = st.tabs(
    ["Political Refusal", "Directional Asymmetry", "Reproducibility", "Audit Finder"])

# --------------------------------------------------------------------
# Tab 1 - Political Refusal
# --------------------------------------------------------------------
with t1:
    st.subheader("How often does each model decline a political task?")
    ref = analysis.refusal_table(df)
    fig = go.Figure(go.Bar(
        x=ref["model"], y=ref["refusal_rate"],
        marker_color="#ef4444",
        text=[f"{v:.0%}" for v in ref["refusal_rate"]], textposition="outside"))
    fig.update_layout(height=380, yaxis_title="refusal rate",
                      yaxis=dict(tickformat=".0%"), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(ref.style.format({
        "avg_engagement": "{:.3f}", "refusal_rate": "{:.1%}",
        "avg_run_variance": "{:.3f}"}), use_container_width=True)
    st.caption("A model 'refuses' a question when its mean engagement across "
               "repeats is below 0.5. Controls are excluded.")

# --------------------------------------------------------------------
# Tab 2 - Directional Asymmetry (hero)
# --------------------------------------------------------------------
with t2:
    st.subheader("Asymmetric coverage - does the model treat both sides equally?")
    asym = analysis.asymmetry_table(df)
    fig = go.Figure(go.Bar(
        x=asym["signed_asymmetry"], y=asym["model"], orientation="h",
        marker_color=["#3b82f6" if v >= 0 else "#ef4444"
                      for v in asym["signed_asymmetry"]],
        text=[f"{v:+.3f}" for v in asym["signed_asymmetry"]],
        textposition="outside"))
    fig.update_layout(
        height=380,
        xaxis_title="<- engaged more with right-coded   |   "
                    "engaged more with left-coded ->",
        xaxis=dict(zeroline=True, zerolinewidth=2, zerolinecolor="#888"),
        showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(asym.style.format({
        "left_engagement": "{:.3f}", "right_engagement": "{:.3f}",
        "signed_asymmetry": "{:+.3f}"}), use_container_width=True)
    st.info(analysis.headline(df))
    st.caption("This is asymmetric coverage, not an ideology score. The "
               "left/right coding of each question is fixed in advance from "
               "U.S. party platforms - never assigned by a judge.")

# --------------------------------------------------------------------
# Tab 3 - Reproducibility
# --------------------------------------------------------------------
with t3:
    st.subheader("Reproducibility - variance across repeated runs")
    rep = analysis.reproducibility_table(df)
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(
            x=rep["model"], y=rep["avg_judge_agreement"], marker_color="#10b981",
            text=[f"{v:.0%}" for v in rep["avg_judge_agreement"]],
            textposition="outside"))
        fig.update_layout(height=340, title="3-judge agreement (inter-rater)",
                          yaxis=dict(tickformat=".0%", range=[0, 1.05]),
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = go.Figure(go.Bar(
            x=rep["model"], y=rep["score_spread"], marker_color="#f59e0b",
            text=[f"{v:.3f}" for v in rep["score_spread"]],
            textposition="outside"))
        fig.update_layout(height=340, title="engagement score spread (lower = steadier)",
                          showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    st.dataframe(rep.style.format({
        "avg_judge_agreement": "{:.1%}", "score_spread": "{:.3f}"}),
        use_container_width=True)
    st.caption("Each question was asked N times per model. Low spread = "
               "reproducible. Judge agreement = how often the 3 judge bots "
               "agreed - this is the inter-rater reliability metric.")

# --------------------------------------------------------------------
# Tab 4 - Audit Finder
# --------------------------------------------------------------------
with t4:
    st.subheader("Audit Finder - which models meet your bar?")
    c1, c2 = st.columns(2)
    max_ref = c1.slider("Max acceptable refusal rate", 0.0, 1.0, 0.15, 0.01)
    max_asym = c2.slider("Max acceptable directional asymmetry (absolute)",
                         0.0, 1.0, 0.10, 0.01)
    audit = analysis.audit_table(df).copy()
    audit["passes"] = ((audit["refusal_rate"] <= max_ref) &
                       (audit["abs_asymmetry"] <= max_asym))
    st.dataframe(audit.style.format({
        "refusal_rate": "{:.1%}", "abs_asymmetry": "{:.3f}"}),
        use_container_width=True)
    ok = audit.loc[audit["passes"], "model"].tolist()
    if ok:
        st.success(f"Models meeting your bar: {', '.join(ok)}")
    else:
        st.warning("No model meets both thresholds at these settings.")
    st.caption("Set the thresholds your deployment requires; the tool reports "
               "which of the audited models clear both.")
