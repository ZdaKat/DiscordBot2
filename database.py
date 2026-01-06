import os
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

class MongoDB:
    def __init__(self):
        """Inicializa la conexión a MongoDB Atlas"""
        self.connection_string = os.getenv("MONGODB_URI")
        if not self.connection_string:
            raise ValueError("MONGODB_URI no encontrada en las variables de entorno")
        
        self.client = MongoClient(self.connection_string)
        self.db = self.client.discord_bot  # Base de datos
        self.setup_collections()
        
    def setup_collections(self):
        """Configura las colecciones y índices"""
        # Colección de usuarios
        self.users = self.db.users
        
        # Colección de inventarios
        self.inventories = self.db.inventories
        
        # Colección de items globales
        self.items = self.db.items
        
        # Crear índices para mejor rendimiento
        self.users.create_index("discord_id", unique=True)
        self.inventories.create_index([("user_id", 1), ("item_id", 1)], unique=True)
        self.items.create_index("name_lower", unique=True)
    
    def get_or_create_user(self, discord_id: int, username: str):
        """Obtiene o crea un usuario en la base de datos"""
        return self.users.find_one_and_update(
            {"discord_id": str(discord_id)},
            {"$setOnInsert": {
                "discord_id": str(discord_id),
                "username": username,
                "created_at": datetime.utcnow()
            }},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
    
    def add_item_to_inventory(self, discord_id: int, item_name: str, quantity: int = 1):
        """Añade un item al inventario del usuario"""
        user = self.get_or_create_user(discord_id, "Unknown")
        
        # Buscar o crear el item global
        item = self.items.find_one_and_update(
            {"name_lower": item_name.lower()},
            {"$setOnInsert": {
                "name": item_name,
                "name_lower": item_name.lower(),
                "created_at": datetime.utcnow(),
                "created_by": str(discord_id)
            }},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        
        # Actualizar inventario
        result = self.inventories.update_one(
            {
                "user_id": str(discord_id),
                "item_id": str(item["_id"])
            },
            {
                "$inc": {"quantity": quantity},
                "$setOnInsert": {
                    "user_id": str(discord_id),
                    "item_id": str(item["_id"]),
                    "item_name": item_name,
                    "added_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        return {
            "user": user,
            "item": item,
            "operation": "added",
            "quantity": quantity
        }
    
    def remove_item_from_inventory(self, discord_id: int, item_identifier: str, quantity: int = 1):
        """Remueve items del inventario"""
        user_id = str(discord_id)
        
        # Buscar el item (por ID o nombre)
        item = None
        if item_identifier.isdigit():
            # Buscar por ID de MongoDB
            from bson import ObjectId
            try:
                item = self.items.find_one({"_id": ObjectId(item_identifier)})
            except:
                item = None
        else:
            # Buscar por nombre
            item = self.items.find_one({"name_lower": item_identifier.lower()})
        
        if not item:
            return {"error": "Item no encontrado"}
        
        # Verificar si el usuario tiene el item
        inventory_item = self.inventories.find_one({
            "user_id": user_id,
            "item_id": str(item["_id"])
        })
        
        if not inventory_item:
            return {"error": "No tienes este item"}
        
        # Verificar cantidad
        if inventory_item["quantity"] < quantity:
            return {"error": f"No tienes suficientes. Tienes: {inventory_item['quantity']}"}
        
        # Actualizar o eliminar
        new_quantity = inventory_item["quantity"] - quantity
        
        if new_quantity <= 0:
            # Eliminar del inventario
            self.inventories.delete_one({
                "user_id": user_id,
                "item_id": str(item["_id"])
            })
            result = "eliminado"
        else:
            # Actualizar cantidad
            self.inventories.update_one(
                {
                    "user_id": user_id,
                    "item_id": str(item["_id"])
                },
                {"$set": {"quantity": new_quantity}}
            )
            result = f"actualizado a {new_quantity}"
        
        return {
            "success": True,
            "item": item,
            "quantity_removed": quantity,
            "result": result
        }
    
    def get_user_inventory(self, discord_id: int, page: int = 1, limit: int = 10):
        """Obtiene el inventario de un usuario con paginación"""
        user_id = str(discord_id)
        
        # Calcular skip para paginación
        skip = (page - 1) * limit
        
        # Contar total
        total_items = self.inventories.count_documents({"user_id": user_id})
        total_pages = (total_items + limit - 1) // limit
        
        # Obtener items
        inventory_items = list(self.inventories.find(
            {"user_id": user_id}
        ).skip(skip).limit(limit).sort("item_name", 1))
        
        # Obtener detalles de los items
        items_with_details = []
        for inv_item in inventory_items:
            item = self.items.find_one({"_id": ObjectId(inv_item["item_id"])})
            items_with_details.append({
                "inventory_data": inv_item,
                "item_details": item
            })
        
        return {
            "items": items_with_details,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit
        }
    
    def search_items(self, search_term: str, limit: int = 10):
        """Busca items por nombre"""
        return list(self.items.find(
            {"name_lower": {"$regex": search_term.lower()}}
        ).limit(limit).sort("name", 1))
    
    def get_item_info(self, item_identifier: str):
        """Obtiene información detallada de un item"""
        from bson import ObjectId
        if item_identifier.isdigit():
            try:
                return self.items.find_one({"_id": ObjectId(item_identifier)})
            except:
                return None
        else:
            return self.items.find_one({"name_lower": item_identifier.lower()})
    
    def get_user_stats(self, discord_id: int):
        """Obtiene estadísticas del usuario"""
        user_id = str(discord_id)
        
        # Items únicos
        unique_items = self.inventories.count_documents({"user_id": user_id})
        
        # Total de unidades
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
        ]
        result = list(self.inventories.aggregate(pipeline))
        total_units = result[0]["total"] if result else 0
        
        # Item más común
        most_common = self.inventories.find_one(
            {"user_id": user_id},
            sort=[("quantity", -1)]
        )
        
        return {
            "unique_items": unique_items,
            "total_units": total_units,
            "most_common": most_common
        }

# Instancia global de la base de datos
db = MongoDB()
