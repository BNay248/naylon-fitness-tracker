import streamlit as st
from datetime import datetime, date, time
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

# Page config
st.set_page_config(page_title="Calorie Tracker - Tracker", layout="wide")

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

    st.title("Calorie Tracker")

    midnight = datetime.combine(date.today(), time.min)
    entries = db.get_calorie_entries_by_user_since(username, midnight)
    total = sum([e.get('calories', 0) for e in entries])

    st.metric("Calories Today", f"{total}")

    foods = db.get_foods_by_user(username)

    if not foods:
        st.info("No foods configured. Add foods on the Foods page.")
    else:
        cols = st.columns(2)
        for idx, food in enumerate(foods):
            col = cols[idx % 2]
            label = f"{food.get('name')} ({food.get('calories')} kcal)"
            if col.button(label, key=f"add_{str(food.get('_id'))}"):
                db.add_calorie_entry({
                    'username': username,
                    'food_name': food.get('name'),
                    'calories': int(food.get('calories', 0)),
                    'created_at': datetime.now()
                })
                st.rerun()
else:
    st.stop()