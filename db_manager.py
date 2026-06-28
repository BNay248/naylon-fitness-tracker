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
        food_doc = {'username': username, 'name': food.get('name'), 'calories': int(food.get('calories', 0))}
        result = self.db.calorie_foods.insert_one(food_doc)
        return str(result.inserted_id)

    def get_foods_by_user(self, username: str) -> List[Dict]:
        return list(self.db.calorie_foods.find({'username': username}))

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
