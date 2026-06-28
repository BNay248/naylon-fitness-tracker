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

    # Inject CSS to force square grid buttons
    st.markdown("""
    <style>
        /* Force the button columns into a grid */
        div[data-testid="column"] > div > div > div > div.stButton > button {
            width: 100% !important;
            aspect-ratio: 1 / 1 !important;
            height: auto !important;
            white-space: normal !important;
            word-break: break-word !important;
            overflow: hidden !important;
            display: -webkit-box !important;
            -webkit-line-clamp: 4 !important;
            -webkit-box-orient: vertical !important;
            font-size: 13px !important;
            font-weight: 600 !important;
            line-height: 1.3 !important;
            padding: 8px !important;
        }

        /* Remove gaps between columns on mobile */
        div[data-testid="columns"] {
            gap: 10px !important;
        }

        /* Make columns not collapse on mobile */
        div[data-testid="column"] {
            min-width: 0 !important;
            flex: 1 1 0% !important;
        }
    </style>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=60)
    def get_foods(uname):
        return db.get_foods_by_user(uname)

    foods = get_foods(username)

    @st.fragment
    def calorie_counter():
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

    calorie_counter()

    if not foods:
        st.info("No foods configured. Add foods on the Foods page.")
    else:
        @st.fragment
        def food_grid():
            cols = st.columns(3)
            for idx, food in enumerate(foods):
                col = cols[idx % 3]
                with col:
                    if st.button(
                        food.get('name', ''),
                        key=f"food_{str(food.get('_id'))}"
                    ):
                        db.add_calorie_entry({
                            'username': username,
                            'food_name': food.get('name'),
                            'calories': int(food.get('calories', 0)),
                            'created_at': datetime.now()
                        })
                        st.rerun(scope="fragment")

        food_grid()

else:
    st.stop()