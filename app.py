import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

st.set_page_config(layout="wide")
st.title("⚡ BESS Optimizer – Ora Energy")

# =========================
# PARAMETRI
# =========================
st.sidebar.header("Parametri BESS")

P_max = st.sidebar.number_input("Potenza BESS (MW)", value=2.5)
E_max = st.sidebar.number_input("Energia BESS (MWh)", value=5.0)

SoC_min = st.sidebar.number_input("SoC min (%)", value=10.0)/100
SoC_max = st.sidebar.number_input("SoC max (%)", value=100.0)/100

eta_rt = st.sidebar.number_input("Efficienza round-trip (%)", value=90.0)/100
oneri = st.sidebar.number_input("Oneri evitati (€/MWh)", value=75.0)

# =========================
# FILE
# =========================
st.header("📂 Upload dati")

file_prezzi = st.file_uploader("Prezzi", type=["xlsx","csv"])
file_pv = st.file_uploader("Produzione FV", type=["xlsx","csv"])
file_load = st.file_uploader("Consumi", type=["xlsx","csv"])

def read_file(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file).iloc[:,0]
    else:
        return pd.read_excel(file).iloc[:,0]

# =========================
# LOGICA OTTIMIZZAZIONE
# =========================
def simulate(prices, pv, load):

    T = len(prices)

    soc = np.zeros(T)
    soc[0] = SoC_min * E_max

    charge = np.zeros(T)
    discharge = np.zeros(T)

    price_low = np.percentile(prices, 30)
    price_high = np.percentile(prices, 70)

    for t in range(1, T):

        # PRIORITÀ 1: autoconsumo FV
        excess_pv = max(0, pv[t] - load[t])

        if excess_pv > 0:
            charge_pv = min(P_max, excess_pv, (SoC_max*E_max - soc[t-1]))
            charge[t] += charge_pv

        # PRIORITÀ 2: arbitraggio
        if prices[t] < price_low:
            charge_grid = min(P_max - charge[t], SoC_max*E_max - soc[t-1])
            charge[t] += charge_grid

        elif prices[t] > price_high:
            discharge[t] = min(P_max, soc[t-1] - SoC_min*E_max)

        # update SOC
        soc[t] = soc[t-1] + charge[t]*eta_rt - discharge[t]/eta_rt

        soc[t] = max(SoC_min*E_max, min(SoC_max*E_max, soc[t]))

    df = pd.DataFrame({
        "Prezzo": prices,
        "PV": pv,
        "Load": load,
        "Charge": charge,
        "Discharge": discharge,
        "SoC": soc
    })

    # KPI economici
    df["Revenue"] = df["Discharge"] * df["Prezzo"]
    df["Cost"] = df["Charge"] * df["Prezzo"]
    df["Saving_oneri"] = np.minimum(df["Discharge"], df["Load"]) * oneri

    df["Profit"] = df["Revenue"] - df["Cost"] + df["Saving_oneri"]

    return df

# =========================
# EXPORT
# =========================
def export_excel(df):

    daily = df.groupby(df.index // 24).sum()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Dettaglio")
        daily.to_excel(writer, sheet_name="Giornaliero")

    return output.getvalue()

# =========================
# RUN
# =========================
if file_prezzi and file_pv and file_load:

    prezzi = pd.to_numeric(read_file(file_prezzi), errors='coerce').dropna()
    pv = pd.to_numeric(read_file(file_pv), errors='coerce').dropna()
    load = pd.to_numeric(read_file(file_load), errors='coerce').dropna()

    T = min(len(prezzi), len(pv), len(load))

    prezzi = prezzi[:T].values
    pv = pv[:T].values
    load = load[:T].values

    df = simulate(prezzi, pv, load)

    # =========================
    # KPI
    # =========================
    st.header("📊 KPI")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("💰 Profit totale (€)", round(df["Profit"].sum(),2))
    col2.metric("📈 Ricavi mercato", round(df["Revenue"].sum(),2))
    col3.metric("⚡ Risparmio oneri", round(df["Saving_oneri"].sum(),2))
    col4.metric("🔋 Cicli eq.", round(df["Discharge"].sum()/(2*E_max),2))

    # =========================
    # GRAFICI
    # =========================
    st.header("📉 Andamento")

    fig = go.Figure()
    fig.add_trace(go.Scatter(y=df["Prezzo"], name="Prezzo"))
    fig.add_trace(go.Bar(y=df["Charge"], name="Carica"))
    fig.add_trace(go.Bar(y=df["Discharge"], name="Scarica"))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(y=df["SoC"], name="SoC"))
    st.plotly_chart(fig2, use_container_width=True)

    st.dataframe(df)

    # =========================
    # DOWNLOAD
    # =========================
    st.download_button(
        "📥 Scarica Excel",
        data=export_excel(df),
        file_name="bess_results.xlsx"
    )

else:
    st.info("Carica tutti i file per partire")
