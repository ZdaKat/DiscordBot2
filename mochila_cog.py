import discord
from discord.ext import commands
import re
from datetime import datetime
from database import db  # Importamos nuestra clase MongoDB
from bson import ObjectId

class Mochila(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(name='mochila', aliases=['inv', 'inventory'], invoke_without_command=True)
    async def mochila(self, ctx):
        """Sistema de mochila/inventario"""
        embed = discord.Embed(
            title="🎒 Sistema de Mochila",
            description="**Comandos disponibles:**",
            color=discord.Color.blue()
        )
        
        comandos = [
            ("add <item> [xN]", "Añade items a tu mochila"),
            ("remove <item/id> [xN]", "Remueve items de tu mochila"),
            ("show [página]", "Muestra tu inventario"),
            ("search <nombre>", "Busca items por nombre"),
            ("info <item/id>", "Información de un item"),
            ("stats", "Tus estadísticas"),
            ("give @usuario <item> [xN]", "Da items a otro usuario")
        ]
        
        for cmd, desc in comandos:
            embed.add_field(name=f"`!mochila {cmd}`", value=desc, inline=False)
        
        await ctx.send(embed=embed)
    
    @mochila.command(name='add')
    async def add_item(self, ctx, *, args: str):
        """Añade items a tu mochila: !mochila add <nombre> [x<cantidad>]"""
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
        
        # Verificar límites
        if cantidad > 100:
            cantidad = 100
            await ctx.send("⚠️ Límite de 100 items por operación. Añadiendo 100.")
        
        if cantidad < 1:
            await ctx.send("❌ La cantidad debe ser al menos 1")
            return
        
        try:
            # Añadir a la base de datos
            result = db.add_item_to_inventory(ctx.author.id, item_name, cantidad)
            
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
                value=f"**Cantidad añadida:** +{cantidad}\n**ID del item:** `{result['item']['_id']}`",
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
    
    @mochila.command(name='remove', aliases=['delete', 'rm'])
    async def remove_item(self, ctx, *, args: str):
        """Remueve items de tu mochila: !mochila remove <nombre/id> [x<cantidad>]"""
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
        
        try:
            # Remover de la base de datos
            result = db.remove_item_from_inventory(ctx.author.id, item_input, cantidad)
            
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
                value=f"**Cantidad removida:** -{cantidad}\n**ID:** `{result['item']['_id']}`",
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
    
    @mochila.command(name='show', aliases=['view', 'list'])
    async def show_inventory(self, ctx, page: int = 1):
        """Muestra tu inventario: !mochila show [página]"""
        if page < 1:
            page = 1
        
        try:
            # Obtener inventario paginado
            inventory_data = db.get_user_inventory(ctx.author.id, page, limit=10)
            
            if not inventory_data["items"]:
                embed = discord.Embed(
                    title="🎒 Tu mochila está vacía",
                    description="Usa `!mochila add <item>` para añadir items",
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
            embed.description = f"**Página {page}/{inventory_data['total_pages']}**"
            embed.add_field(
                name="📊 Estadísticas",
                value=f"**Items únicos:** {stats['unique_items']}\n**Total unidades:** {stats['total_units']}",
                inline=False
            )
            
            # Lista de items
            items_text = []
            for item_data in inventory_data["items"]:
                inv_data = item_data["inventory_data"]
                item_details = item_data["item_details"]
                
                item_name = inv_data.get("item_name", "Desconocido")
                quantity = inv_data.get("quantity", 1)
                item_id = inv_data.get("item_id", "N/A")
                
                items_text.append(f"**{item_name}** (ID: `{item_id}`) ×{quantity}")
            
            if items_text:
                embed.add_field(
                    name=f"📦 Items ({len(items_text)} mostrados)",
                    value="\n".join(items_text),
                    inline=False
                )
            
            # Paginación
            if inventory_data["total_pages"] > 1:
                embed.set_footer(text=f"Usa !mochila show {page+1} para la siguiente página")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @mochila.command(name='search')
    async def search_items(self, ctx, *, search_term: str):
        """Busca items por nombre: !mochila search <nombre>"""
        if len(search_term) < 2:
            await ctx.send("❌ El término de búsqueda debe tener al menos 2 caracteres")
            return
        
        try:
            items = db.search_items(search_term, limit=15)
            
            if not items:
                embed = discord.Embed(
                    title="🔍 Búsqueda sin resultados",
                    description=f"No se encontraron items con '{search_term}'",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                return
            
            embed = discord.Embed(
                title=f"🔍 Resultados para: {search_term}",
                description=f"Encontrados: {len(items)} items",
                color=discord.Color.blue()
            )
            
            # Agrupar items para mostrar
            items_list = []
            for item in items[:10]:  # Mostrar máximo 10
                items_list.append(f"• **{item['name']}** (ID: `{item['_id']}`)")
            
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
    
    @mochila.command(name='info')
    async def item_info(self, ctx, *, item_identifier: str):
        """Muestra información de un item: !mochila info <nombre/id>"""
        try:
            item = db.get_item_info(item_identifier)
            
            if not item:
                await ctx.send(f"❌ Item '{item_identifier}' no encontrado")
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
            
            # Estadísticas del item
            # Contar cuántos usuarios tienen este item
            user_count = db.inventories.count_documents({"item_id": str(item["_id"])})
            embed.add_field(name="👥 Usuarios", value=str(user_count), inline=True)
            
            # Total de unidades en existencia
            pipeline = [
                {"$match": {"item_id": str(item["_id"])}},
                {"$group": {"_id": None, "total": {"$sum": "$quantity"}}}
            ]
            result = list(db.inventories.aggregate(pipeline))
            total_units = result[0]["total"] if result else 0
            embed.add_field(name="📊 En existencia", value=str(total_units), inline=True)
            
            # Verificar si el usuario actual lo tiene
            user_item = db.inventories.find_one({
                "user_id": str(ctx.author.id),
                "item_id": str(item["_id"])
            })
            
            if user_item:
                embed.add_field(name="📦 Tú tienes", value=f"×{user_item['quantity']}", inline=True)
            
            embed.set_footer(text="Usa !mochila add/remove para gestionar este item")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    @mochila.command(name='stats')
    async def user_stats(self, ctx, user: discord.Member = None):
        """Muestra tus estadísticas: !mochila stats [@usuario]"""
        target_user = user or ctx.author
        
        try:
            stats = db.get_user_stats(target_user.id)
            
            # Obtener top 5 items
            top_items = list(db.inventories.find(
                {"user_id": str(target_user.id)}
            ).sort("quantity", -1).limit(5))
            
            embed = discord.Embed(
                title=f"📊 Estadísticas de {target_user.display_name}",
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
    
    @mochila.command(name='give', aliases=['gift', 'transfer'])
    async def give_item(self, ctx, member: discord.Member, *, args: str):
        """Da items a otro usuario: !mochila give @usuario <item> [x<cantidad>]"""
        if member.bot:
            await ctx.send("❌ No puedes dar items a bots")
            return
        
        if member.id == ctx.author.id:
            await ctx.send("❌ No puedes darte items a ti mismo")
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
            await ctx.send("❌ Debes especificar el item a dar")
            return
        
        try:
            # Primero verificar que el remitente tiene el item
            sender_item = None
            
            # Buscar por ID o nombre
            item = db.get_item_info(item_input)
            if not item:
                await ctx.send(f"❌ Item '{item_input}' no encontrado")
                return
            
            sender_item = db.inventories.find_one({
                "user_id": str(ctx.author.id),
                "item_id": str(item["_id"])
            })
            
            if not sender_item:
                await ctx.send(f"❌ No tienes el item '{item['name']}'")
                return
            
            if sender_item["quantity"] < cantidad:
                await ctx.send(f"❌ No tienes suficientes. Tienes: {sender_item['quantity']}")
                return
            
            # Transferir
            # 1. Remover del remitente
            db.remove_item_from_inventory(ctx.author.id, str(item["_id"]), cantidad)
            
            # 2. Añadir al receptor
            db.add_item_to_inventory(member.id, item["name"], cantidad)
            
            # Crear embed de confirmación
            embed = discord.Embed(
                title="🎁 Transferencia completada",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            embed.add_field(
                name=f"📦 {item['name']}",
                value=f"**Cantidad:** ×{cantidad}",
                inline=False
            )
            
            embed.add_field(
                name="👤 De",
                value=ctx.author.mention,
                inline=True
            )
            
            embed.add_field(
                name="👉 Para",
                value=member.mention,
                inline=True
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")

async def setup(bot):
    await bot.add_cog(Mochila(bot))
