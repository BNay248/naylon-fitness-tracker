import streamlit as st
from bson.objectid import ObjectId
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

st.set_page_config(page_title="Calorie Tracker - Foods", layout="wide")

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

    st.title("Foods")

    with st.form("add_food"):
        name = st.text_input("Food name")
        calories = st.number_input("Calories", min_value=0, step=1)
        submitted = st.form_submit_button("Add Food")
        if submitted:
            if not name:
                st.error("Please enter a food name")
            else:
                db.add_food(username, {'name': name, 'calories': int(calories)})
                st.success("Food added")
                st.rerun()

    st.divider()
    st.subheader("Your foods")
    foods = db.get_foods_by_user(username)
    for idx, f in enumerate(foods, start=1):
        cols = st.columns([4, 1, 1, 1])
        cols[0].write(f"**{f.get('name')}** — {f.get('calories')} kcal")
        current_position = int(f.get('position', idx))
        new_position = cols[1].number_input(
            "Position",
            min_value=1,
            max_value=max(len(foods), 1),
            value=current_position,
            key=f"position_{str(f.get('_id'))}",
        )
        if cols[2].button("Set", key=f"set_pos_{str(f.get('_id'))}"):
            if db.update_food_position(str(f.get('_id')), new_position):
                st.success("Food order updated")
                st.rerun()
            else:
                st.error("Failed to update food position")
        if cols[3].button("Delete", key=f"delete_{str(f.get('_id'))}"):
            db.delete_food(str(f.get('_id')))
            st.rerun()
else:
    st.stop()
