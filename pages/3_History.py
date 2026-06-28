import streamlit as st
import pandas as pd
import altair as alt
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

st.set_page_config(page_title="Calorie Tracker - History", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)

if st.session_state.get("authentication_status"):
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state.get("name") }*')
    username = st.session_state.get("username")
    if not username:
        st.error("Session missing username — please log out and log in again.")
        st.stop()

    st.title("History")

    rows = db.aggregate_daily_totals(username)
    if not rows:
        st.info("No data yet")
    else:
        df = pd.DataFrame([{'date': r['_id'], 'calories': r['total']} for r in rows])
        df['date'] = pd.to_datetime(df['date'])

        chart = alt.Chart(df).mark_bar().encode(x='date:T', y='calories:Q')
        st.altair_chart(chart, use_container_width=True)
else:
    st.stop()
