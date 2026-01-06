import discord
from discord.ext import commands
import requests
import os
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
import webserver
import asyncio

#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------

import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# Cargar variables de entorno
load_dotenv()

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Crear bot con prefijo
bot = commands.Bot(command_prefix='t!', intents=intents)


# Evento cuando el bot está listo
@bot.event
async def on_ready():
    print(f'✅ Bot conectado como {bot.user}')
    print(f'👥 Conectado a {len(bot.guilds)} servidores')
    
    # Cambiar estado del bot
    await bot.change_presence(activity=discord.Game(name="!mochila"))

@bot.command(aliases=["decir", "hablar"], name='say', help='Envía un mensaje y borra el comando original.')
async def say(ctx, *, mensaje: str):
    try:
        # Borrar el mensaje del usuario
        await ctx.message.delete()
        # Enviar el mensaje
        await ctx.send(mensaje)
    except discord.Forbidden:
        await ctx.send("❌ No tengo permisos para borrar mensajes o enviar mensajes aquí.", delete_after=5)

# Manejo de errores
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Comando no encontrado. Usa `!mochila` para ver los comandos disponibles.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ No tienes permisos para ejecutar este comando.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Faltan argumentos. Revisa el uso del comando.")
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        # También puedes imprimir el error en la consola para debugging
        print(f"Error en comando {ctx.command}: {error}")

# Cargar los cogs
async def load_cogs():
    try:
        await bot.load_extension('mochila_cog')
        print('✅ Cog mochila_cog cargado')
    except Exception as e:
        print(f'❌ Error cargando mochila_cog: {e}')
    
    try:
        await bot.load_extension('admin_mochila_cog')
        print('✅ Cog admin_mochila_cog cargado')
    except Exception as e:
        print(f'❌ Error cargando admin_mochila_cog: {e}')

# Comando de prueba
@bot.command(name='ping')
async def ping(ctx):
    """Verifica la latencia del bot"""
    latency = round(bot.latency * 1000)
    await ctx.send(f'🏓 Pong! Latencia: {latency}ms')

# Comando para recargar cogs (solo para desarrollo)
@bot.command(name='reload')
@commands.is_owner()
async def reload_cogs(ctx):
    """Recarga todos los cogs (solo dueño del bot)"""
    try:
        await bot.reload_extension('mochila_cog')
        await bot.reload_extension('admin_mochila_cog')
        await ctx.send('✅ Todos los cogs recargados')
    except Exception as e:
        await ctx.send(f'❌ Error recargando cogs: {e}')


#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
#----------------ZONA DE COMANDOS POKE: MOCHILA-------------------
@bot.event
async def on_ready():
    print("Success: Bot is connected to Discord")

webserver.keep_alive()

bot.run(DISCORD_TOKEN)



