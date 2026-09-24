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

    # Nutrition tracker methods
    def add_food(self, username: str, food: Dict) -> str:
        last_food_cursor = self.db.foods.find({'username': username}).sort('position', -1).limit(1)
        last_food = next(last_food_cursor, None)
        max_position = last_food.get('position', 0) if last_food else 0
        food_doc = {
            'username': username,
            'name': food.get('name'),
            'calories': int(food.get('calories', 0)),
            'protein': int(food.get('protein', 0)),
            'created_at': datetime.now(),
            'position': max_position + 1,
        }
        result = self.db.foods.insert_one(food_doc)
        return str(result.inserted_id)

    def get_foods_by_user(self, username: str, sort_by: str = 'position', descending: bool = False) -> List[Dict]:
        query = self.db.foods.find({'username': username})
        direction = -1 if descending else 1
        query = query.sort(sort_by, direction)
        foods = list(query)
        if sort_by == 'position' and any('position' not in f for f in foods):
            self.normalize_food_positions(username)
            foods = list(self.db.foods.find({'username': username}).sort(sort_by, direction))
        return foods

    def delete_food(self, food_id: str) -> bool:
        try:
            food = self.db.foods.find_one({'_id': ObjectId(food_id)})
            result = self.db.foods.delete_one({'_id': ObjectId(food_id)})
            if result.deleted_count > 0 and food:
                self.normalize_food_positions(food['username'])
                return True
            return False
        except:
            return False

    def update_food_position(self, food_id: str, new_position: int) -> bool:
        try:
            food = self.db.foods.find_one({'_id': ObjectId(food_id)})
            if not food:
                return False
            username = food['username']
            current_position = int(food.get('position', 0))
            total = self.db.foods.count_documents({'username': username})
            new_position = max(1, min(int(new_position), total))
            if new_position == current_position:
                return True
            if new_position < current_position:
                self.db.foods.update_many(
                    {'username': username, 'position': {'$gte': new_position, '$lt': current_position}},
                    {'$inc': {'position': 1}}
                )
            else:
                self.db.foods.update_many(
                    {'username': username, 'position': {'$gt': current_position, '$lte': new_position}},
                    {'$inc': {'position': -1}}
                )
            self.db.foods.update_one({'_id': ObjectId(food_id)}, {'$set': {'position': new_position}})
            return True
        except:
            return False

    def normalize_food_positions(self, username: str) -> None:
        foods = list(self.db.foods.find({'username': username}).sort('position', 1))
        for index, food in enumerate(foods, start=1):
            if food.get('position') != index:
                self.db.foods.update_one(
                    {'_id': food['_id']},
                    {'$set': {'position': index}}
                )

    def add_nutrition_entry(self, entry: Dict) -> str:
        client_id = entry.get('client_id')
        if client_id:
            existing = self.db.nutrition_entries.find_one({'username': entry.get('username'), 'client_id': client_id})
            if existing:
                return str(existing['_id'])
        entry_doc = {
            'username': entry.get('username'),
            'food_name': entry.get('food_name'),
            'calories': int(entry.get('calories', 0)),
            'protein': int(entry.get('protein', 0)),
            'created_at': entry.get('created_at', datetime.now()),
            'client_id': client_id
        }
        result = self.db.nutrition_entries.insert_one(entry_doc)
        return str(result.inserted_id)

    def get_nutrition_entries_by_user_since(self, username: str, since: datetime) -> List[Dict]:
        return list(self.db.nutrition_entries.find({'username': username, 'created_at': {'$gte': since}}))

    def get_nutrition_entries_by_user(self, username: str) -> List[Dict]:
        return list(self.db.nutrition_entries.find({'username': username}))

    def aggregate_daily_totals(self, username: str):
        pipeline = [
            {'$match': {'username': username}},
            {'$project': {'calories': 1, 'protein': 1, 'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$created_at'}}}},
            {'$group': {'_id': '$date', 'total_calories': {'$sum': '$calories'}, 'total_protein': {'$sum': '$protein'}}},
            {'$sort': {'_id': 1}}
        ]
        return list(self.db.nutrition_entries.aggregate(pipeline))

    def delete_nutrition_entry(self, entry_id: str) -> bool:
        try:
            result = self.db.nutrition_entries.delete_one({"_id": ObjectId(entry_id)})
            return result.deleted_count > 0
        except:
            return False