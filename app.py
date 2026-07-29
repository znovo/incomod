import discord
from discord.ext import commands
import random
import asyncio
import time
from groq import Groq
from collections import defaultdict
import os
from dotenv import load_dotenv
import json

load_dotenv()
memory = defaultdict(list)
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=";", intents=intents)
bots_perm = {
    1492235531034300627,
    1488997116788346941,
    1512433101723271200
}
MAX_MSG = 50          # limite máximo de mensagens
DELAY = 2             # segundos entre mensagens
conversation_count = defaultdict(int)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
agent_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=agent_api_key)
is_evil_mode = False
active_chats = {}
memory = defaultdict(list)
with open("system_prompt.md", "r", encoding="utf-8") as f:
    system_prompt_normal = f.read()


async def chat_with_ai(historico):
    messages = [
        {
            "role": "system",
            "content": system_prompt_normal
        }
    ]

    messages.extend(historico)

    try:
        def generate():
            print("mensagens", messages)

            chat_completion = client.chat.completions.create(
                model="qwen/qwen3.6-27b",
                messages=messages,
                max_completion_tokens=800,
                response_format={"type": "json_object"},
                temperature=1.0,
                reasoning_effort="none",
            )

            response = chat_completion.choices[0].message.content or "{}"

            dados = json.loads(response)

            think = dados.get("think", "")
            answer = dados.get("final_text", "")
            tool = dados.get("tool")
            print("-----------------------------------------------------------------------")
            print("Think:", think)
            print("Answer:", answer)
            if isinstance(tool, dict):
                name = tool.get("name")
                arguments = tool.get("arguments", {})

                if name:
                    print("Tool:", name)
                    print("Arguments:", arguments)
                    # executar ferramenta aqui

            return answer

        return await asyncio.to_thread(generate)

    except json.JSONDecodeError as e:
        print("Erro ao interpretar JSON:", e)
        return "A IA retornou um JSON inválido."

    except Exception as e:
        print("Erro na geração:", e)
        return "Ocorreu um erro na API da Groq."

@bot.event
async def on_ready():
    print("O bot iniciou!")
@bot.event
async def on_message(msg):

    if msg.author.bot and msg.author.id not in bots_perm:
        return
    is_dm = isinstance(msg.channel, discord.DMChannel)
    mentioned = bot.user in msg.mentions
    if conversation_count[msg.channel.id] > 10:
        return
    chat_active = False


    if msg.channel.id in active_chats:
        if time.time() - active_chats[msg.channel.id] < 120:
            chat_active = True



    if not is_dm and not mentioned and not chat_active:
        return


    user_id = str(msg.author.id)
    if msg.content.startswith(bot.command_prefix):
        await bot.process_commands(msg)
        return
    # Remove a menção do texto
    content = msg.content.replace(
        f"<@{bot.user.id}>", ""
    ).replace(
        f"<@!{bot.user.id}>", ""
    ).strip()
    # Adiciona mensagem do usuário ao histórico
    channel_id = str(msg.channel.id)

    memory[channel_id].append({
        "role": "user",
        "content": f"{msg.author.name}: {content}"
    })
        # Limita memória
    memory[channel_id] = memory[channel_id][-20:]

    response = await chat_with_ai(
        memory[channel_id]
    )
    active_chats[msg.channel.id] = time.time()
    conversation_count[msg.channel.id] += 1
    # Salva resposta
    memory[channel_id].append({
        "role": "assistant",
        "content": response
    })  
    await msg.reply(response, mention_author=False)
@bot.command()
async def falar(ctx: commands.Context, *, texto):
    await ctx.send(texto)

@bot.command()
@commands.has_permissions(manage_roles=True)
async def ttp(ctx: commands.Context, escolha: str):
    nome_cargo = "viado supremo"
    if ctx.guild is None:
        await ctx.send("Use isso em um servidor.")
        return

    num_bot = random.randint(1, 3)
    choices = {1: "papel", 2: "tesoura", 3: "pedra"}
    bot_choice = choices[num_bot]
    user_choice = escolha.lower()


    cargo = discord.utils.get(ctx.guild.roles, name=nome_cargo)

    if cargo is None:
        cargo = await ctx.guild.create_role(name=nome_cargo)
        await ctx.send(f"Cargo '{nome_cargo}' criado.")

    if user_choice not in ["pedra", "papel", "tesoura"]:
        await ctx.send("Escolha inválida.")
        return

    await ctx.send(f"Escolhi **{bot_choice}** e você escolheu **{user_choice}**.")

    if bot_choice == user_choice:
        await ctx.send("Empate")
    elif (
        (bot_choice == "papel" and user_choice == "pedra") or
        (bot_choice == "tesoura" and user_choice == "papel") or
        (bot_choice == "pedra" and user_choice == "tesoura")
    ):
        await ctx.send("Você perdeu")
    else:
        await ctx.send("Você ganhou")
        membro = ctx.author  # agora existe
        await membro.add_roles(cargo) # type: ignore
        await ctx.send(f"{membro.mention} como recomepensa voce recebeu o cargo '{nome_cargo}'.")
        await cargo.edit(color=discord.Color.blue())

@bot.command()
async def soma(ctx: commands.Context, num1, num2):
    try:
        resultado = float(num1) + float(num2)
        await ctx.send(f"A soma de {num1} e {num2} é {resultado}")
    except:
        await ctx.send("Erro ao calcular a soma.")


@bot.command()
async def incomodar(ctx: commands.Context, user: discord.User, *, msg):
    try:
        await ctx.send(f"Vou enviar mensagens para {user.name}")
        for _ in range(MAX_MSG):
            await user.send(msg)
            await asyncio.sleep(DELAY)

        await ctx.send(f"Enviei {MAX_MSG} mensagens com segurança.")
    except Exception:
        await ctx.send("Não consegui enviar a mensagem (DM fechada ou erro).")

bot.run(DISCORD_TOKEN)
