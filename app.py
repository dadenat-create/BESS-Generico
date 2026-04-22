import streamlit as st
import pandas as pd
import numpy as np
from ortools.linear_solver import pywraplp
import plotly.graph_objects as go
import io
import math

st.set_page_config(layout="wide")
st.title("⚡ BESS Optimizer – Ora Energy (Client Version)")

# =========================
# PARAMETRI
# =========================
st.sidebar.header("Parametri BESS")

P_charge = st.sidebar.number_input("Potenza carica (MW)", value=2.5)
P_discharge = st.sidebar.number_input("Potenza scarica (MW)", value=2.5)

SoC_min = st.sidebar.number_input("SoC min (MWh)", value=0.5)
SoC_max = st.sidebar.number_input("SoC max (MWh)", value=5.0)

eta_rt = st.sidebar.number_input("Efficienza round-trip (%)", value=90.0)/100
eta = math.sqrt(eta_rt)

oneri = st.sidebar.number_input("Oneri evitati (€/MWh)", value=75.0)

P_grid_in = st.sidebar.number_input("Limite immissione (MW)", value=7.0)
P_grid_out = st.sidebar.number_input("Limite prelievo (MW)", value=9.0)

# =========================
# FILE
# =========================
file_prezzi = st.file_uploader("Prezzi")
file_pv = st.file_uploader("Produzione FV")
file_load = st.file_uploader("Consumi")

def read_file(f):
    return pd.read_excel(f).iloc[:,0]

# =========================
# MILP
# =========================
def optimize(prices, pv, load):

    T = len(prices)
    solver = pywraplp.Solver.CreateSolver("SCIP")

    cg, cpv, dg, dl = [], [], [], []
    soc, u = [], []

    for t in range(T):
        cg.append(solver.NumVar(0, P_charge, f"cg_{t}"))
        cpv.append(solver.NumVar(0, P_charge, f"cpv_{t}"))
        dg.append(solver.NumVar(0, P_discharge, f"dg_{t}"))
        dl.append(solver.NumVar(0, P_discharge, f"dl_{t}"))
        soc.append(solver.NumVar(SoC_min, SoC_max, f"soc_{t}"))
        u.append(solver.IntVar(0,1,f"u_{t}"))

    # obiettivo
    obj = solver.Objective()
    for t in range(T):
        obj.SetCoefficient(dg[t], prices[t])
        obj.SetCoefficient(cg[t], -prices[t])
        obj.SetCoefficient(cpv[t], -prices[t])
        obj.SetCoefficient(dl[t], oneri)
    obj.SetMaximization()

    # vincoli
    for t in range(T):

        solver.Add(cg[t] + cpv[t] <= P_charge * u[t])
        solver.Add(dg[t] + dl[t] <= P_discharge * (1-u[t]))

        solver.Add(cg[t] <= P_grid_out)
        solver.Add(dg[t] <= P_grid_in)

        if t == 0:
            solver.Add(soc[t] == SoC_min + eta*(cg[t]+cpv[t]) - (dg[t]+dl[t])/eta)
        else:
            solver.Add(soc[t] == soc[t-1] + eta*(cg[t]+cpv[t]) - (dg[t]+dl[t])/eta)

    solver.Solve()

    df = pd.DataFrame({
        "Prezzo": prices,
        "PV": pv,
        "Load": load,
        "Charge_grid": [cg[t].solution_value() for t in range(T)],
        "Charge_PV": [cpv[t].solution_value() for t in range(T)],
        "Discharge_grid": [dg[t].solution_value() for t in range(T)],
        "Discharge_load": [dl[t].solution_value() for t in range(T)],
        "SoC": [soc[t].solution_value() for t in range(T)]
    })

    # KPI economici
    df["Revenue_market"] = df["Prezzo"]*df["Discharge_grid"]
    df["Cost_charge"] = df["Prezzo"]*(df["Charge_grid"]+df["Charge_PV"])
    df["Saving_oneri"] = df["Discharge_load"]*oneri

    df["Profit"] = df["Revenue_market"] - df["Cost_charge"] + df["Saving_oneri"]

    return df

# =========================
# EXPORT
# =========================
def export_excel(df):

    daily = df.groupby(df.index//24).sum()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Dettaglio")
        daily.to_excel(writer, sheet_name="Giornaliero")

    return output.getvalue()

# =========================
# RUN
# =========================
if file_prezzi and file_pv and file_load:

    prices = read_file(file_prezzi)
    pv = read_file(file_pv)
    load = read_file(file_load)

    T = min(len(prices), len(pv), len(load))

    prices = prices[:T].values
    pv = pv[:T].values
    load = load[:T].values

    df = optimize(prices, pv, load)

    # KPI
    st.header("📊 KPI")

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Profit totale", round(df["Profit"].sum(),2))
    col2.metric("📈 Ricavi mercato", round(df["Revenue_market"].sum(),2))
    col3.metric("⚡ Risparmio oneri", round(df["Saving_oneri"].sum(),2))

    # grafici
    st.header("📉 Andamento")

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=df["Prezzo"], name="Prezzo"))
    fig.add_trace(go.Bar(y=df["Charge_grid"], name="Carica"))
    fig.add_trace(go.Bar(y=df["Discharge_grid"], name="Scarica"))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(y=df["SoC"], name="SoC"))
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df)

    # download
    st.download_button(
        "📥 Scarica Excel",
        data=export_excel(df),
        file_name="bess_analysis.xlsx"
    )

else:
    st.info("Carica tutti i file per partire")
