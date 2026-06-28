import streamlit as st
import streamlit.components.v1 as components
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

    st.info("Foods are shown in the explicit order you set on the Foods page.")
    foods = db.get_foods_by_user(username)

    if not foods:
        st.info("No foods configured. Add foods on the Foods page.")
    else:
        # Handle query param click
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
            st.rerun()

        # Build food buttons as HTML
        food_items = ""
        for food in foods:
            food_id = str(food.get('_id'))
            name = food.get('name', '')
            food_items += f'<a class="food-btn" href="?add_food={food_id}"><span>{name}</span></a>\n'

        num_rows = -(-len(foods) // 3)
        height = num_rows * 175 + 40

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            html, body {{
                background: transparent;
                overflow-x: hidden;
                width: 100%;
                max-width: 100%;
            }}
            .food-grid {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                padding: 4px;
                width: 100%;
                max-width: 100%;
            }}
            .food-btn {{
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
                hyphens: auto;
                line-height: 1.3;
                transition: background-color 0.15s;
                width: 100%;
            }}
            .food-btn:active {{
                background-color: #4a4a6a;
            }}
            .food-btn span {{
                display: -webkit-box;
                -webkit-line-clamp: 4;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }}
        </style>
        </head>
        <body>
            <div class="food-grid">
                {food_items}
            </div>
        </body>
        </html>
        """

        components.html(html, height=height, scrolling=False)

else:
    st.stop()