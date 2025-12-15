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

@bot.event
async def on_ready():
    print("Success: Bot is connected to Discord")

webserver.keep_alive()

bot.run(DISCORD_TOKEN)
