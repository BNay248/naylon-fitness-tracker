import streamlit as st

st.set_page_config(page_title="Calorie Tracker", layout="wide")

st.title("Calorie Tracker")

st.write("This app has three pages: Tracker, Foods, and History.")
st.write("Use the Streamlit " + "Pages" + " sidebar to select a page.")

st.info("If you don't see pages, run `streamlit run CALORIES/app.py` from the workspace root.")
