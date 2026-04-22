import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

st.set_page_config(layout="wide")
st.title("⚡ BESS Optimizer – Ora Energy")

# =========================
# SIDEBAR PARAMETRI
# =========================
st.sidebar.header("Parametri BESS")

P_charge_max = st.sidebar.number_input("Potenza carica (MW)", value=2.5)
P_discharge_max = st.sidebar.number_input("Potenza scarica (MW)", value=2.5)

SoC_min = st.sidebar.number_input("SoC minimo (MWh)", value=0.5)
SoC_max = st.sidebar.number_input("SoC massimo (MWh)", value=5.0)

eta_rt = st.sidebar.number_input("Efficienza round trip (%)", value=90.0)/100
oneri = st.sidebar.number_input("Oneri evitati (€/MWh)", value=75.0)

P_grid_in_max = st.sidebar.number_input("Limite immissione (MW)", value=7.0)
P_grid_out_max = st.sidebar.number_input("Limite prelievo (MW)", value=9.0)

# =========================
# UPLOAD FILE
# =========================
st.header("📂 Upload dati")

file_prezzi = st.file_uploader("Prezzi (Excel/CSV)", type=["xlsx","csv"])
file_pv = st.file_uploader("Produzione FV", type=["xlsx","csv"])
file_load = st.file_uploader("Consumi", type=["xlsx","csv"])

# =========================
# LETTURA FILE
# =========================
def read_file(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file).iloc[:,0]
    else:
        return pd.read_excel(file).iloc[:,0]

# =========================
# LOGICA SEMPLIFICATA (robusta cloud)
# =========================
def optimize(prices, pv, load):

    T = len(prices)

    charge = np.zeros(T)
    discharge = np.zeros(T)
    soc = np.zeros(T)

    soc[0] = SoC_min

    for t in range(1, T):

        # strategia semplice: arbitraggio + autoconsumo
        if prices[t] < np.mean(prices):
            charge[t] = min(P_charge_max, SoC_max - soc[t-1])
        else:
            discharge[t] = min(P_discharge_max, soc[t-1] - SoC_min)

        soc[t] = soc[t-1] + charge[t]*eta_rt - discharge[t]/eta_rt

        soc[t] = max(SoC_min, min(SoC_max, soc[t]))

    df = pd.DataFrame({
        "Prezzo": prices,
        "PV": pv,
        "Load": load,
        "Charge": charge,
        "Discharge": discharge,
        "SoC": soc
    })

    df["Profit"] = (
        df["Prezzo"]*df["Discharge"]
        - df["Prezzo"]*df["Charge"]
        + oneri*np.minimum(df["Discharge"], df["Load"])
    )

    return df

# =========================
# EXPORT
# =========================
def export_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Risultati", index=False)
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

    df = optimize(prezzi, pv, load)

    # =========================
    # KPI
    # =========================
    st.header("📊 Risultati")

    col1, col2, col3 = st.columns(3)

    col1.metric("💰 Profit totale (€)", round(df["Profit"].sum(),2))
    col2.metric("⚡ Energia scaricata (MWh)", round(df["Discharge"].sum(),2))
    col3.metric("🔋 SoC medio", round(df["SoC"].mean(),2))

    st.dataframe(df)

    # =========================
    # GRAFICI
    # =========================
    fig = go.Figure()

    fig.add_trace(go.Scatter(y=df["Prezzo"], name="Prezzo"))
    fig.add_trace(go.Bar(y=df["Charge"], name="Carica"))
    fig.add_trace(go.Bar(y=df["Discharge"], name="Scarica"))

    st.plotly_chart(fig, use_container_width=True)

    # SOC
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(y=df["SoC"], name="SoC"))
    st.plotly_chart(fig2, use_container_width=True)

    # =========================
    # DOWNLOAD
    # =========================
    excel = export_excel(df)

    st.download_button(
        "📥 Scarica risultati Excel",
        data=excel,
        file_name="bess_results.xlsx"
    )

else:
    st.info("Carica tutti i file per avviare l'ottimizzazione")
