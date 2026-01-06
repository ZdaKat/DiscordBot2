import discord
from discord.ext import commands, tasks
from pymongo import MongoClient, ReturnDocument
import os
import random
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# ========== CONFIGURACIÓN INICIAL ==========
# Cargar variables de entorno
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="t!", intents=intents, help_command=None)

# ========== ENUMS Y CLASES ==========
class CharacterClass(Enum):
    WARRIOR = "Guerrero"
    MAGE = "Mago"
    ARCHER = "Arquero"
    ROGUE = "Pícaro"
    UNIQUE = "Único"
    SPECIAL = "Especial"
    NORMAL = "Normal"
    BASIC = "Básico"

class Rarity(Enum):
    S = "S - Legendario"
    A = "A - Épico"
    B = "B - Raro"
    C = "C - Común"
    STARTER = "Inicial"

class MonsterType(Enum):
    INSTAKILL = "Instakill"
    MUTER = "Muteador"
    WILD_POKEMON = "Pokémon Salvaje"
    LAG_TYPE = "Tipo del Lag"
    FAST_TYPE = "Tipo Veloz"
    SANDY_GATE = "Puerta de Sandy"
    SLEEPY_TYPE = "Tipo con Sueño"
    DEAD_USER = "User Muerto"
    FEARFUL_TYPE = "Tipo Temeroso"

class BattleEffect(Enum):
    NONE = "Sin efecto"
    INSTAKILL = "¡Instakill!"
    MUTE = "Silenciado"
    LAG = "Lento (ataca al final)"
    FAST = "Rápido (ataca primero)"
    SLEEP = "Duerme (ganas automático)"
    FEAR = "Teme (ganas automático)"

# ========== CLASES DE DATOS ==========
class Character:
    def __init__(self, name: str, rarity: Rarity, max_hp: int, min_damage: int, max_damage: int, 
                 special_effect: str = None, effect_chance: float = 0.0):
        self.name = name
        self.rarity = rarity
        self.max_hp = max_hp
        self.current_hp = max_hp
        self.min_damage = min_damage
        self.max_damage = max_damage
        self.special_effect = special_effect
        self.effect_chance = effect_chance
        self.unlocked = False
        self.created_at = datetime.utcnow()

class Monster:
    def __init__(self, name: str, monster_type: MonsterType, hp: int, min_damage: int, max_damage: int, 
                 coins_reward: int, effect: BattleEffect = BattleEffect.NONE, effect_chance: float = 0.0):
        self.name = name
        self.monster_type = monster_type
        self.hp = hp
        self.current_hp = hp
        self.min_damage = min_damage
        self.max_damage = max_damage
        self.coins_reward = coins_reward
        self.effect = effect
        self.effect_chance = effect_chance

# ========== CONFIGURACIÓN DEL JUEGO ==========
# PERSONAJES INICIALES (Starter)
STARTER_CHARACTERS = {
    "Guy": Character("Guy", Rarity.STARTER, 30, 5, 10),
    "Mage": Character("Mage", Rarity.STARTER, 25, 8, 12),
    "Archer": Character("Archer", Rarity.STARTER, 28, 6, 9),
    "Rogue": Character("Rogue", Rarity.STARTER, 26, 7, 11)
}

# PERSONAJES RAROS S
S_CHARACTERS = {
    "Chocolat": Character("Chocolat", Rarity.S, 50, 20, 40, "Puede generar una tirada al ganar (5%)", 0.05),
    "Crow": Character("Crow", Rarity.S, 60, 1, 100, "Recupera 10 de vida al ganar", 1.0),
    "Tupper": Character("Tupper", Rarity.S, 50, 30, 30, "Genera bonus de 10 monedas por victoria", 1.0)
}

# PERSONAJES ÉPICOS A
A_CHARACTERS = {
    "Nekotina": Character("Nekotina", Rarity.A, 45, 10, 25),
    "Shelly": Character("Shelly", Rarity.A, 30, 12, 24, "Recupera 5 de vida al ganar", 1.0),
    "Panqueque": Character("Panqueque", Rarity.A, 30, 15, 30, "Devuelve la mitad del daño", 1.0),
    "Roca (Temporada 1)": Character("Roca (Temporada 1)", Rarity.A, 10, 1, 100, "Puede hacer instakill si te matan (50%)", 0.5),
    "Sandy": Character("Sandy", Rarity.A, 70, 1, 30, "Puede poner protección que evita cualquier ataque (20%)", 0.2),
    "Emy": Character("Emy", Rarity.A, 50, 50, 50, "Puede quitar 15 de vida y recuperarse eso (30%)", 0.3),
    "Tipo de las barras": Character("Tipo de las barras", Rarity.A, 30, 15, 30, "Pone barras haciendo que ataques de 5 o menos daño hagan 0", 1.0)
}

# PERSONAJES RAROS B
B_CHARACTERS = {
    "Gold": Character("Gold", Rarity.B, 30, 5, 30, "Puede encontrar monedas 5-10", 1.0),
    "Slider (el mango)": Character("Slider (el mango)", Rarity.B, 35, 5, 30, "Puede encontrar monedas 5", 1.0),
    "Tick": Character("Tick", Rarity.B, 15, 50, 50, "Puede encontrar monedas 1-15", 1.0),
    "Eveline": Character("Eveline", Rarity.B, 45, 10, 10, "Puede encontrar tiradas (3%)", 0.03),
    "Sandichu": Character("Sandichu", Rarity.B, 25, 5, 50, "Puede recuperar 10 vida (10%)", 0.1),
    "Zekex": Character("Zekex", Rarity.B, 30, 15, 15, "Puede recuperar 5 vida (20%)", 0.2),
    "Zirconia": Character("Zirconia", Rarity.B, 40, 8, 48, "Puede duplicar ataque (35%)", 0.35),
    "Tomi": Character("Tomi", Rarity.B, 40, 5, 50, "Puede duplicar ataque (35%)", 0.35),
    "Nagito": Character("Nagito", Rarity.B, 30, 5, 15, "Puede encontrar monedas 5-30", 1.0),
    "Error": Character("Error", Rarity.B, 1, 9999, 9999, "Puede aumentarse 30 vida (6%)", 0.06)
}

# PERSONAJES COMUNES C
C_CHARACTERS = {
    "Mafia guy": Character("Mafia guy", Rarity.C, 30, 10, 10),
    "Komekko": Character("Komekko", Rarity.C, 25, 10, 25),
    "Ghosty": Character("Ghosty", Rarity.C, 10, 15, 30),
    "Senri": Character("Senri", Rarity.C, 30, 14, 34),
    "Cirno": Character("Cirno", Rarity.C, 50, 9, 9),
    "GatoEmote": Character("GatoEmote", Rarity.C, 30, 5, 15),
    "Sandy clon": Character("Sandy clon", Rarity.C, 30, 1, 30),
    "Kumo": Character("Kumo", Rarity.C, 30, 8, 8),
    "Celia": Character("Celia", Rarity.C, 30, 15, 15),
    "Lillie": Character("Lillie", Rarity.C, 25, 25, 25),
    "Guy": Character("Guy", Rarity.C, 30, 5, 10),
    "Penny": Character("Penny", Rarity.C, 30, 15, 30),
    "Kris": Character("Kris", Rarity.C, 30, 20, 20),
    "Bea": Character("Bea", Rarity.C, 30, 10, 10),
    "Color-chan": Character("Color-chan", Rarity.C, 30, 10, 15)
}

# COMBINAR TODOS LOS PERSONAJES
ALL_CHARACTERS = {**STARTER_CHARACTERS, **S_CHARACTERS, **A_CHARACTERS, **B_CHARACTERS, **C_CHARACTERS}

# Probabilidades de obtener personajes en daily
CHARACTER_PROBABILITIES = {
    "S": 3.0,    # 3%
    "A": 7.0,    # 7%
    "B": 10.0,   # 10%
    "C": 20.0,   # 20%
    "resources": 60.0  # 60%
}

# Probabilidades de aparición de monstruos (basado en tus números)
MONSTER_PROBABILITIES = {
    "Guión": 0.001,      # 0.1%
    "Muteador": 0.999,   # 99.9%
    "Pokémon salvaje": 4.0,      # 400%
    "Tipo del lag": 10.0,        # 1000%
    "Tipo veloz": 10.0,          # 1000%
    "Puerta de Sandy": 15.0,     # 1500%
    "Tipo con sueño": 20.0,      # 2000%
    "User muerto": 20.0,         # 2000%
    "Tipo temeroso": 20.0        # 2000%
}

# Normalizar probabilidades para que sumen 100%
total_prob = sum(MONSTER_PROBABILITIES.values())
NORMALIZED_MONSTER_PROBABILITIES = {name: prob/total_prob*100 for name, prob in MONSTER_PROBABILITIES.items()}

MONSTERS = {
    "Guión": Monster("Guión", MonsterType.INSTAKILL, 1, 9999, 9999, 1000, BattleEffect.INSTAKILL, 1.0),
    "Muteador": Monster("Muteador", MonsterType.MUTER, 50, 5, 10, 100, BattleEffect.MUTE, 0.3),
    "Pokémon salvaje": Monster("Pokémon salvaje", MonsterType.WILD_POKEMON, 30, 5, 8, 50),
    "Tipo del lag": Monster("Tipo del lag", MonsterType.LAG_TYPE, 20, 5, 5, 30, BattleEffect.LAG, 0.5),
    "Tipo veloz": Monster("Tipo veloz", MonsterType.FAST_TYPE, 20, 5, 5, 30, BattleEffect.FAST, 0.5),
    "Puerta de Sandy": Monster("Puerta de Sandy", MonsterType.SANDY_GATE, 50, 1, 2, 40),
    "Tipo con sueño": Monster("Tipo con sueño", MonsterType.SLEEPY_TYPE, 20, 1, 5, 25, BattleEffect.SLEEP, 0.4),
    "User muerto": Monster("User muerto", MonsterType.DEAD_USER, 8, 1, 5, 10),
    "Tipo temeroso": Monster("Tipo temeroso", MonsterType.FEARFUL_TYPE, 8, 1, 5, 25, BattleEffect.FEAR, 0.4)
}

# ========== BASE DE DATOS DEL JUEGO ==========
class GameDatabase:
    def __init__(self):
        """Inicializa la conexión a MongoDB Atlas para el juego"""
        if not MONGODB_URI:
            print("⚠️ MONGODB_URI no encontrada en .env - Sistema de juego desactivado")
            self.client = None
            self.db = None
            return
        
        print("🔗 Conectando a MongoDB Atlas para el juego...")
        try:
            self.client = MongoClient(MONGODB_URI)
            # Verificar conexión
            self.client.admin.command('ping')
            self.db = self.client.discord_game
            self.players = self.db.players
            self.characters = self.db.characters
            self.monsters = self.db.monsters
            self.items = self.db.items
            self.battles = self.db.battles
            
            # Inicializar personajes en la base de datos
            self.initialize_characters()
            print("✅ Conectado a MongoDB Atlas para el juego")
        except Exception as e:
            print(f"❌ Error al conectar a MongoDB: {e}")
            self.client = None
            self.db = None
    
    def initialize_characters(self):
        """Inicializa todos los personajes en la base de datos"""
        for name, char in ALL_CHARACTERS.items():
            char_data = {
                "name": char.name,
                "rarity": char.rarity.value,
                "max_hp": char.max_hp,
                "min_damage": char.min_damage,
                "max_damage": char.max_damage,
                "special_effect": char.special_effect,
                "effect_chance": char.effect_chance,
                "category": char.rarity.name,
                "is_starter": name in STARTER_CHARACTERS,
                "created_at": datetime.utcnow()
            }
            
            # Insertar si no existe
            self.characters.update_one(
                {"name": name},
                {"$setOnInsert": char_data},
                upsert=True
            )
    
    # ========== MÉTODOS DE JUGADOR ==========
    def create_player(self, discord_id: int, username: str, character_name: str) -> Optional[Dict]:
        if character_name not in STARTER_CHARACTERS:
            return None
        
        character = STARTER_CHARACTERS[character_name]
        
        # Crear inventario de personajes desbloqueados
        unlocked_characters = [{
            "name": character.name,
            "rarity": character.rarity.value,
            "max_hp": character.max_hp,
            "current_hp": character.current_hp,
            "min_damage": character.min_damage,
            "max_damage": character.max_damage,
            "special_effect": character.special_effect,
            "effect_chance": character.effect_chance,
            "is_current": True,
            "unlocked_at": datetime.utcnow()
        }]
        
        player_data = {
            "discord_id": str(discord_id),
            "username": username,
            "current_character": character.name,
            "unlocked_characters": unlocked_characters,
            "character_stats": {
                "name": character.name,
                "max_hp": character.max_hp,
                "current_hp": character.current_hp,
                "min_damage": character.min_damage,
                "max_damage": character.max_damage,
                "special_effect": character.special_effect,
                "effect_chance": character.effect_chance
            },
            "coins": 0,
            "inventory": [],
            "daily_uses_today": 0,
            "sdaily_used_today": False,
            "last_daily_reset": datetime.utcnow(),
            "last_sdaily_reset": datetime.utcnow(),
            "total_damage_dealt": 0,
            "monsters_defeated": 0,
            "characters_unlocked": 1,
            "is_dead": False,
            "death_time": None,
            "last_full_recovery": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        }
        
        return self.players.insert_one(player_data)
    
    def get_player(self, discord_id: int) -> Optional[Dict]:
        return self.players.find_one({"discord_id": str(discord_id)})
    
    def update_player(self, discord_id: int, update_data: Dict) -> Optional[Dict]:
        update_data["last_active"] = datetime.utcnow()
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER
        )
    
    def unlock_character(self, discord_id: int, character_name: str) -> Optional[Dict]:
        """Desbloquea un nuevo personaje para el jugador"""
        player = self.get_player(discord_id)
        if not player:
            return None
        
        # Verificar si el personaje existe
        if character_name not in ALL_CHARACTERS:
            return None
        
        # Verificar si ya tiene el personaje
        for char in player.get("unlocked_characters", []):
            if char["name"] == character_name:
                return player  # Ya lo tiene
        
        character = ALL_CHARACTERS[character_name]
        
        new_character = {
            "name": character.name,
            "rarity": character.rarity.value,
            "max_hp": character.max_hp,
            "current_hp": character.max_hp,  # Empieza con vida completa
            "min_damage": character.min_damage,
            "max_damage": character.max_damage,
            "special_effect": character.special_effect,
            "effect_chance": character.effect_chance,
            "is_current": False,
            "unlocked_at": datetime.utcnow()
        }
        
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {
                "$push": {"unlocked_characters": new_character},
                "$inc": {"characters_unlocked": 1}
            },
            return_document=ReturnDocument.AFTER
        )
    
    def switch_character(self, discord_id: int, character_name: str) -> Optional[Dict]:
        """Cambia el personaje actual del jugador"""
        player = self.get_player(discord_id)
        if not player:
            return None
        
        # Buscar el personaje en los desbloqueados
        target_char = None
        for char in player.get("unlocked_characters", []):
            if char["name"] == character_name:
                target_char = char
                break
        
        if not target_char:
            return None
        
        # Actualizar todos los personajes para marcar solo el actual
        updated_chars = []
        for char in player.get("unlocked_characters", []):
            char_copy = char.copy()
            char_copy["is_current"] = (char["name"] == character_name)
            updated_chars.append(char_copy)
        
        # Actualizar stats del personaje actual
        character_stats = {
            "name": target_char["name"],
            "max_hp": target_char["max_hp"],
            "current_hp": target_char["current_hp"],
            "min_damage": target_char["min_damage"],
            "max_damage": target_char["max_damage"],
            "special_effect": target_char["special_effect"],
            "effect_chance": target_char["effect_chance"]
        }
        
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {
                "$set": {
                    "unlocked_characters": updated_chars,
                    "current_character": character_name,
                    "character_stats": character_stats
                }
            },
            return_document=ReturnDocument.AFTER
        )
    
    def heal_character(self, discord_id: int, character_name: str = None) -> Optional[Dict]:
        """Cura un personaje específico o el actual"""
        player = self.get_player(discord_id)
        if not player:
            return None
        
        if character_name:
            # Curar personaje específico
            updated_chars = []
            for char in player.get("unlocked_characters", []):
                char_copy = char.copy()
                if char["name"] == character_name:
                    char_copy["current_hp"] = char["max_hp"]
                updated_chars.append(char_copy)
            
            return self.players.find_one_and_update(
                {"discord_id": str(discord_id)},
                {"$set": {"unlocked_characters": updated_chars}},
                return_document=ReturnDocument.AFTER
            )
        else:
            # Curar personaje actual
            current_char = player.get("character_stats", {})
            if current_char:
                new_hp = current_char["max_hp"]
                
                # Actualizar en unlocked_characters
                updated_chars = []
                for char in player.get("unlocked_characters", []):
                    char_copy = char.copy()
                    if char["name"] == player["current_character"]:
                        char_copy["current_hp"] = new_hp
                    updated_chars.append(char_copy)
                
                return self.players.find_one_and_update(
                    {"discord_id": str(discord_id)},
                    {
                        "$set": {
                            "unlocked_characters": updated_chars,
                            "character_stats.current_hp": new_hp
                        }
                    },
                    return_document=ReturnDocument.AFTER
                )
        
        return player
    
    def kill_player(self, discord_id: int) -> Optional[Dict]:
        """Marca al jugador como muerto"""
        return self.update_player(discord_id, {
            "is_dead": True,
            "death_time": datetime.utcnow(),
            "character_stats.current_hp": 0
        })
    
    def revive_player(self, discord_id: int) -> Optional[Dict]:
        """Revive al jugador y cura a todos sus personajes"""
        player = self.get_player(discord_id)
        if not player:
            return None
        
        # Curar todos los personajes
        updated_chars = []
        for char in player.get("unlocked_characters", []):
            char_copy = char.copy()
            char_copy["current_hp"] = char["max_hp"]
            updated_chars.append(char_copy)
        
        # Curar personaje actual
        current_char_stats = player.get("character_stats", {})
        if current_char_stats:
            current_char_stats["current_hp"] = current_char_stats["max_hp"]
        
        return self.update_player(discord_id, {
            "is_dead": False,
            "death_time": None,
            "unlocked_characters": updated_chars,
            "character_stats": current_char_stats,
            "last_full_recovery": datetime.utcnow()
        })
    
    def add_coins(self, discord_id: int, amount: int) -> Optional[Dict]:
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {"$inc": {"coins": amount}},
            return_document=ReturnDocument.AFTER
        )
    
    def heal_player(self, discord_id: int, amount: int) -> Optional[Dict]:
        player = self.get_player(discord_id)
        if not player:
            return None
        
        current_hp = player["character_stats"]["current_hp"]
        max_hp = player["character_stats"]["max_hp"]
        new_hp = min(current_hp + amount, max_hp)
        
        # Actualizar en unlocked_characters
        updated_chars = []
        for char in player.get("unlocked_characters", []):
            char_copy = char.copy()
            if char["name"] == player["current_character"]:
                char_copy["current_hp"] = new_hp
            updated_chars.append(char_copy)
        
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {
                "$set": {
                    "unlocked_characters": updated_chars,
                    "character_stats.current_hp": new_hp
                }
            },
            return_document=ReturnDocument.AFTER
        )
    
    def damage_player(self, discord_id: int, amount: int) -> Optional[Dict]:
        player = self.get_player(discord_id)
        if not player:
            return None
        
        current_hp = player["character_stats"]["current_hp"]
        new_hp = max(current_hp - amount, 0)
        
        # Actualizar en unlocked_characters
        updated_chars = []
        for char in player.get("unlocked_characters", []):
            char_copy = char.copy()
            if char["name"] == player["current_character"]:
                char_copy["current_hp"] = new_hp
            updated_chars.append(char_copy)
        
        update_data = {
            "unlocked_characters": updated_chars,
            "character_stats.current_hp": new_hp
        }
        
        # Si la vida llega a 0, el jugador muere
        if new_hp <= 0:
            update_data.update({
                "is_dead": True,
                "death_time": datetime.utcnow()
            })
        
        return self.players.find_one_and_update(
            {"discord_id": str(discord_id)},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER
        )
    
    def reset_daily_uses(self):
        """Resetea los usos diarios para todos los jugadores"""
        now = datetime.utcnow()
        self.players.update_many(
            {},
            {"$set": {
                "daily_uses_today": 0,
                "sdaily_used_today": False,
                "last_daily_reset": now,
                "last_sdaily_reset": now
            }}
        )
    
    def check_and_revive_dead_players(self):
        """Revive a los jugadores muertos si han pasado 48 horas"""
        now = datetime.utcnow()
        two_days_ago = now - timedelta(days=2)
        
        dead_players = list(self.players.find({
            "is_dead": True,
            "death_time": {"$lte": two_days_ago}
        }))
        
        for player in dead_players:
            self.revive_player(int(player["discord_id"]))
        
        return len(dead_players)
    
    def full_recovery_all_players(self):
        """Cura completamente a todos los jugadores vivos"""
        now = datetime.utcnow()
        
        # Para jugadores vivos
        players = list(self.players.find({"is_dead": False}))
        
        for player in players:
            self.revive_player(int(player["discord_id"]))
        
        return len(players)
    
    # ========== MÉTODOS DE BATALLAS ==========
    def log_battle(self, player_id: int, monster_name: str, result: str, damage_dealt: int, coins_earned: int, effect: str = None):
        battle_data = {
            "player_id": str(player_id),
            "monster_name": monster_name,
            "result": result,
            "damage_dealt": damage_dealt,
            "coins_earned": coins_earned,
            "effect_used": effect,
            "battle_date": datetime.utcnow()
        }
        return self.battles.insert_one(battle_data)

# Inicializar base de datos del juego
db = GameDatabase()

# ========== TAREAS AUTOMÁTICAS ==========
@tasks.loop(hours=24)
async def reset_daily_tasks():
    """Resetea los usos diarios cada 24 horas"""
    if db.db is not None:
        db.reset_daily_uses()
        print("✅ Usos diarios reseteados")

@tasks.loop(hours=48)
async def full_recovery_task():
    """Cura completamente a todos los jugadores cada 48 horas"""
    if db.db is not None:
        healed_count = db.full_recovery_all_players()
        revived_count = db.check_and_revive_dead_players()
        print(f"✅ Recuperación completa: {healed_count} curados, {revived_count} revividos")

# ========== FUNCIONES AUXILIARES ==========
def get_random_monster() -> Monster:
    """Selecciona un monstruo aleatorio basado en las probabilidades"""
    monster_names = list(NORMALIZED_MONSTER_PROBABILITIES.keys())
    probabilities = list(NORMALIZED_MONSTER_PROBABILITIES.values())
    
    chosen_name = random.choices(monster_names, weights=probabilities, k=1)[0]
    return MONSTERS[chosen_name]

def get_random_character_reward() -> Tuple[Optional[Character], str]:
    """Selecciona una recompensa aleatoria basada en probabilidades"""
    # Determinar tipo de recompensa
    reward_type = random.choices(
        ["S", "A", "B", "C", "resources"],
        weights=[CHARACTER_PROBABILITIES[t] for t in ["S", "A", "B", "C", "resources"]],
        k=1
    )[0]
    
    if reward_type == "resources":
        return None, "resources"
    
    # Seleccionar personaje aleatorio de la categoría
    if reward_type == "S":
        character_name = random.choice(list(S_CHARACTERS.keys()))
        return S_CHARACTERS[character_name], "S"
    elif reward_type == "A":
        character_name = random.choice(list(A_CHARACTERS.keys()))
        return A_CHARACTERS[character_name], "A"
    elif reward_type == "B":
        character_name = random.choice(list(B_CHARACTERS.keys()))
        return B_CHARACTERS[character_name], "B"
    else:  # C
        character_name = random.choice(list(C_CHARACTERS.keys()))
        return C_CHARACTERS[character_name], "C"

def check_player_dead(player_data: Dict) -> tuple[bool, Optional[str]]:
    """Verifica si el jugador está muerto y devuelve tiempo restante"""
    if not player_data["is_dead"]:
        return False, None
    
    death_time = player_data["death_time"]
    if not death_time:
        return True, "indefinido"
    
    revive_time = death_time + timedelta(days=2)
    time_left = revive_time - datetime.utcnow()
    
    if time_left.total_seconds() <= 0:
        # Debería haber sido revivido por la tarea, pero por si acaso
        db.revive_player(int(player_data["discord_id"]))
        return False, None
    
    # Formatear tiempo restante
    hours = int(time_left.total_seconds() // 3600)
    minutes = int((time_left.total_seconds() % 3600) // 60)
    
    return True, f"{hours}h {minutes}m"

def check_next_full_recovery() -> str:
    """Calcula cuándo será la próxima recuperación completa"""
    now = datetime.utcnow()
    hours_since_midnight = now.hour + now.minute/60 + now.second/3600
    hours_to_next = (48 - (hours_since_midnight % 48)) % 48
    
    if hours_to_next == 0:
        hours_to_next = 48
    
    hours = int(hours_to_next)
    minutes = int((hours_to_next - hours) * 60)
    
    return f"{hours}h {minutes}m"

def create_progress_bar(current: int, maximum: int, length: int = 10) -> str:
    """Crea una barra de progreso visual"""
    if maximum == 0:
        return "[░░░░░░░░░░] 0/0"
    
    filled = int((current / maximum) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {current}/{maximum}"

def apply_monster_effect(monster: Monster) -> Tuple[BattleEffect, str]:
    """Aplica el efecto especial del monstruo si se activa"""
    if monster.effect == BattleEffect.NONE:
        return BattleEffect.NONE, ""
    
    # Verificar si se activa el efecto
    if random.random() <= monster.effect_chance:
        effect = monster.effect
        
        if effect == BattleEffect.INSTAKILL:
            return effect, "⚡ **¡INSTAKILL!** El monstruo usa un ataque instantáneo mortal."
        elif effect == BattleEffect.MUTE:
            return effect, "🔇 **¡SILENCIADO!** El monstruo te ha silenciado."
        elif effect == BattleEffect.LAG:
            return effect, "🐌 **¡LAG!** El monstruo es lento y atacará al final."
        elif effect == BattleEffect.FAST:
            return effect, "⚡ **¡VELOCIDAD!** El monstruo es rápido y atacará primero."
        elif effect == BattleEffect.SLEEP:
            return effect, "😴 **¡SUEÑO!** El monstruo se ha dormido. ¡Ganas automáticamente!"
        elif effect == BattleEffect.FEAR:
            return effect, "😨 **¡MIEDO!** El monstruo tiene miedo. ¡Ganas automáticamente!"
    
    return BattleEffect.NONE, ""

def apply_character_effect(character: Character, battle_result: str) -> Dict:
    """Aplica el efecto especial del personaje después de una batalla"""
    effects = {
        "coins_extra": 0,
        "heal": 0,
        "extra_roll": False
    }
    
    if not character.special_effect:
        return effects
    
    # Verificar si se activa el efecto
    if random.random() <= character.effect_chance:
        effect_text = character.special_effect.lower()
        
        if "monedas" in effect_text or "bonus" in effect_text:
            # Extraer cantidad de monedas
            import re
            coin_matches = re.findall(r'\d+', effect_text)
            if coin_matches:
                if "-" in effect_text:
                    # Rango de monedas
                    if len(coin_matches) >= 2:
                        min_coins = int(coin_matches[0])
                        max_coins = int(coin_matches[1])
                        effects["coins_extra"] = random.randint(min_coins, max_coins)
                    else:
                        effects["coins_extra"] = int(coin_matches[0])
                else:
                    # Cantidad fija
                    effects["coins_extra"] = sum(int(match) for match in coin_matches)
        
        elif "vida" in effect_text or "recupera" in effect_text:
            # Extraer cantidad de vida
            import re
            heal_matches = re.findall(r'\d+', effect_text)
            if heal_matches:
                effects["heal"] = sum(int(match) for match in heal_matches)
        
        elif "tirada" in effect_text:
            effects["extra_roll"] = True
    
    return effects

# ========== COMANDOS DEL JUEGO ==========
@bot.command(name='game', aliases=['juego'])
async def game_main(ctx, action: str = None, *, args: str = None):
    """Sistema principal del juego"""
    if not action:
        await show_game_help(ctx)
        return
    
    action = action.lower()
    
    if action == "start":
        await game_start(ctx, args)
    elif action == "daily":
        await game_daily(ctx)
    elif action == "sdaily":
        await game_sdaily(ctx)
    elif action == "profile":
        await game_profile(ctx)
    elif action == "characters":
        await game_characters(ctx, args)
    elif action == "switch":
        await game_switch(ctx, args)
    elif action == "inventory":
        await game_inventory(ctx)
    elif action == "shop":
        await game_shop(ctx)
    elif action == "fight":
        await game_fight(ctx, args)
    elif action == "heal":
        await game_heal(ctx)
    elif action == "leaderboard":
        await game_leaderboard(ctx)
    elif action == "status":
        await game_status(ctx)
    elif action == "revive":
        await game_revive(ctx)
    elif action == "monsters":
        await game_monsters(ctx)
    elif action == "probabilities":
        await game_probabilities(ctx)
    else:
        await ctx.send("❌ Acción no válida. Usa `t!game help` para ver opciones.")

async def show_game_help(ctx):
    """Muestra la ayuda del juego"""
    embed = discord.Embed(
        title="🎮 Sistema de Juego - Comandos",
        description="**Prefijo: t!game**",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="🎯 **Inicio**",
        value="`start <personaje>` - Comienza tu aventura\n"
              "Personajes iniciales: Guy, Mage, Archer, Rogue",
        inline=False
    )
    
    embed.add_field(
        name="📅 **Recompensas Diarias**",
        value="`daily` - Recompensa diaria (5 usos/día)\n"
              "`sdaily` - Recompensa especial (1 uso/día)",
        inline=False
    )
    
    embed.add_field(
        name="👥 **Personajes**",
        value="`characters` - Tus personajes desbloqueados\n"
              "`characters all` - Ver todos los personajes\n"
              "`switch <nombre>` - Cambiar de personaje",
        inline=False
    )
    
    embed.add_field(
        name="📊 **Información**",
        value="`profile` - Tu perfil de jugador\n"
              "`inventory` - Tu inventario\n"
              "`leaderboard` - Tabla de clasificación\n"
              "`status` - Estado del servidor\n"
              "`monsters` - Lista de monstruos\n"
              "`probabilities` - Probabilidades",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ **Combate**",
        value="`fight <monstruo>` - Pelea contra un monstruo\n"
              "`heal` - Cura a tu personaje actual",
        inline=False
    )
    
    embed.add_field(
        name="💀 **Muerte**",
        value="`revive` - Verifica si puedes revivir\n"
              "⚠️ Si mueres, debes esperar 48 horas",
        inline=False
    )
    
    embed.add_field(
        name="🛒 **Tienda** (Próximamente)",
        value="`shop` - Tienda de objetos",
        inline=False
    )
    
    # Información del sistema
    next_recovery = check_next_full_recovery()
    embed.add_field(
        name="⏰ **Sistema de Recuperación**",
        value=f"• Todos los personajes se curan completamente cada **48 horas**\n"
              f"• Próxima recuperación: **{next_recovery}**\n"
              f"• Si mueres, revives automáticamente después de **48 horas**",
        inline=False
    )
    
    embed.add_field(
        name="🎁 **Probabilidades Daily**",
        value="• **Personaje S:** 3% (Legendario)\n"
              "• **Personaje A:** 7% (Épico)\n"
              "• **Personaje B:** 10% (Raro)\n"
              "• **Personaje C:** 20% (Común)\n"
              "• **Recursos:** 60% (Monedas/Pociones/Monstruos)",
        inline=False
    )
    
    await ctx.send(embed=embed)

async def game_start(ctx, character_name: str):
    """Comienza el juego con un personaje"""
    player = db.get_player(ctx.author.id)
    
    if player:
        await ctx.send("❌ Ya tienes un personaje creado. Usa `t!game profile` para ver tu progreso.")
        return
    
    if not character_name:
        # Mostrar selección de personajes
        embed = discord.Embed(
            title="🎮 Selecciona tu Personaje Inicial",
            description="Usa `t!game start <nombre>` para comenzar",
            color=discord.Color.blue()
        )
        
        for name, char in STARTER_CHARACTERS.items():
            embed.add_field(
                name=f"⚔️ {name} ({char.rarity.value})",
                value=f"**Vida:** {char.max_hp} ❤️\n"
                      f"**Daño:** {char.min_damage}-{char.max_damage} ⚔️",
                inline=True
            )
        
        embed.set_footer(text="Puedes desbloquear más personajes con t!game daily")
        await ctx.send(embed=embed)
        return
    
    if character_name not in STARTER_CHARACTERS:
        await ctx.send(f"❌ Personaje '{character_name}' no encontrado. Personajes iniciales: {', '.join(STARTER_CHARACTERS.keys())}")
        return
    
    # Crear jugador
    result = db.create_player(ctx.author.id, ctx.author.name, character_name)
    
    if result:
        char = STARTER_CHARACTERS[character_name]
        embed = discord.Embed(
            title="🎉 ¡Bienvenido a la Aventura!",
            description=f"Has creado a **{character_name}** ({char.rarity.value})",
            color=discord.Color.green()
        )
        
        embed.add_field(name="❤️ Vida", value=f"{char.max_hp} HP", inline=True)
        embed.add_field(name="⚔️ Daño", value=f"{char.min_damage}-{char.max_damage}", inline=True)
        embed.add_field(name="💰 Monedas", value="0", inline=True)
        
        embed.add_field(
            name="🎁 Sistema de Personajes",
            value=f"• Usa `t!game daily` para desbloquear nuevos personajes\n"
                  f"• **Probabilidades:** S(3%) A(7%) B(10%) C(20%) Recursos(60%)\n"
                  f"• Usa `t!game switch <nombre>` para cambiar de personaje",
            inline=False
        )
        
        embed.add_field(
            name="⚠️ Importante",
            value="• Si mueres, deberás esperar **48 horas** para revivir\n"
                  "• Todos los personajes se curan completamente cada **48 horas**\n"
                  "• Usa `t!game status` para ver el tiempo de recuperación",
            inline=False
        )
        
        embed.set_footer(text="Usa t!game help para ver todos los comandos")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Error al crear el personaje")

async def game_daily(ctx):
    """Recompensa diaria (5 usos por día)"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    is_dead, time_left = check_player_dead(player)
    if is_dead:
        embed = discord.Embed(
            title="💀 ¡Estás muerto!",
            description=f"No puedes usar comandos mientras estás muerto.\n"
                       f"Tiempo para revivir: **{time_left}**\n\n"
                       f"Usa `t!game revive` para verificar si ya puedes revivir.",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return
    
    # Verificar usos diarios
    if player["daily_uses_today"] >= 5:
        await ctx.send("❌ Ya has usado todas tus recompensas diarias hoy. Vuelve mañana.")
        return
    
    # Actualizar contador
    db.update_player(ctx.author.id, {"daily_uses_today": player["daily_uses_today"] + 1})
    
    # Obtener recompensa aleatoria
    character_reward, reward_type = get_random_character_reward()
    
    embed = discord.Embed(
        title="🎁 Recompensa Diaria",
        color=discord.Color.gold()
    )
    
    if reward_type == "resources":
        # Recursos normales (60% probabilidad)
        reward_type = random.choices(
            ["coins", "potion", "monster"],
            weights=[0.4, 0.3, 0.3],
            k=1
        )[0]
        
        if reward_type == "coins":
            coins = random.randint(5, 100)
            db.add_coins(ctx.author.id, coins)
            embed.description = f"Has encontrado **{coins} monedas** 💰"
            embed.add_field(name="💸 Monedas totales", value=f"{player['coins'] + coins}", inline=True)
            
        elif reward_type == "potion":
            heal_amount = random.randint(5, 20)
            db.heal_player(ctx.author.id, heal_amount)
            embed.description = f"Has encontrado una **poción** que cura **{heal_amount} HP** ❤️"
            
            player_after = db.get_player(ctx.author.id)
            embed.add_field(name="❤️ Vida actual", value=f"{player_after['character_stats']['current_hp']}/{player_after['character_stats']['max_hp']}", inline=True)
            
        else:  # monster
            monster = get_random_monster()
            await start_battle(ctx, player, monster)
            return  # La batalla manejará su propio mensaje
        
        embed.set_footer(text=f"Usos diarios hoy: {player['daily_uses_today'] + 1}/5 • Recurso normal")
        
    else:
        # ¡Personaje desbloqueado!
        character = character_reward
        
        # Verificar si ya tiene el personaje
        already_owned = False
        for char in player.get("unlocked_characters", []):
            if char["name"] == character.name:
                already_owned = True
                break
        
        if already_owned:
            # Si ya lo tiene, dar monedas en su lugar
            coins_reward = {
                "S": 500,
                "A": 250,
                "B": 100,
                "C": 50
            }[reward_type]
            
            db.add_coins(ctx.author.id, coins_reward)
            embed.description = f"🎉 **¡Ya tenías a {character.name}!**\nRecibes {coins_reward} monedas en su lugar."
            embed.add_field(name="💸 Monedas totales", value=f"{player['coins'] + coins_reward}", inline=True)
            embed.add_field(name="⭐ Rareza", value=character.rarity.value, inline=True)
            
        else:
            # Desbloquear nuevo personaje
            db.unlock_character(ctx.author.id, character.name)
            
            # Crear emoji según rareza
            rarity_emojis = {
                "S": "🌟",
                "A": "💎",
                "B": "⭐",
                "C": "🔹"
            }
            
            embed.description = f"{rarity_emojis[reward_type]} **¡NUEVO PERSONAJE DESBLOQUEADO!** {rarity_emojis[reward_type]}"
            embed.add_field(name="🎭 Personaje", value=f"**{character.name}**", inline=True)
            embed.add_field(name="⭐ Rareza", value=character.rarity.value, inline=True)
            embed.add_field(name="❤️ Vida", value=f"{character.max_hp} HP", inline=True)
            embed.add_field(name="⚔️ Daño", value=f"{character.min_damage}-{character.max_damage}", inline=True)
            
            if character.special_effect:
                embed.add_field(
                    name="✨ Efecto Especial",
                    value=f"{character.special_effect}",
                    inline=False
                )
            
            embed.add_field(
                name="🎮 Usar personaje",
                value=f"Usa `t!game switch {character.name}` para cambiarte a este personaje",
                inline=False
            )
        
        embed.set_footer(text=f"Usos diarios hoy: {player['daily_uses_today'] + 1}/5 • Personaje {reward_type}")
    
    await ctx.send(embed=embed)

async def game_sdaily(ctx):
    """Recompensa diaria especial (1 uso por día)"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    is_dead, time_left = check_player_dead(player)
    if is_dead:
        embed = discord.Embed(
            title="💀 ¡Estás muerto!",
            description=f"No puedes usar comandos mientras estás muerto.\n"
                       f"Tiempo para revivir: **{time_left}**\n\n"
                       f"Usa `t!game revive` para verificar si ya puedes revivir.",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return
    
    # Verificar si ya usó el sdaily hoy
    if player["sdaily_used_today"]:
        await ctx.send("❌ Ya has usado tu recompensa especial hoy. Vuelve mañana.")
        return
    
    # Marcar como usado
    db.update_player(ctx.author.id, {"sdaily_used_today": True})
    
    # Generar 3 recompensas (triple daily)
    rewards = []
    total_coins = 0
    total_heal = 0
    characters_unlocked = []
    monster_appeared = False
    
    for i in range(3):
        character_reward, reward_type = get_random_character_reward()
        
        if reward_type == "resources":
            # Recursos normales (doble en sdaily)
            reward_subtype = random.choices(
                ["coins", "potion", "monster"],
                weights=[0.4, 0.3, 0.3],
                k=1
            )[0]
            
            if reward_subtype == "coins":
                coins = random.randint(5, 100) * 2
                total_coins += coins
                rewards.append(f"💰 {coins} monedas")
                
            elif reward_subtype == "potion":
                heal = random.randint(5, 20) * 2
                total_heal += heal
                rewards.append(f"❤️ Poción (+{heal} HP)")
                
            else:  # monster
                monster_appeared = True
                # Solo un monstruo por sdaily
                if i == 0:  # Solo el primero
                    monster = get_random_monster()
                    await start_battle_sdaily(ctx, player, monster)
                    # Continuar con las otras recompensas después de la batalla
                    
        else:
            # Personaje
            character = character_reward
            
            # Verificar si ya tiene el personaje
            already_owned = False
            for char in player.get("unlocked_characters", []):
                if char["name"] == character.name:
                    already_owned = True
                    break
            
            if already_owned:
                # Monedas en su lugar (doble)
                coins_reward = {
                    "S": 1000,
                    "A": 500,
                    "B": 200,
                    "C": 100
                }[reward_type]
                
                total_coins += coins_reward
                rewards.append(f"💰 {coins_reward} monedas (Personaje duplicado)")
            else:
                # Nuevo personaje
                characters_unlocked.append(character)
                
                rarity_emojis = {
                    "S": "🌟",
                    "A": "💎",
                    "B": "⭐",
                    "C": "🔹"
                }
                
                rewards.append(f"{rarity_emojis[reward_type]} {character.name} ({reward_type})")
    
    # Aplicar recompensas acumuladas
    if total_coins > 0:
        db.add_coins(ctx.author.id, total_coins)
    
    if total_heal > 0:
        db.heal_player(ctx.author.id, total_heal)
    
    # Desbloquear personajes
    for character in characters_unlocked:
        db.unlock_character(ctx.author.id, character.name)
    
    if not monster_appeared:
        embed = discord.Embed(
            title="🌟 Recompensa Especial Diaria",
            description="¡Recompensas triples del daily!",
            color=discord.Color.purple()
        )
        
        for i, reward in enumerate(rewards, 1):
            embed.add_field(name=f"Recompensa {i}", value=reward, inline=True)
        
        if total_coins > 0:
            player_after = db.get_player(ctx.author.id)
            embed.add_field(name="💰 Monedas totales", value=f"{player_after['coins']}", inline=False)
        
        if total_heal > 0:
            player_after = db.get_player(ctx.author.id)
            embed.add_field(name="❤️ Vida actual", value=f"{player_after['character_stats']['current_hp']}/{player_after['character_stats']['max_hp']}", inline=False)
        
        if characters_unlocked:
            embed.add_field(
                name="🎉 Personajes Desbloqueados",
                value="\n".join([f"• {char.name}" for char in characters_unlocked]),
                inline=False
            )
        
        embed.set_footer(text="¡Recompensa especial usada hoy!")
        await ctx.send(embed=embed)

async def start_battle_sdaily(ctx, player_data: Dict, monster: Monster) -> str:
    """Versión simplificada de batalla para sdaily"""
    player = player_data["character_stats"]
    
    # Verificar que el jugador esté vivo
    if player_data.get("is_dead", False):
        return "player_dead"
    
    # Aplicar efecto del monstruo
    effect, effect_message = apply_monster_effect(monster)
    
    # Efectos que ganan automáticamente
    if effect in [BattleEffect.SLEEP, BattleEffect.FEAR]:
        # Victoria automática
        db.update_player(ctx.author.id, {
            "monsters_defeated": player_data.get("monsters_defeated", 0) + 1
        })
        db.add_coins(ctx.author.id, monster.coins_reward)
        
        embed = discord.Embed(
            title=f"🎉 ¡Victoria Automática!",
            description=f"{effect_message}\n\nHas derrotado a **{monster.name}** sin pelear.",
            color=discord.Color.green()
        )
        
        embed.add_field(name="💰 Recompensa", value=f"{monster.coins_reward} monedas", inline=True)
        embed.add_field(name="👹 Monstruo", value=f"{monster.name}", inline=True)
        
        await ctx.send(embed=embed)
        return "auto_win"
    
    # Efecto Instakill
    elif effect == BattleEffect.INSTAKILL:
        db.kill_player(ctx.author.id)
        
        embed = discord.Embed(
            title="💀 ¡INSTAKILL!",
            description=f"{effect_message}\n\n**{monster.name}** te ha matado instantáneamente.\n\n"
                       f"**⚠️ Deberás esperar 48 horas para revivir.**",
            color=discord.Color.dark_red()
        )
        
        await ctx.send(embed=embed)
        return "instakill"
    
    # Para otros efectos, solo mostrar info
    elif effect != BattleEffect.NONE:
        embed = discord.Embed(
            title="⚔️ ¡Encontraste un monstruo!",
            description=f"**{monster.name}** apareció durante tu recompensa especial.\n\n"
                       f"{effect_message}\n\n"
                       f"Usa `t!game fight` si quieres pelear contra él.",
            color=discord.Color.orange()
        )
        
        embed.add_field(name="❤️ Vida", value=f"{monster.hp} HP", inline=True)
        embed.add_field(name="⚔️ Daño", value=f"{monster.min_damage}-{monster.max_damage}", inline=True)
        embed.add_field(name="💰 Recompensa", value=f"{monster.coins_reward} monedas", inline=True)
        
        await ctx.send(embed=embed)
        return "monster_info"
    
    return "normal_monster"

async def game_profile(ctx):
    """Muestra el perfil del jugador"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    char_stats = player["character_stats"]
    
    embed = discord.Embed(
        title=f"📊 Perfil de {ctx.author.display_name}",
        color=discord.Color.blue()
    )
    
    # Barra de progreso de vida
    hp_bar = create_progress_bar(char_stats["current_hp"], char_stats["max_hp"])
    
    # Estado (vivo/muerto)
    if player["is_dead"]:
        embed.add_field(name="💀 Estado", value="**MUERTO**", inline=True)
        embed.add_field(name="⏰ Tiempo para revivir", value=f"{check_player_dead(player)[1]}", inline=True)
        embed.add_field(name="🎭 Personaje actual", value=f"**{char_stats['name']}**", inline=True)
    else:
        embed.add_field(name="❤️ Estado", value="**VIVO**", inline=True)
        embed.add_field(name="🎭 Personaje actual", value=f"**{char_stats['name']}**", inline=True)
        embed.add_field(name="❤️ Vida", value=f"{char_stats['current_hp']}/{char_stats['max_hp']}\n{hp_bar}", inline=False)
    
    embed.add_field(name="⚔️ Daño", value=f"{char_stats['min_damage']}-{char_stats['max_damage']}", inline=True)
    embed.add_field(name="💰 Monedas", value=f"**{player['coins']}**", inline=True)
    
    if char_stats.get("special_effect"):
        embed.add_field(name="✨ Efecto", value=char_stats["special_effect"], inline=False)
    
    embed.add_field(name="👹 Monstruos Derrotados", value=f"**{player.get('monsters_defeated', 0)}**", inline=True)
    embed.add_field(name="💥 Daño Total", value=f"**{player.get('total_damage_dealt', 0)}**", inline=True)
    embed.add_field(name="👥 Personajes Desbloqueados", value=f"**{player.get('characters_unlocked', 1)}/{len(ALL_CHARACTERS)}**", inline=True)
    
    # Información diaria
    embed.add_field(
        name="📅 Progreso Diario",
        value=f"**Daily:** {player['daily_uses_today']}/5 usados\n"
              f"**Sdaily:** {'✅ Usado' if player['sdaily_used_today'] else '❌ Disponible'}",
        inline=False
    )
    
    # Última recuperación completa
    last_recovery = player.get('last_full_recovery', player['created_at'])
    if isinstance(last_recovery, datetime):
        embed.add_field(
            name="⏰ Última Recuperación",
            value=last_recovery.strftime("%d/%m/%Y %H:%M"),
            inline=True
        )
    
    next_recovery = check_next_full_recovery()
    embed.add_field(
        name="🔄 Próxima Recuperación",
        value=next_recovery,
        inline=True
    )
    
    embed.set_footer(text=f"Jugando desde {player['created_at'].strftime('%d/%m/%Y')}")
    await ctx.send(embed=embed)

async def game_characters(ctx, args: str = None):
    """Muestra los personajes del jugador"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    if args and args.lower() == "all":
        # Mostrar todos los personajes disponibles
        await show_all_characters(ctx)
        return
    
    # Mostrar personajes desbloqueados del jugador
    unlocked_chars = player.get("unlocked_characters", [])
    current_char = player["current_character"]
    
    if not unlocked_chars:
        embed = discord.Embed(
            title="👥 Tus Personajes",
            description="Solo tienes tu personaje inicial.",
            color=discord.Color.light_grey()
        )
    else:
        embed = discord.Embed(
            title="👥 Tus Personajes Desbloqueados",
            color=discord.Color.gold()
        )
        
        # Separar por rareza
        s_chars = []
        a_chars = []
        b_chars = []
        c_chars = []
        starter_chars = []
        
        for char in unlocked_chars:
            if char["name"] in S_CHARACTERS:
                s_chars.append(char)
            elif char["name"] in A_CHARACTERS:
                a_chars.append(char)
            elif char["name"] in B_CHARACTERS:
                b_chars.append(char)
            elif char["name"] in C_CHARACTERS:
                c_chars.append(char)
            else:
                starter_chars.append(char)
        
        # Mostrar personaje actual primero
        for char in unlocked_chars:
            if char["name"] == current_char:
                status = "✅ ACTUAL"
                embed.add_field(
                    name=f"🎯 {char['name']} {status}",
                    value=f"**Rareza:** {char['rarity']}\n"
                          f"**Vida:** {char['current_hp']}/{char['max_hp']} ❤️\n"
                          f"**Daño:** {char['min_damage']}-{char['max_damage']} ⚔️\n"
                          f"{'**Efecto:** ' + char['special_effect'] if char.get('special_effect') else ''}",
                    inline=False
                )
                break
        
        # Mostrar otros personajes por rareza
        def add_characters_section(chars_list, title, emoji):
            if chars_list:
                chars_text = []
                for char in chars_list:
                    if char["name"] != current_char:
                        status = "❤️" if char["current_hp"] > 0 else "💀"
                        chars_text.append(f"{emoji} **{char['name']}** {status} - {char['current_hp']}/{char['max_hp']} HP")
                
                if chars_text:
                    embed.add_field(
                        name=title,
                        value="\n".join(chars_text),
                        inline=False
                    )
        
        add_characters_section(s_chars, "🌟 Personajes S (Legendarios)", "🌟")
        add_characters_section(a_chars, "💎 Personajes A (Épicos)", "💎")
        add_characters_section(b_chars, "⭐ Personajes B (Raros)", "⭐")
        add_characters_section(c_chars, "🔹 Personajes C (Comunes)", "🔹")
        add_characters_section(starter_chars, "🎯 Personajes Iniciales", "🎯")
    
    embed.set_footer(text=f"Total: {len(unlocked_chars)}/{len(ALL_CHARACTERS)} personajes • Usa t!game characters all para ver todos")
    await ctx.send(embed=embed)

async def show_all_characters(ctx):
    """Muestra todos los personajes disponibles"""
    embed = discord.Embed(
        title="📚 Todos los Personajes Disponibles",
        description="Personajes organizados por rareza:",
        color=discord.Color.purple()
    )
    
    # Personajes S
    if S_CHARACTERS:
        s_text = []
        for name, char in S_CHARACTERS.items():
            effect_text = f" - {char.special_effect}" if char.special_effect else ""
            s_text.append(f"🌟 **{name}** - {char.max_hp} HP | {char.min_damage}-{char.max_damage} daño{effect_text}")
        
        embed.add_field(
            name="🌟 S - Legendarios (3%)",
            value="\n".join(s_text),
            inline=False
        )
    
    # Personajes A
    if A_CHARACTERS:
        a_text = []
        for name, char in A_CHARACTERS.items():
            effect_text = f" - {char.special_effect}" if char.special_effect else ""
            a_text.append(f"💎 **{name}** - {char.max_hp} HP | {char.min_damage}-{char.max_damage} daño{effect_text}")
        
        embed.add_field(
            name="💎 A - Épicos (7%)",
            value="\n".join(a_text),
            inline=False
        )
    
    # Personajes B
    if B_CHARACTERS:
        b_text = []
        for name, char in B_CHARACTERS.items():
            effect_text = f" - {char.special_effect}" if char.special_effect else ""
            b_text.append(f"⭐ **{name}** - {char.max_hp} HP | {char.min_damage}-{char.max_damage} daño{effect_text}")
        
        embed.add_field(
            name="⭐ B - Raros (10%)",
            value="\n".join(b_text),
            inline=False
        )
    
    # Personajes C
    if C_CHARACTERS:
        c_text = []
        for name, char in C_CHARACTERS.items():
            effect_text = f" - {char.special_effect}" if char.special_effect else ""
            c_text.append(f"🔹 **{name}** - {char.max_hp} HP | {char.min_damage}-{char.max_damage} daño{effect_text}")
        
        embed.add_field(
            name="🔹 C - Comunes (20%)",
            value="\n".join(c_text),
            inline=False
        )
    
    # Personajes Iniciales
    if STARTER_CHARACTERS:
        starter_text = []
        for name, char in STARTER_CHARACTERS.items():
            starter_text.append(f"🎯 **{name}** - {char.max_hp} HP | {char.min_damage}-{char.max_damage} daño")
        
        embed.add_field(
            name="🎯 Personajes Iniciales",
            value="\n".join(starter_text),
            inline=False
        )
    
    embed.add_field(
        name="📊 Probabilidades en Daily",
        value="• **S:** 3% - Legendario\n• **A:** 7% - Épico\n• **B:** 10% - Raro\n• **C:** 20% - Común\n• **Recursos:** 60% - Monedas/Pociones/Monstruos",
        inline=False
    )
    
    embed.set_footer(text=f"Total: {len(ALL_CHARACTERS)} personajes • Usa t!game daily para desbloquearlos")
    await ctx.send(embed=embed)

async def game_switch(ctx, character_name: str):
    """Cambia el personaje actual"""
    if not character_name:
        await ctx.send("❌ Uso: `t!game switch <nombre_personaje>`")
        return
    
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    is_dead, time_left = check_player_dead(player)
    if is_dead:
        embed = discord.Embed(
            title="💀 ¡Estás muerto!",
            description=f"No puedes cambiar de personaje mientras estás muerto.\n"
                       f"Tiempo para revivir: **{time_left}**",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return
    
    # Verificar si el personaje está desbloqueado
    has_character = False
    target_char = None
    
    for char in player.get("unlocked_characters", []):
        if char["name"].lower() == character_name.lower():
            has_character = True
            target_char = char
            break
    
    if not has_character:
        await ctx.send(f"❌ No tienes desbloqueado a **{character_name}**. Usa `t!game daily` para desbloquear personajes.")
        return
    
    # Verificar si ya es el personaje actual
    if player["current_character"].lower() == character_name.lower():
        await ctx.send(f"❌ Ya estás usando a **{character_name}**.")
        return
    
    # Cambiar de personaje
    result = db.switch_character(ctx.author.id, target_char["name"])
    
    if result:
        embed = discord.Embed(
            title="🔄 Cambio de Personaje",
            description=f"Has cambiado a **{target_char['name']}**",
            color=discord.Color.green()
        )
        
        embed.add_field(name="❤️ Vida", value=f"{target_char['current_hp']}/{target_char['max_hp']} HP", inline=True)
        embed.add_field(name="⚔️ Daño", value=f"{target_char['min_damage']}-{target_char['max_damage']}", inline=True)
        embed.add_field(name="⭐ Rareza", value=target_char["rarity"], inline=True)
        
        if target_char.get("special_effect"):
            embed.add_field(name="✨ Efecto Especial", value=target_char["special_effect"], inline=False)
        
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Error al cambiar de personaje.")

async def game_inventory(ctx):
    """Muestra el inventario del jugador (simplificado)"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    embed = discord.Embed(
        title="🎒 Tu Inventario",
        description="Aquí están tus posesiones actuales:",
        color=discord.Color.green()
    )
    
    embed.add_field(name="💰 Monedas", value=f"{player['coins']} monedas", inline=True)
    
    # Mostrar algunos items básicos (puedes expandir esto)
    if player.get("inventory"):
        items = player["inventory"]
        items_text = []
        for item in items[:10]:  # Mostrar primeros 10 items
            items_text.append(f"• {item.get('name', 'Item desconocido')} x{item.get('quantity', 1)}")
        
        if items_text:
            embed.add_field(
                name="📦 Items",
                value="\n".join(items_text),
                inline=False
            )
    else:
        embed.add_field(name="📦 Items", value="Tu inventario está vacío", inline=False)
    
    # Información de personajes
    embed.add_field(
        name="👥 Personajes Desbloqueados",
        value=f"{player.get('characters_unlocked', 1)}/{len(ALL_CHARACTERS)} personajes",
        inline=True
    )
    
    embed.set_footer(text="Usa t!game shop para comprar items (próximamente)")
    await ctx.send(embed=embed)

async def game_shop(ctx):
    """Muestra la tienda (simplificada)"""
    embed = discord.Embed(
        title="🛒 Tienda del Juego",
        description="Aquí puedes comprar items y mejoras (próximamente)",
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name="🎭 Personajes Especiales",
        value="Próximamente podrás comprar personajes exclusivos",
        inline=False
    )
    
    embed.add_field(
        name="❤️ Pociones de Vida",
        value="Pociones que recuperan 25 HP - **50 monedas**",
        inline=False
    )
    
    embed.add_field(
        name="⚔️ Mejoras de Daño",
        value="Aumenta tu daño base - **100 monedas**",
        inline=False
    )
    
    embed.add_field(
        name="🛡️ Armaduras",
        value="Reduce el daño recibido - **200 monedas**",
        inline=False
    )
    
    embed.set_footer(text="La tienda estará disponible en la próxima actualización")
    await ctx.send(embed=embed)

async def game_fight(ctx, monster_name: str = None):
    """Pelea contra un monstruo"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    is_dead, time_left = check_player_dead(player)
    if is_dead:
        embed = discord.Embed(
            title="💀 ¡Estás muerto!",
            description=f"No puedes pelear mientras estás muerto.\n"
                       f"Tiempo para revivir: **{time_left}**\n\n"
                       f"Usa `t!game revive` para verificar si ya puedes revivir.",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return
    
    # Verificar que el jugador tenga vida
    if player["character_stats"]["current_hp"] <= 0:
        await ctx.send("❌ Tu personaje no tiene vida. Usa `t!game heal` para curarte.")
        return
    
    # Obtener monstruo aleatorio o específico
    if monster_name:
        # Buscar monstruo específico
        monster = None
        for key, m in MONSTERS.items():
            if monster_name.lower() in key.lower():
                monster = m
                break
        
        if not monster:
            await ctx.send(f"❌ Monstruo '{monster_name}' no encontrado.")
            return
    else:
        # Monstruo aleatorio
        monster = get_random_monster()
    
    await start_battle(ctx, player, monster)

async def start_battle(ctx, player_data: Dict, monster: Monster):
    """Inicia una batalla entre el jugador y un monstruo"""
    player = player_data["character_stats"]
    
    # Crear embed inicial de batalla
    embed = discord.Embed(
        title="⚔️ ¡COMIENZA LA BATALLA!",
        description=f"**{player['name']}** vs **{monster.name}**",
        color=discord.Color.red()
    )
    
    embed.add_field(name=f"❤️ {player['name']}", value=f"{player['current_hp']}/{player['max_hp']} HP", inline=True)
    embed.add_field(name="⚔️ Daño", value=f"{player['min_damage']}-{player['max_damage']}", inline=True)
    
    embed.add_field(name="\u200b", value="\u200b", inline=True)  # Separador
    
    embed.add_field(name=f"👹 {monster.name}", value=f"{monster.hp} HP", inline=True)
    embed.add_field(name="⚔️ Daño", value=f"{monster.min_damage}-{monster.max_damage}", inline=True)
    embed.add_field(name="💰 Recompensa", value=f"{monster.coins_reward} monedas", inline=True)
    
    if monster.effect != BattleEffect.NONE:
        embed.add_field(
            name="⚠️ Efecto Especial",
            value=f"{monster.effect.value} ({monster.effect_chance*100}% probabilidad)",
            inline=False
        )
    
    battle_msg = await ctx.send(embed=embed)
    
    # Pequeña pausa para dramatismo
    await asyncio.sleep(2)
    
    # Aplicar efecto del monstruo
    effect, effect_message = apply_monster_effect(monster)
    
    # Verificar efectos especiales
    if effect == BattleEffect.INSTAKILL:
        # Instakill - jugador muere instantáneamente
        db.kill_player(ctx.author.id)
        
        embed = discord.Embed(
            title="💀 ¡INSTAKILL!",
            description=f"{effect_message}\n\n**{monster.name}** te ha matado instantáneamente.\n\n"
                       f"**⚠️ Deberás esperar 48 horas para revivir.**",
            color=discord.Color.dark_red()
        )
        
        await battle_msg.edit(embed=embed)
        return
    
    elif effect in [BattleEffect.SLEEP, BattleEffect.FEAR]:
        # Victoria automática
        db.update_player(ctx.author.id, {
            "monsters_defeated": player_data.get("monsters_defeated", 0) + 1
        })
        db.add_coins(ctx.author.id, monster.coins_reward)
        
        embed = discord.Embed(
            title="🎉 ¡VICTORIA AUTOMÁTICA!",
            description=f"{effect_message}\n\nHas derrotado a **{monster.name}** sin pelear.",
            color=discord.Color.green()
        )
        
        embed.add_field(name="💰 Recompensa", value=f"{monster.coins_reward} monedas", inline=True)
        embed.add_field(name="👹 Monstruos Derrotados", value=f"{player_data.get('monsters_defeated', 0) + 1}", inline=True)
        
        await battle_msg.edit(embed=embed)
        return
    
    # Iniciar batalla normal
    player_hp = player["current_hp"]
    monster_hp = monster.hp
    
    battle_log = []
    
    # Determinar quién ataca primero (efectos LAG/FAST)
    player_first = True
    if effect == BattleEffect.LAG:
        player_first = False
        battle_log.append("🐌 **¡EFECTO LAG!** Atacas al final del turno.")
    elif effect == BattleEffect.FAST:
        battle_log.append("⚡ **¡EFECTO VELOCIDAD!** Atacas primero en el turno.")
    
    turn = 1
    while player_hp > 0 and monster_hp > 0:
        # Turno del jugador
        if player_first or turn > 1:
            damage = random.randint(player["min_damage"], player["max_damage"])
            monster_hp -= damage
            battle_log.append(f"**Turno {turn}:** {player['name']} ataca a {monster.name} por **{damage}** daño.")
            
            if monster_hp <= 0:
                break
        
        # Turno del monstruo
        damage = random.randint(monster.min_damage, monster.max_damage)
        player_hp -= damage
        battle_log.append(f"**Turno {turn}:** {monster.name} ataca a {player['name']} por **{damage}** daño.")
        
        turn += 1
    
    # Determinar resultado
    if player_hp <= 0:
        # Jugador muere
        db.kill_player(ctx.author.id)
        
        embed = discord.Embed(
            title="💀 ¡HAS MUERTO!",
            description=f"**{monster.name}** te ha derrotado.\n\n"
                       f"**⚠️ Deberás esperar 48 horas para revivir.**",
            color=discord.Color.dark_red()
        )
        
        if battle_log:
            embed.add_field(
                name="📜 Registro de Batalla",
                value="\n".join(battle_log[-5:]),  # Mostrar últimos 5 turnos
                inline=False
            )
        
        await battle_msg.edit(embed=embed)
        
    else:
        # Victoria del jugador
        # Actualizar estadísticas
        db.update_player(ctx.author.id, {
            "monsters_defeated": player_data.get("monsters_defeated", 0) + 1,
            "total_damage_dealt": player_data.get("total_damage_dealt", 0) + (monster.hp - monster_hp)
        })
        
        # Dar recompensa de monedas
        db.add_coins(ctx.author.id, monster.coins_reward)
        
        # Actualizar vida del jugador
        db.damage_player(ctx.author.id, player["current_hp"] - player_hp)
        
        # Aplicar efecto del personaje si gana
        character_effects = apply_character_effect(
            ALL_CHARACTERS.get(player["name"], Character(player["name"], Rarity.C, 30, 5, 10)),
            "win"
        )
        
        # Aplicar efectos ganados
        extra_coins = 0
        extra_heal = 0
        
        if character_effects["coins_extra"] > 0:
            extra_coins = character_effects["coins_extra"]
            db.add_coins(ctx.author.id, extra_coins)
        
        if character_effects["heal"] > 0:
            extra_heal = character_effects["heal"]
            db.heal_player(ctx.author.id, extra_heal)
        
        embed = discord.Embed(
            title="🎉 ¡VICTORIA!",
            description=f"Has derrotado a **{monster.name}**",
            color=discord.Color.green()
        )
        
        embed.add_field(name="💰 Recompensa Base", value=f"{monster.coins_reward} monedas", inline=True)
        
        if extra_coins > 0:
            embed.add_field(name="💰 Bonus de Personaje", value=f"+{extra_coins} monedas", inline=True)
        
        if extra_heal > 0:
            embed.add_field(name="❤️ Curación Bonus", value=f"+{extra_heal} HP", inline=True)
        
        embed.add_field(name="❤️ Vida Restante", value=f"{player_hp}/{player['max_hp']} HP", inline=True)
        embed.add_field(name="👹 Monstruos Derrotados", value=f"{player_data.get('monsters_defeated', 0) + 1}", inline=True)
        embed.add_field(name="💥 Daño Total", value=f"{player_data.get('total_damage_dealt', 0) + (monster.hp - monster_hp)}", inline=True)
        
        if battle_log:
            embed.add_field(
                name="📜 Últimos Turnos",
                value="\n".join(battle_log[-3:]),  # Mostrar últimos 3 turnos
                inline=False
            )
        
        await battle_msg.edit(embed=embed)

async def game_heal(ctx):
    """Cura al personaje actual"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    is_dead, time_left = check_player_dead(player)
    if is_dead:
        embed = discord.Embed(
            title="💀 ¡Estás muerto!",
            description=f"No puedes curarte mientras estás muerto.\n"
                       f"Tiempo para revivir: **{time_left}**",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return
    
    char_stats = player["character_stats"]
    
    # Verificar si ya tiene vida completa
    if char_stats["current_hp"] >= char_stats["max_hp"]:
        embed = discord.Embed(
            title="❤️ Vida Completa",
            description=f"**{char_stats['name']}** ya tiene toda su vida.",
            color=discord.Color.green()
        )
        embed.add_field(name="Vida Actual", value=f"{char_stats['current_hp']}/{char_stats['max_hp']} HP")
        await ctx.send(embed=embed)
        return
    
    # Curar completamente
    db.heal_character(ctx.author.id)
    
    # Obtener datos actualizados
    player_after = db.get_player(ctx.author.id)
    
    embed = discord.Embed(
        title="❤️ ¡Curado Completamente!",
        description=f"**{char_stats['name']}** ha sido curado.",
        color=discord.Color.green()
    )
    
    embed.add_field(name="Vida Anterior", value=f"{char_stats['current_hp']}/{char_stats['max_hp']} HP", inline=True)
    embed.add_field(name="Vida Actual", value=f"{player_after['character_stats']['current_hp']}/{player_after['character_stats']['max_hp']} HP", inline=True)
    
    await ctx.send(embed=embed)

async def game_leaderboard(ctx):
    """Muestra la tabla de clasificación"""
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        # Obtener top 10 jugadores por monstruos derrotados
        top_monsters = list(db.players.find({"is_dead": False}).sort("monsters_defeated", -1).limit(10))
        
        # Obtener top 10 jugadores por monedas
        top_coins = list(db.players.find({"is_dead": False}).sort("coins", -1).limit(10))
        
        # Obtener top 10 jugadores por personajes desbloqueados
        top_characters = list(db.players.find({"is_dead": False}).sort("characters_unlocked", -1).limit(10))
        
        embed = discord.Embed(
            title="🏆 Tabla de Clasificación",
            color=discord.Color.gold()
        )
        
        # Top por monstruos derrotados
        if top_monsters:
            monsters_text = []
            for i, player in enumerate(top_monsters, 1):
                monsters_text.append(f"{i}. **{player['username']}** - {player.get('monsters_defeated', 0)} monstruos")
            
            embed.add_field(
                name="👹 Top Cazadores",
                value="\n".join(monsters_text),
                inline=True
            )
        
        # Top por monedas
        if top_coins:
            coins_text = []
            for i, player in enumerate(top_coins, 1):
                coins_text.append(f"{i}. **{player['username']}** - {player.get('coins', 0)} monedas")
            
            embed.add_field(
                name="💰 Top Ricos",
                value="\n".join(coins_text),
                inline=True
            )
        
        # Top por personajes
        if top_characters:
            chars_text = []
            for i, player in enumerate(top_characters, 1):
                chars_text.append(f"{i}. **{player['username']}** - {player.get('characters_unlocked', 1)} personajes")
            
            embed.add_field(
                name="👥 Top Coleccionistas",
                value="\n".join(chars_text),
                inline=True
            )
        
        # Contar jugadores totales
        total_players = db.players.count_documents({})
        alive_players = db.players.count_documents({"is_dead": False})
        
        embed.add_field(
            name="📊 Estadísticas Globales",
            value=f"**Jugadores totales:** {total_players}\n"
                  f"**Jugadores vivos:** {alive_players}\n"
                  f"**Personajes desbloqueados:** {len(ALL_CHARACTERS)}",
            inline=False
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error al obtener la tabla de clasificación: {str(e)}")

async def game_status(ctx):
    """Muestra el estado del servidor del juego"""
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        # Contar jugadores
        total_players = db.players.count_documents({})
        alive_players = db.players.count_documents({"is_dead": False})
        dead_players = db.players.count_documents({"is_dead": True})
        
        # Contar batallas
        total_battles = db.battles.count_documents({})
        
        embed = discord.Embed(
            title="📊 Estado del Servidor de Juego",
            color=discord.Color.blue()
        )
        
        # Estadísticas de jugadores
        embed.add_field(
            name="👥 Jugadores",
            value=f"**Total:** {total_players}\n"
                  f"**Vivos:** {alive_players}\n"
                  f"**Muertos:** {dead_players}",
            inline=True
        )
        
        # Estadísticas del juego
        if total_players > 0:
            # Obtener estadísticas promedio
            pipeline = [
                {"$group": {
                    "_id": None,
                    "avg_coins": {"$avg": "$coins"},
                    "avg_monsters": {"$avg": "$monsters_defeated"},
                    "avg_characters": {"$avg": "$characters_unlocked"}
                }}
            ]
            
            stats = list(db.players.aggregate(pipeline))
            if stats:
                stat = stats[0]
                embed.add_field(
                    name="📈 Promedios",
                    value=f"**Monedas:** {int(stat['avg_coins'])}\n"
                          f"**Monstruos:** {int(stat['avg_monsters'])}\n"
                          f"**Personajes:** {int(stat['avg_characters'])}",
                    inline=True
                )
        
        embed.add_field(
            name="⚔️ Batallas",
            value=f"**Total:** {total_battles}",
            inline=True
        )
        
        # Tiempos del sistema
        next_recovery = check_next_full_recovery()
        embed.add_field(
            name="⏰ Sistema de Tiempo",
            value=f"**Próxima recuperación:** {next_recovery}\n"
                  f"**Reseteo diario:** Cada 24 horas\n"
                  f"**Reinicio muerte:** 48 horas",
            inline=False
        )
        
        # Información de personajes
        embed.add_field(
            name="🎭 Personajes Disponibles",
            value=f"**Total:** {len(ALL_CHARACTERS)}\n"
                  f"**S:** {len(S_CHARACTERS)} | **A:** {len(A_CHARACTERS)}\n"
                  f"**B:** {len(B_CHARACTERS)} | **C:** {len(C_CHARACTERS)}\n"
                  f"**Iniciales:** {len(STARTER_CHARACTERS)}",
            inline=False
        )
        
        embed.set_footer(text="Sistema de juego en funcionamiento")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error al obtener el estado: {str(e)}")

async def game_revive(ctx):
    """Verifica si el jugador puede revivir"""
    player = db.get_player(ctx.author.id)
    
    if not player:
        await ctx.send("❌ No tienes un personaje. Usa `t!game start` para crear uno.")
        return
    
    # Verificar si está muerto
    if not player["is_dead"]:
        embed = discord.Embed(
            title="❤️ ¡Estás vivo!",
            description="No necesitas revivir, ya estás vivo.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        return
    
    death_time = player["death_time"]
    if not death_time:
        # Si no hay tiempo de muerte, revivir inmediatamente
        db.revive_player(ctx.author.id)
        
        embed = discord.Embed(
            title="✨ ¡Revivido!",
            description="Has sido revivido exitosamente.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        return
    
    # Calcular tiempo restante
    revive_time = death_time + timedelta(days=2)
    time_left = revive_time - datetime.utcnow()
    
    if time_left.total_seconds() <= 0:
        # ¡Puede revivir!
        db.revive_player(ctx.author.id)
        
        embed = discord.Embed(
            title="✨ ¡Revivido!",
            description="Has sido revivido exitosamente. ¡Bienvenido de nuevo!",
            color=discord.Color.green()
        )
        
        player_after = db.get_player(ctx.author.id)
        embed.add_field(name="❤️ Vida", value=f"{player_after['character_stats']['current_hp']}/{player_after['character_stats']['max_hp']} HP")
        
        await ctx.send(embed=embed)
    else:
        # Aún no puede revivir
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        seconds = int(time_left.total_seconds() % 60)
        
        embed = discord.Embed(
            title="💀 Aún no puedes revivir",
            description=f"Debes esperar **{hours}h {minutes}m {seconds}s** para revivir.",
            color=discord.Color.dark_grey()
        )
        
        embed.add_field(
            name="⏰ Tiempo de Muerte",
            value=death_time.strftime("%d/%m/%Y %H:%M:%S"),
            inline=True
        )
        
        embed.add_field(
            name="⏰ Tiempo de Revivir",
            value=revive_time.strftime("%d/%m/%Y %H:%M:%S"),
            inline=True
        )
        
        await ctx.send(embed=embed)

async def game_monsters(ctx):
    """Muestra la lista de monstruos disponibles"""
    embed = discord.Embed(
        title="👹 Lista de Monstruos",
        description="Monstruos que puedes encontrar en tus aventuras:",
        color=discord.Color.dark_red()
    )
    
    for monster_name, monster in MONSTERS.items():
        prob = NORMALIZED_MONSTER_PROBABILITIES.get(monster_name, 0)
        
        monster_info = f"**Vida:** {monster.hp} HP\n"
        monster_info += f"**Daño:** {monster.min_damage}-{monster.max_damage}\n"
        monster_info += f"**Recompensa:** {monster.coins_reward} monedas\n"
        monster_info += f"**Probabilidad:** {prob:.2f}%\n"
        
        if monster.effect != BattleEffect.NONE:
            monster_info += f"**Efecto:** {monster.effect.value} ({monster.effect_chance*100}%)\n"
        
        embed.add_field(
            name=f"👹 {monster_name}",
            value=monster_info,
            inline=True
        )
    
    embed.set_footer(text="Usa t!game fight [nombre] para pelear contra un monstruo específico")
    await ctx.send(embed=embed)

async def game_probabilities(ctx):
    """Muestra las probabilidades del juego"""
    embed = discord.Embed(
        title="🎲 Probabilidades del Juego",
        color=discord.Color.purple()
    )
    
    # Probabilidades de daily
    embed.add_field(
        name="🎁 Recompensas Diarias (t!game daily)",
        value=f"• **Personaje S (Legendario):** {CHARACTER_PROBABILITIES['S']}%\n"
              f"• **Personaje A (Épico):** {CHARACTER_PROBABILITIES['A']}%\n"
              f"• **Personaje B (Raro):** {CHARACTER_PROBABILITIES['B']}%\n"
              f"• **Personaje C (Común):** {CHARACTER_PROBABILITIES['C']}%\n"
              f"• **Recursos (Monedas/Pociones/Monstruos):** {CHARACTER_PROBABILITIES['resources']}%",
        inline=False
    )
    
    # Probabilidades de monstruos
    monsters_prob_text = []
    for monster_name, prob in sorted(NORMALIZED_MONSTER_PROBABILITIES.items(), key=lambda x: x[1], reverse=True):
        monsters_prob_text.append(f"• **{monster_name}:** {prob:.2f}%")
    
    embed.add_field(
        name="👹 Aparición de Monstruos",
        value="\n".join(monsters_prob_text),
        inline=False
    )
    
    # Contar personajes por rareza
    embed.add_field(
        name="🎭 Personajes por Rareza",
        value=f"• **S (Legendarios):** {len(S_CHARACTERS)} personajes\n"
              f"• **A (Épicos):** {len(A_CHARACTERS)} personajes\n"
              f"• **B (Raros):** {len(B_CHARACTERS)} personajes\n"
              f"• **C (Comunes):** {len(C_CHARACTERS)} personajes\n"
              f"• **Iniciales:** {len(STARTER_CHARACTERS)} personajes\n"
              f"• **TOTAL:** {len(ALL_CHARACTERS)} personajes",
        inline=False
    )
    
    embed.set_footer(text="Las probabilidades pueden cambiar en futuras actualizaciones")
    await ctx.send(embed=embed)

# ========== COMANDO HELP SIMPLIFICADO ==========
@bot.command(name='help', aliases=['ayuda', 'comandos'])
async def help_command(ctx, comando: str = None):
    """Muestra todos los comandos disponibles"""
    
    if comando:
        # Ayuda específica para un comando
        cmd = bot.get_command(comando)
        if not cmd:
            await ctx.send(f"❌ Comando `{comando}` no encontrado")
            return
        
        embed = discord.Embed(
            title=f"📖 Ayuda: {cmd.name}",
            color=discord.Color.green()
        )
        
        if cmd.help:
            embed.description = cmd.help
        else:
            embed.description = "Sin descripción disponible"
        
        if cmd.aliases:
            embed.add_field(name="Alias", value=", ".join(cmd.aliases), inline=True)
        
        await ctx.send(embed=embed)
    else:
        # Mostrar todos los comandos
        embed = discord.Embed(
            title="📚 Lista de Comandos - Prefijo: t!",
            description="Usa `t!help <comando>` para más detalles",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎮 **Sistema de Juego**",
            value="`t!game` - Sistema principal del juego\n"
                  "`t!game start` - Comenzar aventura\n"
                  "`t!game daily` - Recompensa diaria\n"
                  "`t!game profile` - Ver tu perfil\n"
                  "`t!game characters` - Tus personajes\n"
                  "`t!game fight` - Pelear contra monstruos\n"
                  "`t!game leaderboard` - Tabla de clasificación",
            inline=False
        )
        
        await ctx.send(embed=embed)

# ========== EVENTOS DEL BOT ==========
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'👥 Conectado a {len(bot.guilds)} servidores')
    
    # Estadísticas del juego
    print(f"🎮 Personajes totales: {len(ALL_CHARACTERS)}")
    print(f"  • S: {len(S_CHARACTERS)} | A: {len(A_CHARACTERS)} | B: {len(B_CHARACTERS)} | C: {len(C_CHARACTERS)} | Iniciales: {len(STARTER_CHARACTERS)}")
    print(f"🎲 Probabilidades Daily: S({CHARACTER_PROBABILITIES['S']}%) A({CHARACTER_PROBABILITIES['A']}%) B({CHARACTER_PROBABILITIES['B']}%) C({CHARACTER_PROBABILITIES['C']}%) Recursos({CHARACTER_PROBABILITIES['resources']}%)")
    
    # Iniciar tareas automáticas
    if not reset_daily_tasks.is_running():
        reset_daily_tasks.start()
    
    if not full_recovery_task.is_running():
        full_recovery_task.start()
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.playing,
        name="t!game start para jugar"
    ))

@bot.event
async def on_command_error(ctx, error):
    """Manejo de errores de comandos"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignorar comandos no encontrados
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Faltan argumentos. Usa `t!help {ctx.command}` para ayuda.")
    else:
        print(f"Error en comando {ctx.command}: {error}")

#-------------------------------------------------------------------------------
# ========== WEBSERVER PARA RENDER ==========
from flask import Flask
from threading import Thread
import os

# Crear servidor Flask simple
app = Flask(__name__)

@app.route('/')
def home():
    return "🎮 Bot de juego Discord funcionando | Usa t!game para jugar"

def run_webserver():
    port = int(os.environ.get('PORT', 8080))  # Render asigna un puerto
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """Mantiene el bot activo en Render"""
    server = Thread(target=run_webserver)
    server.daemon = True
    server.start()
    print(f"🌐 Servidor web iniciado en puerto {os.environ.get('PORT', 8080)}")

# ========== MODIFICAR on_ready ==========
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'👥 Conectado a {len(bot.guilds)} servidores')
    
    # Estadísticas del juego
    print(f"🎮 Personajes totales: {len(ALL_CHARACTERS)}")
    print(f"  • S: {len(S_CHARACTERS)} | A: {len(A_CHARACTERS)} | B: {len(B_CHARACTERS)} | C: {len(C_CHARACTERS)} | Iniciales: {len(STARTER_CHARACTERS)}")
    print(f"🎲 Probabilidades Daily: S({CHARACTER_PROBABILITIES['S']}%) A({CHARACTER_PROBABILITIES['A']}%) B({CHARACTER_PROBABILITIES['B']}%) C({CHARACTER_PROBABILITIES['C']}%) Recursos({CHARACTER_PROBABILITIES['resources']}%)")
    
    # Iniciar tareas automáticas
    if not reset_daily_tasks.is_running():
        reset_daily_tasks.start()
    
    if not full_recovery_task.is_running():
        full_recovery_task.start()
    
    # Iniciar servidor web si está en Render
    try:
        # Verificar si estamos en Render (tiene variable PORT)
        if 'PORT' in os.environ:
            keep_alive()
            print("✅ Servidor web para Render iniciado")
    except Exception as e:
        print(f"⚠️ Error al iniciar servidor web: {e}")
    
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.playing,
        name="t!game start para jugar"
    ))

#---------------------------------------------------------------------------------


# ========== INICIAR EL BOT ==========
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR: No se encontró DISCORD_TOKEN")
        print("💡 Asegúrate de tener un archivo .env con DISCORD_TOKEN=tu_token")
        exit(1)
    
    print("🤖 Iniciando bot de Discord con sistema de juego...")
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Token de Discord inválido")
        print("💡 Verifica tu token en el archivo .env")
    except Exception as e:
        print(f"❌ ERROR: {e}")











