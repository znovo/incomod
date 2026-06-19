import discord
from discord.ext import commands
import random
import ollama
import asyncio
import time
from groq import Groq
from collections import defaultdict
import re
import os
from dotenv import load_dotenv

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

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
os.getenv("GROQ_API_KEY")
client = Groq(api_key=agent_api_key)
evil_mode = False
active_chats = {}
memory = defaultdict(list)

system_prompt_normal = os.getenv("SYSTEM_PROMPT")


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
            print("mensagens ", messages)
            chat_completion = client.chat.completions.create(
                model="qwen/qwen3-32b",
                messages=messages,
                max_completion_tokens=800,
                temperature=1.0,
            )
            response = chat_completion.choices[0].message.content

            match = re.search(
                r"<think>(.*?)</think>",
                response,
                flags=re.DOTALL
            )

            if match:
                print("\n=== REASONING ===")
                print(match.group(1))
                print("=================\n")

            response = re.sub(
                r"<think>.*?</think>",
                "",
                response,
                flags=re.DOTALL
            ).strip()

            return response

        return await asyncio.to_thread(generate)
    except Exception as e:
        print("a geraçao de mensagens com ia deu erro ", e)
        return "ocorreu um erro na api da groq"

@bot.event
async def on_ready():
    print("O bot iniciou!")
@bot.event
async def on_message(msg):
    conversation_count = defaultdict(int)
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
async def evil_mode(ctx: commands.Context, switch: str):
    global evil_mode

    if switch.lower() == "on":
        evil_mode = True
        await ctx.send("Modo evil ativado.")
    elif switch.lower() == "off":
        evil_mode = False
        await ctx.send("Modo evil desativado.")
    else:
        await ctx.send("Switch inválido. Use `;evil_mode on` ou `;evil_mode off`.")

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
        await ctx.send("irei enviar as mensagens para o usuario ", discord.user)
        for _ in range(MAX_MSG):
            await user.send(msg)
            await asyncio.sleep(DELAY)

        await ctx.send(f"Enviei {MAX_MSG} mensagens com segurança.")
    except Exception:
        await ctx.send("Não consegui enviar a mensagem (DM fechada ou erro).")

@bot.command()

async def ask(ctx: commands.Context, *, question):
    template = """SYSTEM:
Você é um bot do Discord chamado Incomod.
Sua função é responder as perguntas dos usuários zoando eles, sendo sarcástico, provocador e engraçado.
Você não precisa ser educado, mas deve evitar discurso de ódio, ameaças ou coisas ilegais.
Sempre mantenha o tom debochado, irônico e divertido.

Se você NÃO souber a resposta, admita isso claramente e não invente informações.
Evite respostas erradas — é melhor dizer que não sabe do que falar besteira.
"""

    try:
        await ctx.send("Respondendo...")
        inicio = time.time()

        resposta = await asyncio.to_thread(
            ollama.generate,
            model="gemma:2b",
            prompt=question,
            template=template,
            options={"temperature": 0.9, "max_tokens": 200}
        )

        texto = resposta.get("response", "").strip()
        tempo = time.time() - inicio

        await ctx.send(f"Resposta gerada em {tempo:.2f}s")
        await ctx.send(texto if texto else "Não consegui gerar uma resposta ")

    except Exception as e:
        await ctx.send(f"Erro ao gerar resposta: {e}")


@bot.command()
async def evil(ctx: commands.Context, switch: str):
    global evil_mode

    if switch.lower() == "on":
        evil_mode = True
        await ctx.send("Modo evil ativado.")
    elif switch.lower() == "off":
        evil_mode = False
        await ctx.send("Modo evil desativado.")
    else:
        await ctx.send("Switch inválido. Use `;evil on` ou `;evil off`.")


@bot.command()
async def groq(ctx: commands.Context, *, question):
    try:
        await ctx.send("Respondendo...")
        start = time.time()

        resposta = await asyncio.to_thread(chat_with_ai, question, evil_mode)

        end = time.time()
        await ctx.send(resposta)
        await ctx.send(f"Resposta gerada em {end - start:.2f}s")

    except Exception as e:
        await ctx.send(f"Erro ao gerar resposta: {e}")
bot.run(DISCORD_TOKEN)
