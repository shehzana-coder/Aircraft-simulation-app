import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from datetime import timedelta
import time

# --- 2026 COMPLIANT CONFIG ---
st.set_page_config(page_title="SkyPredict | Master Pilot Build", page_icon="✈️", layout="wide")

# --- ADAPTIVE CSS ---
st.markdown("""
    <style>
    .stMetric { padding: 15px; border-radius: 12px; border: 1px solid rgba(128,128,128,0.3); }
    [data-testid="stMetricValue"] { color: #0078ff !important; font-weight: bold !important; }
    .status-box { padding: 15px; border-radius: 10px; margin-bottom: 20px; font-weight: bold; text-align: center; border: 2px solid #0078ff; }
    </style>
    """, unsafe_allow_html=True)

# --- MATH ENGINE ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi, dlambda = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1-a))

def simulate_flight(fuel_l, ac_key, wind_pct, payload_kg, total_d):
    ac = aircraft_data[ac_key]
    fuel_kg = fuel_l * 0.84
    # Refined fuel rate (kg per second)
    base_rate = ac['fuel_rate']
    eff_rate = base_rate * (1 + (payload_kg / 200000)) * (1 + (wind_pct / 100))
    
    cl_t = ac['cruise_alt'] / ac['climb_rate']
    cl_d = 0.5 * cl_t * ac['cruise_speed']
    cl_f = cl_t * eff_rate * 1.2 # Climb uses more fuel
    
    de_t = ac['cruise_alt'] / ac['descent_rate']
    de_d = 0.5 * de_t * ac['cruise_speed']
    
    dist_rem = max(0, total_d - cl_d - de_d)
    cr_t = dist_rem / ac['cruise_speed']
    cr_f_req = cr_t * eff_rate
    
    total_f_req = cl_f + cr_f_req
    
    d_pts, h_pts, f_pts, statuses = [], [], [], []
    curr_f, curr_d = fuel_kg, 0
    
    # 1. Climb
    for t in np.linspace(0, cl_t, 50):
        step_f = (cl_t/50) * eff_rate * 1.2
        if curr_f > step_f:
            curr_f -= step_f; curr_d += (cl_d / 50)
            d_pts.append(curr_d); h_pts.append(t * ac['climb_rate'])
            f_pts.append(curr_f); statuses.append("Climbing")
        else: statuses.append("CRASHED"); break

    # 2. Cruise
    if "CRASHED" not in statuses:
        for t in np.linspace(0, cr_t, 100):
            step_f = (cr_t/100) * eff_rate
            if curr_f > step_f:
                curr_f -= step_f; curr_d += (dist_rem / 100)
                d_pts.append(curr_d); h_pts.append(ac['cruise_alt'])
                f_pts.append(curr_f); statuses.append("Cruising")
            else: statuses.append("ENGINE FAILURE"); break
                
    # 3. Descent
    if "CRASHED" not in statuses:
        is_em = "ENGINE FAILURE" in statuses
        for t in np.linspace(0, de_t, 50):
            curr_d += (de_d / 50); alt = max(0, ac['cruise_alt'] - (t * ac['descent_rate']))
            d_pts.append(curr_d); h_pts.append(alt)
            f_pts.append(curr_f); statuses.append("Landing" if not is_em else "CRASHING")
            if alt <= 0: break

    return d_pts, h_pts, f_pts, statuses, total_f_req

# --- DATA ---
CITIES = {
    "London (LHR)": (51.4700, -0.4543), "New York (JFK)": (40.6413, -73.7781),
    "Dubai (DXB)": (25.2532, 55.3657), "Tokyo (HND)": (35.5494, 139.7798),
    "Sydney (SYD)": (-33.9399, 151.1753), "Lahore (LHE)": (31.5204, 74.3587),
    "Karachi (KHI)": (24.9065, 67.1608)
}

aircraft_data = {
    'Airbus_A320': {
        'name': 'Airbus A320', 'image': 'https://images.unsplash.com/photo-1542296332-2e4473faf563?q=80&w=1000',
        'max_fuel_l': 24210, 'cruise_speed': 281, 'climb_rate': 12.3, 'descent_rate': 7.5, 'cruise_alt': 12000, 'fuel_rate': 0.6
    },
    'Boeing_777': {
        'name': 'Boeing 777', 'image': 'https://images.unsplash.com/photo-1521342475957-8db764a61064?q=80&w=1000',
        'max_fuel_l': 181280, 'cruise_speed': 305, 'climb_rate': 20.2, 'descent_rate': 7.5, 'cruise_alt': 11000, 'fuel_rate': 1.5
    }
}

# --- SIDEBAR ---
st.sidebar.title("🛂 Mission Dispatch")
start_c = st.sidebar.selectbox("Departure", list(CITIES.keys()), index=5)
end_c = st.sidebar.selectbox("Destination", list(CITIES.keys()), index=6)
dist_g = haversine(*CITIES[start_c], *CITIES[end_c])

ac_k = st.sidebar.selectbox("Aircraft", list(aircraft_data.keys()))
ac = aircraft_data[ac_k]

st.sidebar.markdown("### Settings")
f_in = st.sidebar.slider("Fuel (Liters)", 1000, int(ac['max_fuel_l']), 5000)
w_in = st.sidebar.slider("Wind Resistance (%)", 0, 50, 5)
p_in = st.sidebar.slider("Cargo Weight (kg)", 0, 50000, 10000)

d_pts, h_pts, f_pts, statuses, f_req = simulate_flight(f_in, ac_k, w_in, p_in, dist_g)
f_avail = f_in * 0.84

st.sidebar.markdown("---")
st.sidebar.subheader("📋 Co-Pilot Advice")
if f_avail >= f_req:
    st.sidebar.success(f"GO: Trip requires {f_req:.0f}kg. You have {f_avail:.0f}kg. Safe to fly.")
    can_fly = True
elif f_avail > f_req * 0.8:
    st.sidebar.warning(f"RISK: Trip requires {f_req:.0f}kg. You only have {f_avail:.0f}kg. Engine may fail near end.")
    can_fly = False
else:
    st.sidebar.error(f"NO-GO: Massive fuel shortage ({f_req:.0f}kg needed). PLANE WILL CRASH.")
    can_fly = False

take_off = st.sidebar.button("🚀 EXECUTE FLIGHT MISSION")

# --- MAIN UI ---
st.title("🛰️ SkyPredict: Adaptive Command Center")
c_map, c_stats = st.columns([2, 1])

with c_stats:
    st.image(ac['image'], width='stretch')
    st_box = st.empty()
    st.table(pd.DataFrame({
        "Mission Param": ["Distance", "Total Fuel Req", "Cargo Load"],
        "Value": [f"{dist_g/1000:.1f} km", f"{f_req:.0f} kg", f"{p_in} kg"]
    }))

with c_map:
    m1, m2, m3 = st.columns(3)
    p_d, p_a, p_f = m1.empty(), m2.empty(), m3.empty()
    p_g = st.empty()

    if take_off:
        for i in range(len(d_pts)):
            p_d.metric("DISTANCE", f"{d_pts[i]/1000:.1f} km")
            p_a.metric("ALTITUDE", f"{h_pts[i]:.0f} m")
            p_f.metric("FUEL LEFT", f"{f_pts[i]:.0f} kg")
            
            s = statuses[i]
            color = "#ff4b4b" if "CRASH" in s or "FAILURE" in s else "#0078ff"
            st_box.markdown(f'<div class="status-box" style="border-color: {color}; color: {color};">STATUS: {s}</div>', unsafe_allow_html=True)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[p/1000 for p in d_pts], y=h_pts, mode='lines', line=dict(color='rgba(128,128,128,0.2)', width=1)))
            fig.add_trace(go.Scatter(x=[p/1000 for p in d_pts[:i+1]], y=h_pts[:i+1], mode='lines', line=dict(color=color, width=4)))
            icon = "💥" if "CRASH" in s or "FAILURE" in s else "✈️"
            fig.add_trace(go.Scatter(x=[d_pts[i]/1000], y=[h_pts[i]], mode='markers+text', text=[icon], textposition="top center", marker=dict(size=25, color=color)))
            fig.update_layout(title="Live Mission Radar", height=450, showlegend=False, template="none")
            p_g.plotly_chart(fig, width='stretch')
            
            if "CRASH" in s and h_pts[i] <= 0: break
            time.sleep(0.01)
        
        if "CRASH" in statuses[-1] or "FAILURE" in statuses[-1]: st.error("🚨 MISSION LOST")
        else: st.success("🏁 MISSION ACCOMPLISHED")
    else:
        st_box.markdown('<div class="status-box" style="border-color: #555; color: gray;">STATUS: READY</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[p/1000 for p in d_pts], y=h_pts, mode='lines', line=dict(color='rgba(128,128,128,0.3)', width=1)))
        fig.update_layout(title="Route Preview", height=450, showlegend=False, template="none")
        p_g.plotly_chart(fig, width='stretch')
