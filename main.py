import discord
from discord.ext import commands
import requests
import os
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
import webserver
import asyncio

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix = "t!",intents=intents)

@bot.command(aliases=["decir", "hablar"], name='say', help='Envía un mensaje y borra el comando original.')
async def say(ctx, *, mensaje: str):
    try:
        # Borrar el mensaje del usuario
        await ctx.message.delete()
        # Enviar el mensaje
        await ctx.send(mensaje)
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para borrar mensajes o enviar mensajes aquí.", delete_after=5)

#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------

#CONFIGURACION DE BASE DE DATOS SQL---------------------------------------
import sqlite3
import discord
from datetime import datetime
import os

# Configurar base de datos
DB_PATH = "inventario.db"

def init_database():
    """Inicializa la base de datos si no existe"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabla de usuarios
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id TEXT UNIQUE NOT NULL,
        nombre TEXT,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabla de items (global)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        descripcion TEXT,
        emoji TEXT DEFAULT '📦',
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Tabla de inventario (relación usuario-item)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventario (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        cantidad INTEGER DEFAULT 1,
        obtenido_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (usuario_id) REFERENCES usuarios (id),
        FOREIGN KEY (item_id) REFERENCES items (id),
        UNIQUE(usuario_id, item_id)
    )
    ''')
    
    conn.commit()
    conn.close()

# Inicializar BD al inicio
init_database()
#CONFIGURACION DE BASE DE DATOS SQL---------------------------------------

#FUNCIONES DE BASE DE DATOS------------------------------------------------
def get_db_connection():
    """Obtiene conexión a la base de datos"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
    return conn

def get_or_create_usuario(discord_id: str, nombre: str):
    """Obtiene o crea un usuario en la BD"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM usuarios WHERE discord_id = ?", (discord_id,))
    usuario = cursor.fetchone()
    
    if not usuario:
        cursor.execute(
            "INSERT INTO usuarios (discord_id, nombre) VALUES (?, ?)",
            (discord_id, nombre)
        )
        usuario_id = cursor.lastrowid
    else:
        usuario_id = usuario[0]
    
    conn.commit()
    conn.close()
    return usuario_id

def get_item_id(nombre: str, create_if_not_exists=True):
    """Obtiene el ID de un item, lo crea si no existe"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM items WHERE LOWER(nombre) = LOWER(?)", (nombre,))
    item = cursor.fetchone()
    
    if item:
        item_id = item[0]
    elif create_if_not_exists:
        cursor.execute(
            "INSERT INTO items (nombre, descripcion) VALUES (?, ?)",
            (nombre, f"Item: {nombre}")
        )
        item_id = cursor.lastrowid
    else:
        item_id = None
    
    conn.commit()
    conn.close()
    return item_id

def get_item_by_id(item_id: int):
    """Obtiene información de un item por ID"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    
    conn.close()
    return dict(item) if item else None
#FUNCIONES DE BASE DE DATOS------------------------------------------------

@bot.command(name='mochila', aliases=['inv', 'inventory', 'bag'])
async def mochila(ctx, accion: str = None, *, argumentos: str = None):
    """
    Sistema de inventario con base de datos
    """
    
    if not accion:
        # Mostrar ayuda
        embed = discord.Embed(
            title="🎒 Sistema de Mochila",
            description="**Comandos disponibles:**",
            color=discord.Color.blue()
        )
        
        comandos = [
            ("add <item> [xN]", "Añade items a tu mochila"),
            ("remove <item/id> [xN]", "Remueve items de tu mochila"),
            ("show [página]", "Muestra tu inventario"),
            ("info <item/id>", "Información detallada de un item"),
            ("search <nombre>", "Busca items por nombre"),
            ("give @usuario <item> [xN]", "Da items a otro usuario")
        ]
        
        for cmd, desc in comandos:
            embed.add_field(name=f"`!mochila {cmd}`", value=desc, inline=False)
        
        await ctx.send(embed=embed)
        return
    
    accion = accion.lower()
    
    if accion == "add":
        await add_item_db(ctx, argumentos)
    elif accion == "remove":
        await remove_item_db(ctx, argumentos)
    elif accion == "show":
        await show_inventory_db(ctx, argumentos)
    elif accion == "info":
        await item_info_db(ctx, argumentos)
    elif accion == "search":
        await search_items(ctx, argumentos)
    elif accion == "give":
        await give_item(ctx, argumentos)
    else:
        await ctx.send("❌ Comando no reconocido. Usa `!mochila` para ayuda.")

async def add_item_db(ctx, args: str = None):
    """Añade items a la mochila usando base de datos"""
    if not args:
        await ctx.send("❌ Uso: `!mochila add <nombre> [x<cantidad>]`")
        return
    
    # Parsear argumentos
    cantidad = 1
    nombre_item = args
    
    # Buscar patrón xN
    import re
    match = re.search(r'x(\d+)$', args, re.IGNORECASE)
    if match:
        cantidad = int(match.group(1))
        nombre_item = args[:match.start()].strip()
    
    if not nombre_item:
        await ctx.send("❌ Debes especificar el nombre del item")
        return
    
    # Obtener usuario
    usuario_id = get_or_create_usuario(str(ctx.author.id), ctx.author.name)
    
    # Obtener o crear item
    item_id = get_item_id(nombre_item, create_if_not_exists=True)
    
    if not item_id:
        await ctx.send("❌ Error al crear/obtener el item")
        return
    
    # Añadir o actualizar en inventario
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Verificar si ya tiene el item
    cursor.execute(
        "SELECT id, cantidad FROM inventario WHERE usuario_id = ? AND item_id = ?",
        (usuario_id, item_id)
    )
    inventario = cursor.fetchone()
    
    if inventario:
        # Actualizar cantidad
        nueva_cantidad = inventario['cantidad'] + cantidad
        cursor.execute(
            "UPDATE inventario SET cantidad = ? WHERE id = ?",
            (nueva_cantidad, inventario['id'])
        )
    else:
        # Insertar nuevo
        cursor.execute(
            "INSERT INTO inventario (usuario_id, item_id, cantidad) VALUES (?, ?, ?)",
            (usuario_id, item_id, cantidad)
        )
        nueva_cantidad = cantidad
    
    conn.commit()
    
    # Obtener info del item
    cursor.execute("SELECT nombre, emoji FROM items WHERE id = ?", (item_id,))
    item_info = cursor.fetchone()
    
    conn.close()
    
    # Enviar confirmación
    embed = discord.Embed(
        title="✅ Item añadido",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name=f"{item_info['emoji']} {item_info['nombre']}",
        value=f"**ID:** `{item_id}`\n**Cantidad añadida:** +{cantidad}\n**Total:** {nueva_cantidad}",
        inline=False
    )
    
    await ctx.send(embed=embed)

async def remove_item_db(ctx, args: str = None):
    """Remueve items de la mochila"""
    if not args:
        await ctx.send("❌ Uso: `!mochila remove <nombre/id> [x<cantidad>]`")
        return
    
    # Parsear argumentos
    cantidad = 1
    input_item = args
    
    # Buscar patrón xN
    import re
    match = re.search(r'x(\d+)$', args, re.IGNORECASE)
    if match:
        cantidad = int(match.group(1))
        input_item = args[:match.start()].strip()
    
    if not input_item:
        await ctx.send("❌ Debes especificar el nombre o ID del item")
        return
    
    # Obtener usuario
    usuario_id = get_or_create_usuario(str(ctx.author.id), ctx.author.name)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Determinar si es ID o nombre
    item_id = None
    if input_item.isdigit():
        # Es un ID
        item_id = int(input_item)
        cursor.execute("SELECT id FROM items WHERE id = ?", (item_id,))
        if not cursor.fetchone():
            await ctx.send(f"❌ No existe un item con ID `{item_id}`")
            conn.close()
            return
    else:
        # Es un nombre
        cursor.execute("SELECT id FROM items WHERE LOWER(nombre) = LOWER(?)", (input_item,))
        item = cursor.fetchone()
        if not item:
            await ctx.send(f"❌ No existe un item llamado `{input_item}`")
            conn.close()
            return
        item_id = item[0]
    
    # Verificar si tiene el item
    cursor.execute(
        "SELECT id, cantidad FROM inventario WHERE usuario_id = ? AND item_id = ?",
        (usuario_id, item_id)
    )
    inventario = cursor.fetchone()
    
    if not inventario:
        await ctx.send("❌ No tienes ese item en tu mochila")
        conn.close()
        return
    
    # Verificar cantidad
    cantidad_actual = inventario['cantidad']
    
    if cantidad_actual < cantidad:
        await ctx.send(f"❌ Solo tienes {cantidad_actual} de ese item")
        conn.close()
        return
    
    # Calcular nueva cantidad
    nueva_cantidad = cantidad_actual - cantidad
    
    if nueva_cantidad <= 0:
        # Eliminar del inventario
        cursor.execute("DELETE FROM inventario WHERE id = ?", (inventario['id'],))
        mensaje = "Item eliminado completamente"
    else:
        # Actualizar cantidad
        cursor.execute(
            "UPDATE inventario SET cantidad = ? WHERE id = ?",
            (nueva_cantidad, inventario['id'])
        )
        mensaje = f"Quedan: {nueva_cantidad}"
    
    conn.commit()
    
    # Obtener info del item
    cursor.execute("SELECT nombre, emoji FROM items WHERE id = ?", (item_id,))
    item_info = cursor.fetchone()
    
    conn.close()
    
    # Enviar confirmación
    embed = discord.Embed(
        title="➖ Item removido",
        color=discord.Color.orange()
    )
    
    embed.add_field(
        name=f"{item_info['emoji']} {item_info['nombre']}",
        value=f"**ID:** `{item_id}`\n**Removidos:** -{cantidad}\n**Resultado:** {mensaje}",
        inline=False
    )
    
    await ctx.send(embed=embed)

async def show_inventory_db(ctx, args: str = None):
    """Muestra el inventario del usuario"""
    # Obtener usuario
    usuario_id = get_or_create_usuario(str(ctx.author.id), ctx.author.name)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Contar total de items
    cursor.execute(
        """
        SELECT COUNT(*) as total_items, SUM(i.cantidad) as total_unidades
        FROM inventario i
        WHERE i.usuario_id = ?
        """,
        (usuario_id,)
    )
    stats = cursor.fetchone()
    
    if not stats or stats['total_items'] == 0:
        embed = discord.Embed(
            title="🎒 Tu mochila está vacía",
            description="Usa `!mochila add <item>` para empezar",
            color=discord.Color.light_grey()
        )
        await ctx.send(embed=embed)
        conn.close()
        return
    
    # Paginación
    pagina = 1
    if args and args.isdigit():
        pagina = int(args)
    
    items_por_pagina = 10
    offset = (pagina - 1) * items_por_pagina
    
    # Obtener items con paginación
    cursor.execute(
        """
        SELECT i.id, it.nombre, it.emoji, i.cantidad, it.id as item_id
        FROM inventario i
        JOIN items it ON i.item_id = it.id
        WHERE i.usuario_id = ?
        ORDER BY it.nombre
        LIMIT ? OFFSET ?
        """,
        (usuario_id, items_por_pagina, offset)
    )
    
    items = cursor.fetchall()
    
    # Calcular total de páginas
    total_paginas = (stats['total_items'] + items_por_pagina - 1) // items_por_pagina
    
    conn.close()
    
    # Crear embed
    embed = discord.Embed(
        title=f"🎒 Mochila de {ctx.author.display_name}",
        color=discord.Color.purple()
    )
    
    # Estadísticas
    embed.add_field(
        name="📊 Estadísticas",
        value=f"**Items únicos:** {stats['total_items']}\n**Total unidades:** {stats['total_unidades']}",
        inline=False
    )
    
    # Lista de items
    if items:
        items_text = []
        for item in items:
            items_text.append(f"{item['emoji']} **{item['nombre']}** (ID: `{item['item_id']}`) ×{item['cantidad']}")
        
        embed.add_field(
            name=f"📦 Items (Página {pagina}/{total_paginas})",
            value="\n".join(items_text),
            inline=False
        )
    
    # Navegación
    if total_paginas > 1:
        embed.set_footer(text=f"Usa !mochila show {pagina+1} para la siguiente página")
    
    await ctx.send(embed=embed)

async def item_info_db(ctx, args: str = None):
    """Muestra información detallada de un item"""
    if not args:
        await ctx.send("❌ Uso: `!mochila info <nombre/id>`")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Buscar item
    item_id = None
    if args.isdigit():
        item_id = int(args)
        cursor.execute("SELECT * FROM items WHERE id = ?", (item_id,))
    else:
        cursor.execute("SELECT * FROM items WHERE LOWER(nombre) = LOWER(?)", (args,))
    
    item = cursor.fetchone()
    
    if not item:
        await ctx.send("❌ Item no encontrado")
        conn.close()
        return
    
    item_id = item['id']
    
    # Contar cuántos usuarios tienen este item
    cursor.execute(
        "SELECT COUNT(DISTINCT usuario_id) as total_usuarios, SUM(cantidad) as total_existencia FROM inventario WHERE item_id = ?",
        (item_id,)
    )
    stats = cursor.fetchone()
    
    # Verificar si el usuario actual lo tiene
    usuario_id = get_or_create_usuario(str(ctx.author.id), ctx.author.name)
    cursor.execute(
        "SELECT cantidad FROM inventario WHERE usuario_id = ? AND item_id = ?",
        (usuario_id, item_id)
    )
    user_has = cursor.fetchone()
    
    conn.close()
    
    # Crear embed
    embed = discord.Embed(
        title=f"{item['emoji']} {item['nombre']}",
        description=item['descripcion'] or "Sin descripción",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="🆔 ID", value=f"`{item['id']}`", inline=True)
    embed.add_field(name="📅 Creado", value=item['creado_en'][:10], inline=True)
    
    if stats['total_existencia']:
        embed.add_field(name="🌍 En el mundo", value=f"{stats['total_existencia']} unidades", inline=False)
        embed.add_field(name="👥 Dueños", value=f"{stats['total_usuarios']} usuarios", inline=True)
    
    if user_has:
        embed.add_field(name="📦 Tú tienes", value=f"×{user_has['cantidad']}", inline=True)
    
    await ctx.send(embed=embed)

async def search_items(ctx, args: str = None):
    """Busca items en el sistema"""
    if not args:
        await ctx.send("❌ Uso: `!mochila search <nombre>`")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT * FROM items WHERE LOWER(nombre) LIKE LOWER(?) ORDER BY nombre LIMIT 10",
        (f"%{args}%",)
    )
    
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        embed = discord.Embed(
            title="🔍 Búsqueda sin resultados",
            description=f"No se encontraron items con `{args}`",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(
        title=f"🔍 Resultados para: {args}",
        color=discord.Color.blue()
    )
    
    for item in items:
        embed.add_field(
            name=f"{item['emoji']} {item['nombre']}",
            value=f"ID: `{item['id']}`",
            inline=True
        )
    
    await ctx.send(embed=embed)

async def give_item(ctx, args: str = None):
    """Da items a otro usuario"""
    if not args:
        await ctx.send("❌ Uso: `!mochila give @usuario <item> [x<cantidad>]`")
        return
    
    if not ctx.message.mentions:
        await ctx.send("❌ Debes mencionar a un usuario")
        return
    
    target_user = ctx.message.mentions[0]
    if target_user.bot:
        await ctx.send("❌ No puedes dar items a bots")
        return
    
    if target_user.id == ctx.author.id:
        await ctx.send("❌ No puedes darte items a ti mismo")
        return
    
    # Parsear argumentos restantes
    import re
    args_text = args.replace(f'<@{target_user.id}>', '').replace(f'<@!{target_user.id}>', '').strip()
    
    cantidad = 1
    nombre_item = args_text
    
    # Buscar patrón xN
    match = re.search(r'x(\d+)$', args_text, re.IGNORECASE)
    if match:
        cantidad = int(match.group(1))
        nombre_item = args_text[:match.start()].strip()
    
    if not nombre_item:
        await ctx.send("❌ Debes especificar el item a dar")
        return
    
    # Verificar que el remitente tenga el item
    usuario_id = get_or_create_usuario(str(ctx.author.id), ctx.author.name)
    target_id = get_or_create_usuario(str(target_user.id), target_user.name)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Buscar item por nombre o ID
    item_id = None
    if nombre_item.isdigit():
        item_id = int(nombre_item)
    else:
        cursor.execute("SELECT id FROM items WHERE LOWER(nombre) = LOWER(?)", (nombre_item,))
        item = cursor.fetchone()
        if item:
            item_id = item[0]
    
    if not item_id:
        await ctx.send("❌ Item no encontrado")
        conn.close()
        return
    
    # Verificar que el remitente tiene suficiente
    cursor.execute(
        "SELECT id, cantidad FROM inventario WHERE usuario_id = ? AND item_id = ?",
        (usuario_id, item_id)
    )
    sender_inv = cursor.fetchone()
    
    if not sender_inv or sender_inv['cantidad'] < cantidad:
        await ctx.send("❌ No tienes suficientes items para dar")
        conn.close()
        return
    
    # Transferir items
    # 1. Remover del remitente
    nueva_cantidad_sender = sender_inv['cantidad'] - cantidad
    if nueva_cantidad_sender <= 0:
        cursor.execute("DELETE FROM inventario WHERE id = ?", (sender_inv['id'],))
    else:
        cursor.execute(
            "UPDATE inventario SET cantidad = ? WHERE id = ?",
            (nueva_cantidad_sender, sender_inv['id'])
        )
    
    # 2. Añadir al receptor
    cursor.execute(
        "SELECT id, cantidad FROM inventario WHERE usuario_id = ? AND item_id = ?",
        (target_id, item_id)
    )
    target_inv = cursor.fetchone()
    
    if target_inv:
        nueva_cantidad_target = target_inv['cantidad'] + cantidad
        cursor.execute(
            "UPDATE inventario SET cantidad = ? WHERE id = ?",
            (nueva_cantidad_target, target_inv['id'])
        )
    else:
        cursor.execute(
            "INSERT INTO inventario (usuario_id, item_id, cantidad) VALUES (?, ?, ?)",
            (target_id, item_id, cantidad)
        )
    
    conn.commit()
    
    # Obtener info del item
    cursor.execute("SELECT nombre, emoji FROM items WHERE id = ?", (item_id,))
    item_info = cursor.fetchone()
    
    conn.close()
    
    # Enviar confirmación
    embed = discord.Embed(
        title="🎁 Transferencia completada",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name=f"{item_info['emoji']} {item_info['nombre']}",
        value=f"**Cantidad:** ×{cantidad}\n**De:** {ctx.author.mention}\n**Para:** {target_user.mention}",
        inline=False
    )
    
    await ctx.send(embed=embed)

#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
@bot.event
async def on_ready():
    print("Success: Bot is connected to Discord")

webserver.keep_alive()

bot.run(DISCORD_TOKEN)

