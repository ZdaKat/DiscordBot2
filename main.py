import discord
from discord.ext import commands
from pymongo import MongoClient, ReturnDocument
import os
import random
import re
import aiohttp
from datetime import datetime
from bson import ObjectId
import asyncio

# ========== CONFIGURACIÓN INICIAL ==========
# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="t!", intents=intents, help_command=None)

# ========== CONEXIÓN A MONGODB ATLAS ==========
class MongoDB:
    def __init__(self):
        """Inicializa la conexión a MongoDB Atlas"""
        self.connection_string = os.getenv("MONGODB_URI")
        if not self.connection_string:
            print("⚠️ MONGODB_URI no encontrada en .env - Sistema de mochila desactivado")
            self.client = None
            self.db = None
            return
        
        print("🔗 Conectando a MongoDB Atlas...")
        try:
            self.client = MongoClient(self.connection_string)
            # Verificar conexión
            self.client.admin.command('ping')
            self.db = self.client.discord_bot
            self.setup_collections()
            print("✅ Conectado a MongoDB Atlas")
        except Exception as e:
            print(f"❌ Error al conectar a MongoDB: {e}")
            self.client = None
            self.db = None
    
    def setup_collections(self):
        """Configura las colecciones y índices"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return
        
        self.users = self.db.users
        self.inventories = self.db.inventories
        self.items = self.db.items
        
        # Crear índices
        self.users.create_index("discord_id", unique=True)
        self.inventories.create_index([("user_id", 1), ("item_id", 1)], unique=True)
        self.items.create_index("name_lower", unique=True)
    
    # ========== MÉTODOS DE USUARIO ==========
    def get_or_create_user(self, discord_id: int, username: str):
        """Obtiene o crea un usuario en la base de datos"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return None
        
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
    
    # ========== MÉTODOS DE INVENTARIO ==========
    def add_item(self, discord_id: int, item_name: str, quantity: int = 1):
        """Añade un item al inventario del usuario"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return {"error": "Base de datos no disponible"}
        
        user = self.get_or_create_user(discord_id, "Unknown")
        if user is None:
            return {"error": "No se pudo crear/obtener usuario"}
        
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
        self.inventories.update_one(
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
        
        return {"success": True, "item": item}
    
    def remove_item(self, discord_id: int, item_identifier: str, quantity: int = 1):
        """Remueve items del inventario"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return {"error": "Base de datos no disponible"}
        
        user_id = str(discord_id)
        
        # Buscar el item (por ID o nombre)
        item = None
        try:
            if item_identifier.isdigit():
                item = self.items.find_one({"_id": ObjectId(item_identifier)})
            else:
                item = self.items.find_one({"name_lower": item_identifier.lower()})
        except:
            item = None
        
        if not item:
            return {"error": "Item no encontrado"}
        
        # Verificar si el usuario tiene el item
        inventory_item = self.inventories.find_one({
            "user_id": user_id,
            "item_id": str(item["_id"])
        })
        
        if not inventory_item:
            return {"error": "No tienes este item"}
        
        if inventory_item["quantity"] < quantity:
            return {"error": f"No tienes suficientes. Tienes: {inventory_item['quantity']}"}
        
        # Actualizar o eliminar
        new_quantity = inventory_item["quantity"] - quantity
        
        if new_quantity <= 0:
            self.inventories.delete_one({
                "user_id": user_id,
                "item_id": str(item["_id"])
            })
            result = "eliminado"
        else:
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
    
    def get_inventory(self, discord_id: int, page: int = 1, limit: int = 10):
        """Obtiene el inventario de un usuario con paginación"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return {"items": [], "total_items": 0, "total_pages": 0, "current_page": 1, "limit": 10}
        
        user_id = str(discord_id)
        skip = (page - 1) * limit
        
        try:
            total_items = self.inventories.count_documents({"user_id": user_id})
            total_pages = max(1, (total_items + limit - 1) // limit)
            
            inventory_items = list(self.inventories.find(
                {"user_id": user_id}
            ).skip(skip).limit(limit).sort("item_name", 1))
            
            items_with_details = []
            for inv_item in inventory_items:
                try:
                    item = self.items.find_one({"_id": ObjectId(inv_item["item_id"])})
                    if item:
                        items_with_details.append({
                            "inventory_data": inv_item,
                            "item_details": item
                        })
                except:
                    continue
            
            return {
                "items": items_with_details,
                "total_items": total_items,
                "total_pages": total_pages,
                "current_page": min(page, total_pages),
                "limit": limit
            }
        except Exception as e:
            print(f"Error en get_inventory: {e}")
            return {"items": [], "total_items": 0, "total_pages": 0, "current_page": 1, "limit": 10}
    
    def search_items(self, search_term: str, limit: int = 10):
        """Busca items por nombre"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return []
        
        try:
            return list(self.items.find(
                {"name_lower": {"$regex": search_term.lower(), "$options": "i"}}
            ).limit(limit).sort("name", 1))
        except Exception as e:
            print(f"Error en search_items: {e}")
            return []
    
    def get_item_info(self, item_identifier: str):
        """Obtiene información detallada de un item"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return None
        
        try:
            if item_identifier.isdigit():
                return self.items.find_one({"_id": ObjectId(item_identifier)})
            else:
                return self.items.find_one({"name_lower": item_identifier.lower()})
        except Exception as e:
            print(f"Error en get_item_info: {e}")
            return None
    
    def get_user_stats(self, discord_id: int):
        """Obtiene estadísticas del usuario"""
        if self.db is None:  # CORREGIDO: Comparar con None
            return {"unique_items": 0, "total_units": 0}
        
        user_id = str(discord_id)
        try:
            unique_items = self.inventories.count_documents({"user_id": user_id})
            
            pipeline = [
                {"$match": {"user_id": user_id}},
                {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
            ]
            result = list(self.inventories.aggregate(pipeline))
            total_units = result[0]["total"] if result else 0
            
            return {
                "unique_items": unique_items,
                "total_units": total_units
            }
        except Exception as e:
            print(f"Error en get_user_stats: {e}")
            return {"unique_items": 0, "total_units": 0}

# Inicializar MongoDB
db = MongoDB()

# ========== EVENTOS DEL BOT ==========
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'👥 Conectado a {len(bot.guilds)} servidores')
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="t!help"
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

# ========== COMANDO HELP ==========
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
            name="🎒 **Mochila/Inventario**",
            value="`t!mochila add <item>` - Añadir item\n"
                  "`t!mochila remove <item>` - Remover item\n"
                  "`t!mochila show` - Ver inventario\n"
                  "`t!mochila search <item>` - Buscar item\n"
                  "`t!mochila info <item>` - Info de item",
            inline=False
        )
        
        embed.add_field(
            name="🎮 **Diversión**",
            value="`t!golpe @usuario` - Golpear a alguien\n"
                  "`t!choose op1, op2` - Elegir entre opciones\n"
                  "`t!pokemon <nombre>` - Info de Pokémon\n"
                  "`t!moves <pokemon> [nivel]` - Movimientos Pokémon",
            inline=False
        )
        
        embed.add_field(
            name="⚙️ **Utilidad**",
            value="`t!help` - Muestra esta ayuda\n"
                  "`t!ping` - Ver latencia del bot\n"
                  "`t!serverinfo` - Info del servidor",
            inline=False
        )
        
        await ctx.send(embed=embed)

# ========== COMANDOS DE MOCHILA/INVENTARIO ==========
@bot.command(name='mochila', aliases=['inv', 'inventory', 'bag'])
async def mochila(ctx, accion: str = None, *, args: str = None):
    """Sistema de mochila/inventario"""
    
    if not accion:
        # Mostrar ayuda de mochila
        embed = discord.Embed(
            title="🎒 Comandos de Mochila",
            description="**Uso:** `t!mochila <accion> [argumentos]`",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="➕ **add** <nombre> [x<cantidad>]",
            value="Añade items a tu mochila\n`t!mochila add espada x3`",
            inline=False
        )
        
        embed.add_field(
            name="➖ **remove** <nombre/id> [x<cantidad>]",
            value="Remueve items de tu mochila\n`t!mochila remove espada`",
            inline=False
        )
        
        embed.add_field(
            name="📋 **show** [página]",
            value="Muestra todos tus items\n`t!mochila show 2`",
            inline=False
        )
        
        embed.add_field(
            name="🔍 **search** <nombre>",
            value="Busca items por nombre\n`t!mochila search oro`",
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ **info** <nombre/id>",
            value="Muestra info de un item\n`t!mochila info 123abc`",
            inline=False
        )
        
        embed.add_field(
            name="📊 **stats**",
            value="Muestra tus estadísticas\n`t!mochila stats`",
            inline=False
        )
        
        await ctx.send(embed=embed)
        return
    
    accion = accion.lower()
    
    if accion == "add":
        await mochila_add(ctx, args)
    elif accion == "remove":
        await mochila_remove(ctx, args)
    elif accion == "show":
        await mochila_show(ctx, args)
    elif accion == "search":
        await mochila_search(ctx, args)
    elif accion == "info":
        await mochila_info(ctx, args)
    elif accion == "stats":
        await mochila_stats(ctx)
    else:
        await ctx.send("❌ Acción no válida. Usa `t!mochila` para ver opciones.")

async def mochila_add(ctx, args: str):
    """Añade items a la mochila"""
    if not args:
        await ctx.send("❌ Uso: `t!mochila add <nombre> [x<cantidad>]`")
        return
    
    # Parsear argumentos
    cantidad = 1
    match = re.search(r'x(\d+)$', args, re.IGNORECASE)
    
    if match:
        cantidad = int(match.group(1))
        item_name = args[:match.start()].strip()
    else:
        item_name = args.strip()
    
    if not item_name:
        await ctx.send("❌ Debes especificar el nombre del item")
        return
    
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        # Añadir a la base de datos
        result = db.add_item(ctx.author.id, item_name, cantidad)
        
        if "error" in result:
            await ctx.send(f"❌ {result['error']}")
            return
        
        # Crear embed de confirmación
        embed = discord.Embed(
            title="✅ Item añadido",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name=f"📦 {item_name}",
            value=f"**Cantidad añadida:** +{cantidad}",
            inline=False
        )
        
        # Obtener cantidad actual
        inventory_item = db.inventories.find_one({
            "user_id": str(ctx.author.id),
            "item_id": str(result['item']['_id'])
        })
        
        if inventory_item:
            embed.add_field(
                name="📊 Total actual",
                value=f"×{inventory_item['quantity']}",
                inline=True
            )
        
        embed.set_footer(text=f"Añadido por {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def mochila_remove(ctx, args: str):
    """Remueve items de la mochila"""
    if not args:
        await ctx.send("❌ Uso: `t!mochila remove <nombre/id> [x<cantidad>]`")
        return
    
    # Parsear argumentos
    cantidad = 1
    match = re.search(r'x(\d+)$', args, re.IGNORECASE)
    
    if match:
        cantidad = int(match.group(1))
        item_input = args[:match.start()].strip()
    else:
        item_input = args.strip()
    
    if not item_input:
        await ctx.send("❌ Debes especificar el nombre o ID del item")
        return
    
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        # Remover de la base de datos
        result = db.remove_item(ctx.author.id, item_input, cantidad)
        
        if "error" in result:
            await ctx.send(f"❌ {result['error']}")
            return
        
        # Crear embed de confirmación
        embed = discord.Embed(
            title="➖ Item removido",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name=f"📦 {result['item']['name']}",
            value=f"**Cantidad removida:** -{cantidad}",
            inline=False
        )
        
        if result['result'] == "eliminado":
            embed.add_field(name="📝 Estado", value="✅ Eliminado completamente", inline=True)
        else:
            embed.add_field(name="📝 Estado", value=f"📊 {result['result']}", inline=True)
        
        embed.set_footer(text=f"Removido por {ctx.author.display_name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def mochila_show(ctx, args: str = None):
    """Muestra el inventario del usuario"""
    page = 1
    if args and args.isdigit():
        page = int(args)
    
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        # Obtener inventario paginado
        inventory_data = db.get_inventory(ctx.author.id, page, limit=10)
        
        if not inventory_data["items"]:
            embed = discord.Embed(
                title="🎒 Tu mochila está vacía",
                description="Usa `t!mochila add <item>` para añadir items",
                color=discord.Color.light_grey()
            )
            await ctx.send(embed=embed)
            return
        
        # Crear embed
        embed = discord.Embed(
            title=f"🎒 Mochila de {ctx.author.display_name}",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        # Estadísticas
        stats = db.get_user_stats(ctx.author.id)
        embed.description = f"**Página {inventory_data['current_page']}/{inventory_data['total_pages']}**"
        embed.add_field(
            name="📊 Estadísticas",
            value=f"**Items únicos:** {stats['unique_items']}\n**Total unidades:** {stats['total_units']}",
            inline=False
        )
        
        # Lista de items
        items_text = []
        for item_data in inventory_data["items"]:
            inv_data = item_data["inventory_data"]
            quantity = inv_data.get("quantity", 1)
            item_name = inv_data.get("item_name", "Desconocido")
            items_text.append(f"• **{item_name}** ×{quantity}")
        
        if items_text:
            embed.add_field(
                name=f"📦 Items ({len(items_text)} mostrados)",
                value="\n".join(items_text),
                inline=False
            )
        
        # Paginación
        if inventory_data["total_pages"] > 1:
            next_page = inventory_data['current_page'] + 1
            if next_page <= inventory_data['total_pages']:
                embed.set_footer(text=f"Usa t!mochila show {next_page} para la siguiente página")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def mochila_search(ctx, args: str):
    """Busca items por nombre"""
    if not args:
        await ctx.send("❌ Uso: `t!mochila search <nombre>`")
        return
    
    if len(args) < 2:
        await ctx.send("❌ El término de búsqueda debe tener al menos 2 caracteres")
        return
    
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        items = db.search_items(args, limit=15)
        
        if not items:
            embed = discord.Embed(
                title="🔍 Búsqueda sin resultados",
                description=f"No se encontraron items con '{args}'",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"🔍 Resultados para: {args}",
            description=f"Encontrados: {len(items)} items",
            color=discord.Color.blue()
        )
        
        # Agrupar items para mostrar
        items_list = []
        for item in items[:10]:  # Mostrar máximo 10
            items_list.append(f"• **{item['name']}**")
        
        embed.add_field(
            name="📦 Items encontrados",
            value="\n".join(items_list) if items_list else "No hay resultados",
            inline=False
        )
        
        if len(items) > 10:
            embed.set_footer(text=f"Mostrando 10 de {len(items)} resultados. Sé más específico.")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def mochila_info(ctx, args: str):
    """Muestra información de un item"""
    if not args:
        await ctx.send("❌ Uso: `t!mochila info <nombre/id>`")
        return
    
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        item = db.get_item_info(args)
        
        if not item:
            await ctx.send(f"❌ Item '{args}' no encontrado")
            return
        
        # Crear embed
        embed = discord.Embed(
            title=f"📦 {item.get('name', 'Desconocido')}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        # Información básica
        embed.add_field(name="🆔 ID", value=f"`{item['_id']}`", inline=True)
        
        if "created_at" in item:
            fecha = item["created_at"].strftime("%d/%m/%Y") if hasattr(item["created_at"], 'strftime') else item["created_at"]
            embed.add_field(name="📅 Creado", value=fecha, inline=True)
        
        # Verificar si el usuario actual lo tiene
        user_item = db.inventories.find_one({
            "user_id": str(ctx.author.id),
            "item_id": str(item["_id"])
        })
        
        if user_item:
            embed.add_field(name="📦 Tú tienes", value=f"×{user_item['quantity']}", inline=True)
        
        embed.set_footer(text="Usa t!mochila add/remove para gestionar este item")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def mochila_stats(ctx):
    """Muestra estadísticas del usuario"""
    # CORREGIDO: Usar db.db is None en lugar de db.db
    if db.db is None:
        await ctx.send("❌ La base de datos no está disponible")
        return
    
    try:
        stats = db.get_user_stats(ctx.author.id)
        
        # Obtener top 5 items
        top_items = list(db.inventories.find(
            {"user_id": str(ctx.author.id)}
        ).sort("quantity", -1).limit(5))
        
        embed = discord.Embed(
            title=f"📊 Estadísticas de {ctx.author.display_name}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        # Estadísticas principales
        embed.add_field(
            name="📈 General",
            value=f"**Items únicos:** {stats['unique_items']}\n**Total unidades:** {stats['total_units']}",
            inline=False
        )
        
        # Top items
        if top_items:
            top_text = []
            for i, item in enumerate(top_items, 1):
                item_details = db.get_item_info(item['item_id'])
                item_name = item_details['name'] if item_details else item['item_id']
                top_text.append(f"{i}. **{item_name}** ×{item['quantity']}")
            
            embed.add_field(
                name="🏆 Top 5 Items",
                value="\n".join(top_text),
                inline=False
            )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

# ========== COMANDOS DE DIVERSIÓN ==========
@bot.command(name='golpe', aliases=['punch', 'hit'])
async def golpe(ctx, user: discord.Member = None):
    """Golpea a un usuario mencionado"""
    if not user:
        await ctx.send("❌ Debes mencionar a alguien para golpear. Ejemplo: `t!golpe @usuario`")
        return
    
    if user == ctx.author:
        await ctx.send("🤕 No te golpees a ti mismo...")
        return
    
    gifs = [
        "https://media.giphy.com/media/l1J9HWBKLp20YfNAY/giphy.gif",
        "https://media.giphy.com/media/xUNd9HZq1itMkiK652/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/3o7abAHdYvZdBNnGZq/giphy.gif"
    ]
    
    embed = discord.Embed(
        color=discord.Color.red(),
        timestamp=ctx.message.created_at
    )
    
    embed.set_author(
        name=f"👊 {ctx.author.display_name} golpeó a {user.display_name}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url
    )
    
    embed.set_image(url=random.choice(gifs))
    embed.set_footer(text="¡Golpe crítico!")
    
    await ctx.send(embed=embed)

@bot.command(name='choose', aliases=['elegir', 'decidir'])
async def choose(ctx, *, opciones: str = None):
    """Elige entre múltiples opciones separadas por comas"""
    if not opciones:
        await ctx.send("❌ Necesitas proporcionar opciones. Ejemplo: `t!choose pizza, hamburguesa, sushi`")
        return
    
    # Dividir opciones por comas y limpiar
    lista_opciones = [opcion.strip() for opcion in opciones.split(',') if opcion.strip()]
    
    if len(lista_opciones) < 2:
        await ctx.send("❌ Necesitas al menos 2 opciones. Ejemplo: `t!choose pizza, hamburguesa`")
        return
    
    if len(lista_opciones) > 20:
        await ctx.send("❌ Demasiadas opciones. Máximo 20 opciones.")
        return
    
    eleccion = random.choice(lista_opciones)
    
    embed = discord.Embed(
        title="🎯 Decisión tomada",
        description=f"De entre **{len(lista_opciones)}** opciones...",
        color=discord.Color.blue(),
        timestamp=ctx.message.created_at
    )
    
    embed.add_field(
        name="La opción elegida es:",
        value=f"**{eleccion}**",
        inline=False
    )
    
    embed.add_field(
        name="Opciones consideradas:",
        value="\n".join([f"• {op}" for op in lista_opciones]),
        inline=False
    )
    
    embed.set_footer(text=f"Pedido por {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

# ========== COMANDOS POKÉMON ==========
async def get_pokemon_data(pokemon_name: str):
    """Obtiene datos de un Pokémon desde la PokeAPI"""
    url = f"https://pokeapi.co/api/v2/pokemon/{pokemon_name.lower()}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.json()
            return None

@bot.command(name='pokemon', aliases=['poke', 'pokedex'])
async def pokemon_info(ctx, *, pokemon: str):
    """Muestra información de un Pokémon"""
    if not pokemon:
        await ctx.send("❌ Debes especificar un Pokémon. Ejemplo: `t!pokemon pikachu`")
        return
    
    try:
        msg = await ctx.send("🔍 Buscando en la Pokédex...")
        
        data = await get_pokemon_data(pokemon)
        
        if not data:
            await msg.edit(content=f"❌ Pokémon '{pokemon}' no encontrado")
            return
        
        pokemon_name = data['name'].title()
        pokemon_id = data['id']
        
        # Obtener tipos
        types = [t['type']['name'].title() for t in data['types']]
        
        # Obtener estadísticas
        stats = {stat['stat']['name']: stat['base_stat'] for stat in data['stats']}
        
        embed = discord.Embed(
            title=f"#{pokemon_id:03d} {pokemon_name}",
            color=discord.Color.green()
        )
        
        # Imagen del Pokémon
        embed.set_thumbnail(url=data['sprites']['front_default'])
        
        # Información básica
        embed.add_field(name="📊 Tipos", value=", ".join(types), inline=True)
        embed.add_field(name="📏 Altura", value=f"{data['height'] / 10:.1f} m", inline=True)
        embed.add_field(name="⚖️ Peso", value=f"{data['weight'] / 10:.1f} kg", inline=True)
        
        # Estadísticas principales
        stats_text = f"**HP:** {stats.get('hp', 0)}\n"
        stats_text += f"**Ataque:** {stats.get('attack', 0)}\n"
        stats_text += f"**Defensa:** {stats.get('defense', 0)}\n"
        stats_text += f"**A. Especial:** {stats.get('special-attack', 0)}\n"
        stats_text += f"**D. Especial:** {stats.get('special-defense', 0)}\n"
        stats_text += f"**Velocidad:** {stats.get('speed', 0)}\n"
        stats_text += f"**Total:** {sum(stats.values())}"
        
        embed.add_field(name="📈 Estadísticas Base", value=stats_text, inline=True)
        
        # Movimientos aprendidos por nivel (primeros 5)
        level_moves = []
        for move_entry in data['moves'][:8]:
            for version in move_entry['version_group_details']:
                if version['move_learn_method']['name'] == 'level-up':
                    level = version['level_learned_at']
                    move_name = move_entry['move']['name'].replace('-', ' ').title()
                    level_moves.append(f"Nivel {level}: {move_name}")
                    break
        
        if level_moves:
            embed.add_field(
                name="🎮 Primeros Movimientos",
                value="\n".join(level_moves[:5]),
                inline=True
            )
        
        embed.set_footer(text="Pokémon data from PokeAPI.co")
        
        await msg.edit(content=None, embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name='moves', aliases=['movimientos', 'movs'])
async def pokemon_moves(ctx, pokemon: str, nivel_max: int = 100):
    """Muestra los movimientos que un Pokémon aprende hasta cierto nivel"""
    if not pokemon:
        await ctx.send("❌ Debes especificar un Pokémon. Ejemplo: `t!moves pikachu 15`")
        return
    
    if nivel_max < 1 or nivel_max > 100:
        await ctx.send("❌ El nivel debe estar entre 1 y 100")
        return
    
    try:
        msg = await ctx.send("🔍 Consultando movimientos...")
        
        data = await get_pokemon_data(pokemon)
        
        if not data:
            await msg.edit(content=f"❌ Pokémon '{pokemon}' no encontrado")
            return
        
        # Filtrar movimientos por nivel
        moves = []
        for move_entry in data['moves']:
            for version in move_entry['version_group_details']:
                if version['move_learn_method']['name'] == 'level-up':
                    level = version['level_learned_at']
                    if level <= nivel_max:
                        move_name = move_entry['move']['name'].replace('-', ' ').title()
                        moves.append((level, move_name))
                        break
        
        if not moves:
            await msg.edit(content=f"❌ {data['name'].title()} no aprende movimientos por nivel hasta el nivel {nivel_max}")
            return
        
        # Ordenar y agrupar
        moves.sort(key=lambda x: x[0])
        
        # Crear lista formateada
        pokemon_name = data['name'].title()
        output = [f"**🎮 Movimientos de {pokemon_name} (hasta nivel {nivel_max}):**\n"]
        
        current_level = None
        level_moves = []
        
        for level, move_name in moves:
            if level != current_level:
                if level_moves:
                    output.append(f"**Nivel {current_level}:** {', '.join(level_moves)}")
                current_level = level
                level_moves = [move_name]
            else:
                level_moves.append(move_name)
        
        if level_moves:
            output.append(f"**Nivel {current_level}:** {', '.join(level_moves)}")
        
        # Enviar en partes si es muy largo
        message = "\n".join(output)
        
        if len(message) > 2000:
            # Dividir en partes
            parts = []
            current_part = ""
            for line in output:
                if len(current_part) + len(line) + 1 > 2000:
                    parts.append(current_part)
                    current_part = line + "\n"
                else:
                    current_part += line + "\n"
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts, 1):
                if i == 1:
                    await msg.edit(content=part)
                else:
                    await ctx.send(f"**Continuación...**\n{part}")
        else:
            await msg.edit(content=message)
            
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

# ========== COMANDOS DE UTILIDAD ==========
@bot.command(name='ping')
async def ping(ctx):
    """Muestra la latencia del bot"""
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Latencia:** {latency}ms",
        color=discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 300 else discord.Color.red()
    )
    
    embed.set_footer(text=f"Solicitado por {ctx.author.display_name}")
    
    await ctx.send(embed=embed)

@bot.command(name='serverinfo', aliases=['server'])
async def server_info(ctx):
    """Muestra información del servidor"""
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"📊 {guild.name}",
        color=discord.Color.blurple(),
        timestamp=ctx.message.created_at
    )
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="👑 Dueño", value=guild.owner.mention, inline=True)
    embed.add_field(name="🌍 Región", value=str(guild.preferred_locale).title(), inline=True)
    embed.add_field(name="📅 Creado", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    
    embed.add_field(name="👥 Miembros", value=str(guild.member_count), inline=True)
    embed.add_field(name="💬 Canales", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="😀 Emojis", value=str(len(guild.emojis)), inline=True)
    
    embed.add_field(name="🛡️ Nivel de verificación", value=str(guild.verification_level).title(), inline=True)
    embed.add_field(name="🎨 Boost Nivel", value=guild.premium_tier, inline=True)
    embed.add_field(name="🚀 Boosts", value=guild.premium_subscription_count, inline=True)
    
    embed.set_footer(text=f"ID: {guild.id}")
    
    await ctx.send(embed=embed)

# ========== COMANDO DE PRUEBA CON GIF PERSONALIZADO ==========
CANAL_ORIGEN_ID = 1447369197091815554  # Cambia esto por el ID de tu canal

@bot.command(name='prueba', aliases=['gif'])
async def prueba_gif(ctx, user: discord.Member = None, *, argumentos: str = None):
    """
    Comando de prueba con GIF personalizado
    Uso: t!prueba [@usuario] [titulo: texto] [texto: descripción]
    """
    canal_origen = bot.get_channel(CANAL_ORIGEN_ID)
    
    if not canal_origen:
        await ctx.send("⚠️ Canal origen no configurado")
        return
    
    # Parsear argumentos
    usuario_objetivo = user
    titulo = ""
    texto = ""
    
    if argumentos:
        # Buscar título: y texto:
        if "titulo:" in argumentos.lower():
            inicio = argumentos.lower().find("titulo:") + 7
            if "texto:" in argumentos.lower():
                fin = argumentos.lower().find("texto:")
                titulo = argumentos[inicio:fin].strip()
            else:
                titulo = argumentos[inicio:].strip()
        
        if "texto:" in argumentos.lower():
            inicio = argumentos.lower().find("texto:") + 6
            texto = argumentos[inicio:].strip()
    
    try:
        # Buscar último mensaje del usuario
        ultimo_msg = None
        async for msg in canal_origen.history(limit=50):
            if msg.author.id == ctx.author.id:
                ultimo_msg = msg
                break
        
        if not ultimo_msg:
            await ctx.send("❌ No tienes mensajes en el canal origen")
            return
        
        # Obtener URL de la imagen
        imagen_url = None
        
        # Buscar en adjuntos
        if ultimo_msg.attachments:
            for adjunto in ultimo_msg.attachments:
                if any(adjunto.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                    imagen_url = adjunto.url
                    break
        
        # Buscar en contenido
        if not imagen_url and ultimo_msg.content:
            urls = re.findall(r'https?://\S+', ultimo_msg.content)
            for url in urls:
                if any(ext in url.lower() for ext in ['.gif', '.gifv', '.png', '.jpg', '.jpeg', '.webp']):
                    imagen_url = url
                    break
        
        if not imagen_url:
            await ctx.send("❌ No se encontró imagen/GIF en tu mensaje")
            return
        
        # Crear embed
        embed = discord.Embed(color=discord.Color.red())
        
        # Solo agregar título si se proporcionó
        if titulo:
            embed.title = titulo
        elif usuario_objetivo:
            embed.title = f"👊 {ctx.author.display_name} → {usuario_objetivo.display_name}"
        
        # Solo agregar texto si se proporcionó
        if texto:
            embed.description = texto
        
        # Imagen siempre
        embed.set_image(url=imagen_url)
        
        # Footer mínimo
        embed.set_footer(text=f"Por {ctx.author.name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ========== COMANDOS DE ADMINISTRACIÓN ==========
@bot.command(name='clear', aliases=['limpiar'])
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, cantidad: int = 10):
    """Elimina una cantidad específica de mensajes (Admin only)"""
    if cantidad < 1 or cantidad > 100:
        await ctx.send("❌ La cantidad debe estar entre 1 y 100")
        return
    
    deleted = await ctx.channel.purge(limit=cantidad + 1)  # +1 para incluir el comando
    
    embed = discord.Embed(
        title="🗑️ Mensajes eliminados",
        description=f"Se eliminaron {len(deleted)-1} mensajes",
        color=discord.Color.green()
    )
    
    msg = await ctx.send(embed=embed, delete_after=5)


#====================================================================================================================================
#====================================================================================================================================
#====================================================================================================================================
#====================================================================================================================================

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

# ========== CONFIGURACIÓN INICIAL ==========
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
# S: 3%, A: 7%, B: 10%, C: 20%, Recursos: 60%
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

# ========== BASE DE DATOS ==========
class GameDatabase:
    def __init__(self):
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client.discord_game
        self.players = self.db.players
        self.characters = self.db.characters
        self.monsters = self.db.monsters
        self.items = self.db.items
        self.battles = self.db.battles
        
        # Inicializar personajes en la base de datos
        self.initialize_characters()
        
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

# Inicializar base de datos
db = GameDatabase()

# ========== TAREAS AUTOMÁTICAS ==========
@tasks.loop(hours=24)
async def reset_daily_tasks():
    """Resetea los usos diarios cada 24 horas"""
    db.reset_daily_uses()
    print("✅ Usos diarios reseteados")

@tasks.loop(hours=48)
async def full_recovery_task():
    """Cura completamente a todos los jugadores cada 48 horas"""
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

# ... (el resto del código se mantiene igual, solo añadiendo los comandos nuevos)

# ========== EVENTOS DEL BOT ==========
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'👥 Conectado a {len(bot.guilds)} servidores')
    
    # Estadísticas
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

#====================================================================================================================================
#====================================================================================================================================
#====================================================================================================================================
#====================================================================================================================================

# ========== PARA RENDER ==========
# Importar y configurar el webserver para mantener el bot activo
try:
    from webserver import keep_alive
    keep_alive()
    print("🌐 Servidor web iniciado para Render")
except ImportError:
    print("⚠️ No se encontró webserver.py, funcionando sin servidor web")

# ========== INICIAR EL BOT ==========
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR: No se encontró DISCORD_TOKEN")
        print("💡 Asegúrate de tener un archivo .env con DISCORD_TOKEN=tu_token")
        exit(1)
    
    print("🤖 Iniciando bot de Discord...")
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        print("❌ ERROR: Token de Discord inválido")
        print("💡 Verifica tu token en el archivo .env")
    except Exception as e:
        print(f"❌ ERROR: {e}")











