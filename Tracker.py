import streamlit as st
from datetime import datetime, date, time
from db_manager import TrainerDB
from auth_helper import load_config, create_authenticator, render_login_and_registration

st.set_page_config(page_title="Calorie Tracker - Tracker", layout="wide")

config = load_config()
db = TrainerDB()
authenticator = create_authenticator(config, db)
render_login_and_registration(authenticator, config, db)

if st.session_state.get("authentication_status"):
    authenticator.logout(location='sidebar')
    st.sidebar.write(f'Welcome *{st.session_state.get("name")}*')
    username = st.session_state.get("username")
    if not username:
        st.error("Session missing username — please log out and log in again.")
        st.stop()

    st.title("Calorie Tracker")

    @st.cache_data(ttl=60)
    def get_foods(uname):
        return db.get_foods_by_user(uname)

    foods = get_foods(username)

    @st.fragment
    def main_page():
        # Handle query param click inside fragment
        params = st.query_params
        if "add_food" in params:
            food_id = params.get("add_food")
            if isinstance(food_id, (list, tuple)):
                food_id = food_id[0] if food_id else None
            food = next((f for f in foods if str(f.get('_id')) == str(food_id)), None)
            if food:
                db.add_calorie_entry({
                    'username': username,
                    'food_name': food.get('name'),
                    'calories': int(food.get('calories', 0)),
                    'created_at': datetime.now()
                })
            st.query_params.clear()

        # Calorie counter + undo
        midnight = datetime.combine(date.today(), time.min)
        entries = db.get_calorie_entries_by_user_since(username, midnight) # type: ignore
        total = sum([e.get('calories', 0) for e in entries])

        col1, col2 = st.columns([3, 1])
        with col1:
            st.metric("Calories Today", f"{total}")
        with col2:
            st.write("")
            if entries:
                if st.button("↩️ Undo"):
                    latest = max(entries, key=lambda e: e.get('created_at', datetime.min))
                    db.delete_calorie_entry(str(latest['_id']))
                    st.rerun(scope="fragment")

        # Pure HTML grid - no iframe, just markdown
        if not foods:
            st.info("No foods configured. Add foods on the Foods page.")
            return

        food_items = ""
        for food in foods:
            food_id = str(food.get('_id'))
            name = food.get('name', '')
            food_items += f"""
            <a href="?add_food={food_id}" style="
                display: flex;
                align-items: center;
                justify-content: center;
                aspect-ratio: 1 / 1;
                background-color: #262730;
                color: white;
                border: 1px solid #555;
                border-radius: 10px;
                text-align: center;
                font-size: 13px;
                font-weight: 600;
                padding: 8px;
                overflow: hidden;
                text-decoration: none;
                cursor: pointer;
                word-break: break-word;
                line-height: 1.3;
            "><span style="
                display: -webkit-box;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                overflow: hidden;
            ">{name}</span></a>
            """

        st.markdown(f"""
        <div style="
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            padding: 4px;
            width: 100%;
        ">
            {food_items}
        </div>
        """, unsafe_allow_html=True)

    main_page()

else:
    st.stop()