import discord
from discord.ext import commands
from database import db
from datetime import datetime
from bson import ObjectId

class AdminMochila(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(name='admininv', aliases=['adminmochila'])
    @commands.has_permissions(administrator=True)
    async def admininv(self, ctx):
        """Comandos de administración del inventario"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="⚙️ Admin - Sistema de Mochila",
                color=discord.Color.dark_blue()
            )
            
            comandos = [
                ("view @usuario", "Ver inventario de otro usuario"),
                ("additem <nombre>", "Crear nuevo item global"),
                ("edititem <id> <nuevo_nombre>", "Editar nombre de item"),
                ("deleteitem <id>", "Eliminar item global"),
                ("reset @usuario", "Resetear inventario de usuario"),
                ("stats", "Estadísticas del sistema")
            ]
            
            for cmd, desc in comandos:
                embed.add_field(name=f"`!admininv {cmd}`", value=desc, inline=False)
            
            await ctx.send(embed=embed)
    
    @admininv.command(name='view')
    async def admin_view(self, ctx, member: discord.Member):
        """Ver inventario de otro usuario"""
        try:
            inventory_data = db.get_user_inventory(member.id, page=1, limit=20)
            
            if not inventory_data["items"]:
                embed = discord.Embed(
                    title=f"🎒 Inventario de {member.display_name}",
                    description="*Está vacío*",
                    color=discord.Color.light_grey()
                )
                await ctx.send(embed=embed)
                return
            
            # Crear embed
            embed = discord.Embed(
                title=f"👑 Inventario de {member.display_name}",
                color=discord.Color.dark_gold()
            )
            
            # Items
            items_text = []
            for item_data in inventory_data["items"]:
                inv_data = item_data["inventory_data"]
                items_text.append(f"• **{inv_data['item_name']}** ×{inv_data['quantity']}")
            
            embed.add_field(
                name=f"📦 Items ({len(items_text)})",
                value="\n".join(items_text) if items_text else "No hay items",
                inline=False
            )
            
            # Estadísticas
            stats = db.get_user_stats(member.id)
            embed.set_footer(text=f"Items únicos: {stats['unique_items']} | Total unidades: {stats['total_units']}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @admininv.command(name='additem')
    async def admin_add_item(self, ctx, *, item_name: str):
        """Crear un nuevo item global"""
        try:
            # Verificar si ya existe
            existing = db.items.find_one({"name_lower": item_name.lower()})
            if existing:
                await ctx.send(f"❌ El item '{item_name}' ya existe (ID: `{existing['_id']}`)")
                return
            
            # Crear item
            item = db.items.insert_one({
                "name": item_name,
                "name_lower": item_name.lower(),
                "created_at": datetime.utcnow(),
                "created_by": str(ctx.author.id),
                "admin_created": True
            })
            
            embed = discord.Embed(
                title="✅ Item global creado",
                description=f"**Nombre:** {item_name}\n**ID:** `{item.inserted_id}`",
                color=discord.Color.green()
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @admininv.command(name='edititem')
    async def admin_edit_item(self, ctx, item_id: str, *, new_name: str):
        """Editar el nombre de un item global"""
        try:
            # Buscar item
            item = db.items.find_one({"_id": ObjectId(item_id)})
            if not item:
                await ctx.send(f"❌ Item con ID `{item_id}` no encontrado")
                return
            
            # Verificar si el nuevo nombre ya existe
            existing = db.items.find_one({"name_lower": new_name.lower()})
            if existing:
                await ctx.send(f"❌ Ya existe un item con el nombre '{new_name}'")
                return
            
            # Actualizar
            db.items.update_one(
                {"_id": ObjectId(item_id)},
                {"$set": {
                    "name": new_name,
                    "name_lower": new_name.lower(),
                    "updated_at": datetime.utcnow(),
                    "updated_by": str(ctx.author.id)
                }}
            )
            
            # Actualizar también en los inventarios
            db.inventories.update_many(
                {"item_id": item_id},
                {"$set": {"item_name": new_name}}
            )
            
            embed = discord.Embed(
                title="✅ Item actualizado",
                description=f"**Nuevo nombre:** {new_name}\n**ID:** `{item_id}`",
                color=discord.Color.blue()
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @admininv.command(name='deleteitem')
    async def admin_delete_item(self, ctx, item_id: str):
        """Eliminar un item global (y de todos los inventarios)"""
        try:
            # Buscar item
            item = db.items.find_one({"_id": ObjectId(item_id)})
            if not item:
                await ctx.send(f"❌ Item con ID `{item_id}` no encontrado")
                return
            
            # Confirmación
            embed = discord.Embed(
                title="⚠️ ¿Estás seguro?",
                description=f"Vas a eliminar el item **{item['name']}** (ID: `{item_id}`)\n\nEsta acción eliminará el item de TODOS los inventarios y no se puede deshacer.\n\nReacciona con ✅ para confirmar o ❌ para cancelar.",
                color=discord.Color.red()
            )
            
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "✅":
                    # Eliminar de items globales
                    db.items.delete_one({"_id": ObjectId(item_id)})
                    
                    # Eliminar de todos los inventarios
                    result = db.inventories.delete_many({"item_id": item_id})
                    
                    embed = discord.Embed(
                        title="✅ Item eliminado",
                        description=f"**Item:** {item['name']}\n**Eliminado de:** {result.deleted_count} inventarios",
                        color=discord.Color.green()
                    )
                    
                    await msg.edit(embed=embed)
                    
                else:
                    embed = discord.Embed(
                        title="❌ Operación cancelada",
                        color=discord.Color.orange()
                    )
                    await msg.edit(embed=embed)
                    
            except:
                embed = discord.Embed(
                    title="⏰ Tiempo agotado",
                    description="La operación fue cancelada por tiempo.",
                    color=discord.Color.orange()
                )
                await msg.edit(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @admininv.command(name='reset')
    async def admin_reset_inventory(self, ctx, member: discord.Member):
        """Resetear el inventario de un usuario"""
        try:
            # Confirmación
            embed = discord.Embed(
                title="⚠️ ¿Estás seguro?",
                description=f"Vas a resetear el inventario de **{member.display_name}**\n\nEsta acción eliminará TODOS sus items y no se puede deshacer.\n\nReacciona con ✅ para confirmar o ❌ para cancelar.",
                color=discord.Color.red()
            )
            
            msg = await ctx.send(embed=embed)
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            
            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == msg.id
            
            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
                
                if str(reaction.emoji) == "✅":
                    # Eliminar todos los items del usuario
                    result = db.inventories.delete_many({"user_id": str(member.id)})
                    
                    embed = discord.Embed(
                        title="✅ Inventario reseteado",
                        description=f"**Usuario:** {member.mention}\n**Items eliminados:** {result.deleted_count}",
                        color=discord.Color.green()
                    )
                    
                    await msg.edit(embed=embed)
                    
                else:
                    embed = discord.Embed(
                        title="❌ Operación cancelada",
                        color=discord.Color.orange()
                    )
                    await msg.edit(embed=embed)
                    
            except:
                embed = discord.Embed(
                    title="⏰ Tiempo agotado",
                    description="La operación fue cancelada por tiempo.",
                    color=discord.Color.orange()
                )
                await msg.edit(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @admininv.command(name='stats')
    async def system_stats(self, ctx):
        """Estadísticas del sistema"""
        try:
            # Total usuarios
            total_users = db.users.count_documents({})
            
            # Total items globales
            total_items = db.items.count_documents({})
            
            # Total registros en inventarios
            total_inventory_entries = db.inventories.count_documents({})
            
            # Total de unidades en todos los inventarios
            pipeline = [
                {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
            ]
            result = list(db.inventories.aggregate(pipeline))
            total_units = result[0]["total"] if result else 0
            
            # Items más populares
            pipeline = [
                {"$group": {"_id": "$item_id", "total": {"$sum": "$quantity"}}},
                {"$sort": {"total": -1}},
                {"$limit": 5}
            ]
            popular_items = list(db.inventories.aggregate(pipeline))
            
            embed = discord.Embed(
                title="📊 Estadísticas del Sistema",
                color=discord.Color.purple(),
                timestamp=datetime.utcnow()
            )
            
            # Datos generales
            embed.add_field(name="👥 Usuarios totales", value=str(total_users), inline=True)
            embed.add_field(name="📦 Tipos de items", value=str(total_items), inline=True)
            embed.add_field(name="📝 Registros", value=str(total_inventory_entries), inline=True)
            embed.add_field(name="🎒 Unidades totales", value=str(total_units), inline=True)
            
            # Items más populares
            if popular_items:
                popular_text = []
                for i, item in enumerate(popular_items, 1):
                    item_details = db.get_item_info(item["_id"])
                    item_name = item_details["name"] if item_details else item["_id"]
                    popular_text.append(f"{i}. **{item_name}** ×{item['total']}")
                
                embed.add_field(
                    name="🏆 Items más populares",
                    value="\n".join(popular_text),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

async def setup(bot):
    await bot.add_cog(AdminMochila(bot))
