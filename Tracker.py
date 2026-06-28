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
    st.sidebar.write(f'Welcome *{st.session_state.get("name")}*')
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
        # Build query param click handler
        params = st.query_params
        if "add_food" in params:
            food_id = params["add_food"]
            food = db.get_food_by_id(food_id)
            if food:
                db.add_calorie_entry({
                    'username': username,
                    'food_name': food.get('name'),
                    'calories': int(food.get('calories', 0)),
                    'created_at': datetime.now()
                })
            st.query_params.clear()
            st.rerun()

        # Build HTML grid
        buttons_html = """
        <style>
            .food-grid {
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
                padding: 8px 0;
            }
            .food-btn {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 100%;
                aspect-ratio: 1 / 1;
                background-color: #262730;
                color: white;
                border: 1px solid #555;
                border-radius: 10px;
                text-align: center;
                font-size: 14px;
                font-weight: 600;
                padding: 8px;
                box-sizing: border-box;
                overflow: hidden;
                text-decoration: none;
                cursor: pointer;
                word-break: break-word;
                hyphens: auto;
                line-height: 1.3;
            }
            .food-btn:hover {
                background-color: #3a3a4a;
                border-color: #888;
            }
            .food-btn span {
                display: -webkit-box;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
        </style>
        <div class="food-grid">
        """

        for food in foods:
            food_id = str(food.get('_id'))
            name = food.get('name', '')
            buttons_html += f"""
            <a class="food-btn" href="?add_food={food_id}">
                <span>{name}</span>
            </a>
            """

        buttons_html += "</div>"

        st.markdown(buttons_html, unsafe_allow_html=True)

else:
    st.stop()