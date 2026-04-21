import streamlit as st
import pandas as pd
import pulp
import math
import plotly.graph_objects as go
import io

st.set_page_config(layout="wide")
st.title("⚡ BESS Optimizer")

# =========================
# SIDEBAR PARAMETRI
# =========================
st.sidebar.header("Parametri BESS")

P_charge_max = st.sidebar.number_input("Potenza carica (MW)", value=2.5)
P_discharge_max = st.sidebar.number_input("Potenza scarica (MW)", value=2.5)

SoC_min = st.sidebar.number_input("SoC minimo (MWh)", value=0.5)
SoC_max = st.sidebar.number_input("SoC massimo (MWh)", value=5.0)

eta_rt = st.sidebar.number_input("Efficienza round-trip (%)", value=90.0)/100
eta = math.sqrt(eta_rt)

oneri = st.sidebar.number_input("Oneri evitati (€/MWh)", value=75.0)

P_grid_in_max = st.sidebar.number_input("Limite immissione (MW)", value=7.0)
P_grid_out_max = st.sidebar.number_input("Limite prelievo (MW)", value=9.0)

# =========================
# UPLOAD FILE
# =========================
st.header("📂 Upload dati")

file_prezzi = st.file_uploader("Prezzi (una colonna)", type=["xlsx"])
file_pv = st.file_uploader("Produzione FV", type=["xlsx"])
file_load = st.file_uploader("Consumi", type=["xlsx"])

# =========================
# OTTIMIZZAZIONE
# =========================
def optimize(prices, pv, load):

    T = len(prices)
    model = pulp.LpProblem("BESS", pulp.LpMaximize)

    cg = pulp.LpVariable.dicts("cg", range(T), 0)
    cpv = pulp.LpVariable.dicts("cpv", range(T), 0)
    dg = pulp.LpVariable.dicts("dg", range(T), 0)
    dl = pulp.LpVariable.dicts("dl", range(T), 0)

    pvl = pulp.LpVariable.dicts("pvl", range(T), 0)
    pvg = pulp.LpVariable.dicts("pvg", range(T), 0)
    gtl = pulp.LpVariable.dicts("gtl", range(T), 0)

    soc = pulp.LpVariable.dicts("soc", range(T), SoC_min, SoC_max)
    u = pulp.LpVariable.dicts("mode", range(T), cat="Binary")

    model += pulp.lpSum([
        prices[t]*dg[t]
        - prices[t]*cg[t]
        - prices[t]*cpv[t]
        + oneri*dl[t]
        for t in range(T)
    ])

    for t in range(T):

        model += cg[t] + cpv[t] <= P_charge_max * u[t]
        model += dg[t] + dl[t] <= P_discharge_max * (1-u[t])

        model += cg[t] + cpv[t] <= P_charge_max
        model += dg[t] + dl[t] <= P_discharge_max

        model += pv[t] == pvl[t] + cpv[t] + pvg[t]
        model += load[t] == pvl[t] + dl[t] + gtl[t]

        model += dg[t] + pvg[t] <= P_grid_in_max
        model += cg[t] + gtl[t] <= P_grid_out_max

        if t == 0:
            model += soc[t] == SoC_min + eta*(cg[t]+cpv[t]) - (dg[t]+dl[t])/eta
        else:
            model += soc[t] == soc[t-1] + eta*(cg[t]+cpv[t]) - (dg[t]+dl[t])/eta

    model.solve(pulp.PULP_CBC_CMD(msg=0))

    df = pd.DataFrame({
        "Prezzo": prices,
        "PV": pv,
        "Load": load,
        "Charge_grid": [cg[t].value() for t in range(T)],
        "Charge_PV": [cpv[t].value() for t in range(T)],
        "Discharge_grid": [dg[t].value() for t in range(T)],
        "Discharge_load": [dl[t].value() for t in range(T)],
        "SoC": [soc[t].value() for t in range(T)]
    })

    df["Profit"] = (
        df["Prezzo"]*df["Discharge_grid"]
        - df["Prezzo"]*df["Charge_grid"]
        - df["Prezzo"]*df["Charge_PV"]
        + oneri*df["Discharge_load"]
    )

    return df

# =========================
# EXPORT
# =========================
def export_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Dettaglio", index=False)
    return output.getvalue()

# =========================
# RUN
# =========================
if file_prezzi and file_pv and file_load:

    prices = pd.to_numeric(pd.read_excel(file_prezzi).iloc[:,0], errors='coerce').dropna()
    pv = pd.to_numeric(pd.read_excel(file_pv).iloc[:,0], errors='coerce').dropna()
    load = pd.to_numeric(pd.read_excel(file_load).iloc[:,0], errors='coerce').dropna()

    T = min(len(prices), len(pv), len(load))

    prices = prices[:T].tolist()
    pv = pv[:T].tolist()
    load = load[:T].tolist()

    df = optimize(prices, pv, load)

    st.header("📊 Risultati")

    col1, col2 = st.columns(2)
    col1.metric("💰 Profit totale (€)", round(df["Profit"].sum(),2))
    col2.metric("⚡ Energia scaricata (MWh)", round(df["Discharge_grid"].sum()+df["Discharge_load"].sum(),2))

    st.dataframe(df)

    # Grafico
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=df["Prezzo"], name="Prezzo"))
    fig.add_trace(go.Bar(y=df["Charge_grid"], name="Carica rete"))
    fig.add_trace(go.Bar(y=df["Discharge_grid"], name="Scarica rete"))
    st.plotly_chart(fig, use_container_width=True)

    # Download
    excel = export_excel(df)
    st.download_button("📥 Scarica Excel", data=excel, file_name="risultati_bess.xlsx")

else:
    st.info("Carica tutti i file per avviare l'ottimizzazione")
