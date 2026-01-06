@bot.command(name='say', aliases=['decir', 'hablar'])
async def say(ctx, *, mensaje: str = None):
    """
    Haz que el bot diga algo (elimina tu mensaje)
    Uso: t!say <mensaje>
    Ejemplo: t!say ¡Hola a todos!
    """
    
    # Verificar si hay mensaje
    if not mensaje:
        await ctx.send("❌ Debes escribir un mensaje. Ejemplo: `t!say ¡Hola!`", delete_after=10)
        return
    
    # Verificar longitud del mensaje
    if len(mensaje) > 2000:
        await ctx.send("❌ El mensaje es demasiado largo (máximo 2000 caracteres)", delete_after=10)
        return
    
    try:
        # Intentar eliminar el mensaje del usuario
        await ctx.message.delete()
        
    except discord.Forbidden:
        # El bot no tiene permisos para eliminar mensajes
        embed = discord.Embed(
            description="⚠️ **Nota:** No pude eliminar tu mensaje (falta permiso).",
            color=discord.Color.orange()
        )
        warning_msg = await ctx.send(embed=embed, delete_after=5)
        
        # Enviar el mensaje después
        await asyncio.sleep(2)  # Pequeña pausa
        await ctx.send(mensaje)
        
    except discord.NotFound:
        # El mensaje ya fue eliminado
        await ctx.send(mensaje)
        
    except Exception as e:
        # Error inesperado
        print(f"Error en comando say: {e}")
        await ctx.send("❌ Ocurrió un error al procesar el comando", delete_after=5)
        await ctx.send(mensaje)  # Aún envía el mensaje
        
    else:
        # Si se eliminó correctamente, enviar el mensaje
        await ctx.send(mensaje)










