import streamlit as st
import pandas as pd
import numpy as np
from scipy.optimize import linprog
import plotly.graph_objects as go
import io

st.set_page_config(layout="wide")
st.title("⚡ BESS Optimizer (Stable Version)")

# =========================
# PARAMETRI
# =========================
P_max = st.sidebar.number_input("Potenza BESS (MW)", value=2.5)
SoC_min = st.sidebar.number_input("SoC min", value=0.5)
SoC_max = st.sidebar.number_input("SoC max", value=5.0)
eta = st.sidebar.number_input("Efficienza", value=0.9)
oneri = st.sidebar.number_input("Oneri", value=75.0)

# =========================
# UPLOAD
# =========================
file_prezzi = st.file_uploader("Prezzi")
file_pv = st.file_uploader("PV")
file_load = st.file_uploader("Load")

# =========================
# OTTIMIZZAZIONE SEMPLICE
# =========================
def optimize(prices):

    T = len(prices)

    # variabili: charge, discharge
    c = []
    for t in range(T):
        c += [-prices[t], prices[t]]  # maximize -> min negative

    bounds = [(0, P_max)] * (2*T)

    res = linprog(c, bounds=bounds, method='highs')

    charge = res.x[:T]
    discharge = res.x[T:]

    df = pd.DataFrame({
        "Prezzo": prices,
        "Charge": charge,
        "Discharge": discharge
    })

    df["Profit"] = prices*df["Discharge"] - prices*df["Charge"]

    return df

# =========================
# RUN
# =========================
if file_prezzi:

    prices = pd.read_excel(file_prezzi).iloc[:,0].dropna().values

    df = optimize(prices)

    st.metric("💰 Profit", round(df["Profit"].sum(),2))
    st.dataframe(df)

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=df["Prezzo"], name="Prezzo"))
    fig.add_trace(go.Bar(y=df["Charge"], name="Charge"))
    fig.add_trace(go.Bar(y=df["Discharge"], name="Discharge"))
    st.plotly_chart(fig)

else:
    st.info("Carica il file prezzi")
