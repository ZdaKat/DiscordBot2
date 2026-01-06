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








