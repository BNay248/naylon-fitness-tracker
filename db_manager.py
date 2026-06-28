from pymongo import MongoClient
from datetime import datetime
from typing import List, Dict, Optional
from bson.objectid import ObjectId

class TrainerDB:
    def __init__(self, connection_string="mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client.workout_platform

    # User methods
    def add_user(self, user_data: Dict) -> str:
        result = self.db.users.insert_one(user_data)
        return str(result.inserted_id)

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        return self.db.users.find_one({"username": username})

    def get_all_users(self) -> List[Dict]:
        return list(self.db.users.find())

    def delete_user_by_username(self, username: str) -> bool:
        result = self.db.users.delete_one({"username": username})
        return result.deleted_count > 0

    def update_user(self, username: str, updates: Dict) -> bool:
        result = self.db.users.update_one({"username": username}, {"$set": updates})
        return result.modified_count > 0

    # Calorie tracker methods
    def add_food(self, username: str, food: Dict) -> str:
        highest = list(
            self.db.calorie_foods.find({'username': username}).sort('position', -1).limit(1)
        )
        next_position = 1
        if highest:
            next_position = int(highest[0].get('position', 0)) + 1

        food_doc = {
            'username': username,
            'name': food.get('name'),
            'calories': int(food.get('calories', 0)),
            'position': next_position,
            'created_at': datetime.now(),
        }
        result = self.db.calorie_foods.insert_one(food_doc)
        return str(result.inserted_id)

    def get_foods_by_user(self, username: str, sort_by: str = 'position', descending: bool = False) -> List[Dict]:
        query = self.db.calorie_foods.find({'username': username})
        if sort_by:
            direction = -1 if descending else 1
            query = query.sort(sort_by, direction)
        return list(query)

    def get_food_by_id(self, food_id: str) -> Optional[Dict]:
        try:
            return self.db.calorie_foods.find_one({'_id': ObjectId(food_id)})
        except:
            return None

    def update_food_position(self, food_id: str, position: int) -> bool:
        try:
            result = self.db.calorie_foods.update_one(
                {'_id': ObjectId(food_id)},
                {'$set': {'position': int(position)}}
            )
            return result.modified_count > 0
        except:
            return False

    def move_food_position(self, username: str, food_id: str, direction: int) -> bool:
        foods = self.get_foods_by_user(username)
        index = next((i for i, f in enumerate(foods) if str(f.get('_id')) == str(food_id)), None)
        if index is None:
            return False

        target_index = index + direction
        if target_index < 0 or target_index >= len(foods):
            return False

        first = foods[index]
        second = foods[target_index]
        first_pos = int(first.get('position', index + 1))
        second_pos = int(second.get('position', target_index + 1))

        if not self.update_food_position(str(first.get('_id')), second_pos):
            return False
        return self.update_food_position(str(second.get('_id')), first_pos)

    def delete_food(self, food_id: str) -> bool:
        try:
            result = self.db.calorie_foods.delete_one({'_id': ObjectId(food_id)})
            return result.deleted_count > 0
        except:
            return False

    def add_calorie_entry(self, entry: Dict) -> str:
        entry_doc = {
            'username': entry.get('username'),
            'food_name': entry.get('food_name'),
            'calories': int(entry.get('calories', 0)),
            'created_at': entry.get('created_at', datetime.now())
        }
        result = self.db.calorie_entries.insert_one(entry_doc)
        return str(result.inserted_id)

    def get_calorie_entries_by_user_since(self, username: str, since: datetime) -> List[Dict]:
        return list(self.db.calorie_entries.find({'username': username, 'created_at': {'$gte': since}}))

    def get_calorie_entries_by_user(self, username: str) -> List[Dict]:
        return list(self.db.calorie_entries.find({'username': username}))

    def aggregate_daily_totals(self, username: str):
        pipeline = [
            {'$match': {'username': username}},
            {'$project': {'calories': 1, 'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}}}},
            {'$group': {'_id': '$date', 'total': {'$sum': '$calories'}}},
            {'$sort': {'_id': 1}}
        ]
        return list(self.db.calorie_entries.aggregate(pipeline))
