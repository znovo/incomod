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
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import tempfile
import logging
from threading import Lock

load_dotenv()

# configurar logging
logging.basicConfig(level=logging.INFO)


# Configuração de intents: reduz consumo e mantém apenas o necessário para ler mensagens.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False

bot = commands.Bot(command_prefix=";", intents=intents)

# Bots permitidos a interagir para evitar loops com outros bots desconhecidos.
bots_perm = {
    1492235531034300627,
    1488997116788346941,
    1512433101723271200
}

MAX_MSG = 50          # limite máximo de mensagens
DELAY = 2             # segundos entre mensagens
MEMORY_FILE = Path(__file__).parent / "memory.json"
MAX_USER_MEMORY_ITEMS = 8

# lock para proteger escrita concorrente em disco
save_lock = Lock()

# carregar variaveis de ambiente
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
agent_api_key = os.getenv("GROQ_API_KEY")
client = Groq(api_key=agent_api_key)


# memoria de curto prazo para cada canal, armazenando as últimas 20 mensagens
active_chats = {}
memory = defaultdict(list)
conversation_count = defaultdict(int)

# Memória de longo prazo persistida em arquivo.
long_term_memory = {
    "version": 1,
    "users": {},
    "servers": {}
}

def load_memory():
    # Carrega a memória persistida; se não existir, cria arquivo com estrutura padrão.
    global long_term_memory
    try:
        if not MEMORY_FILE.exists():
            save_memory()
            return

        with open(str(MEMORY_FILE), "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logging.warning("memory.json não contém um dict. Ignorando conteúdo.")
            return
        long_term_memory["version"] = data.get("version", 1)
        long_term_memory["users"] = data.get("users", {}) or {}
        long_term_memory["servers"] = data.get("servers", {}) or {}

    except (json.JSONDecodeError, OSError) as e:
        logging.exception("Falha ao carregar memory.json — usando memória padrão e regravando: %s", e)
        long_term_memory = {
            "version": 1,
            "users": {},
            "servers": {}
        }
        try:
            save_memory()
        except Exception:
            logging.exception("Falha ao regravar memory.json após erro de carga.")


def save_memory():
    # Salva em disco para sobreviver a reinícios da hospedagem.
    # Escrita atômica usando arquivo temporário e replace.
    dirpath = MEMORY_FILE.parent
    try:
        with save_lock:
            dirpath.mkdir(parents=True, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(dirpath), delete=False)
            try:
                json.dump(long_term_memory, tmp, ensure_ascii=False, indent=2)
                tmp.flush()
                os.fsync(tmp.fileno())
            finally:
                tmp.close()
            os.replace(tmp.name, str(MEMORY_FILE))
            logging.info("memory salvo em %s", MEMORY_FILE)
    except Exception:
        logging.exception("Falha ao salvar memory.json")


def get_server_data(server_id: str, server_name: str):
    # Garante que o servidor exista na memória de longo prazo.
    servers = long_term_memory["servers"]
    if server_id not in servers:
        servers[server_id] = {
            "name": server_name,
            "summary": "",
            "last_activity": hora_atual()
        }
    else:
        servers[server_id]["name"] = server_name
    return servers[server_id]


def get_user_data(user_id: str, user_name: str):
    # Garante que o usuário exista na memória de longo prazo.
    users = long_term_memory["users"]
    if user_id not in users:
        users[user_id] = {
            "name": user_name,
            "nickname": "",
            "memory": [],
            "bot_opinion": "",
            "last_seen": hora_atual(),
            "server_id": ""
        }
    else:
        users[user_id]["name"] = user_name
    return users[user_id]


def limit_memory(user_data: dict):
    # Mantém apenas os últimos itens para não crescer indefinidamente.
    user_data["memory"] = user_data.get("memory", [])[-MAX_USER_MEMORY_ITEMS:]


def update_last_seen(user_data: dict):
    # Atualiza o último momento em que o usuário interagiu com o bot.
    user_data["last_seen"] = hora_atual()


def update_user_memory(user_data: dict, info: str):
    # Salva fatos curtos relevantes e evita duplicatas simples.
    cleaned = info.strip()
    if not cleaned:
        return
    memories = user_data.setdefault("memory", [])
    if cleaned not in memories:
        memories.append(cleaned)
    limit_memory(user_data)


async def execute_extract_memory(user_data: dict, tool: dict, exact_text: str = ""):
    # Executa a tool extract_memory de forma assíncrona.
    args = tool.get("arguments", {})
    info = exact_text.strip() or args.get("info", "")
    update_user_memory(user_data, info)


async def execute_update_opinion(user_data: dict, tool: dict):
    # Executa a tool update_opinion de forma assíncrona.
    args = tool.get("arguments", {})
    opinion = args.get("opinion", "")
    if opinion:
        user_data["bot_opinion"] = opinion.strip()


async def process_tools_parallel(user_data: dict, tools_list, exact_text: str = ""):
    # Processa múltiplas tools em paralelo usando asyncio.gather().
    if not isinstance(tools_list, list):
        return
    tasks = []
    for tool in tools_list:
        if not isinstance(tool, dict):
            continue
        tool_name = tool.get("name")
        if tool_name == "extract_memory":
            tasks.append(execute_extract_memory(user_data, tool, exact_text=exact_text))
        elif tool_name == "update_opinion":
            tasks.append(execute_update_opinion(user_data, tool))
    if tasks:
        await asyncio.gather(*tasks)


def build_long_term_context(user_data: dict, server_data: dict):
    # Monta um bloco de contexto para enviar à IA junto do histórico curto.
    nickname = user_data.get("nickname") or "(sem apelido)"
    opinion = user_data.get("bot_opinion") or "(sem opinião)"
    memory_items = user_data.get("memory", [])
    memory_text = " | ".join(memory_items) if memory_items else "(sem memória)"

    return (
        f"Contexto de longo prazo:\n"
        f"Usuário: {user_data.get('name', '')}\n"
        f"Apelido: {nickname}\n"
        f"Opinião do bot: {opinion}\n"
        f"Última vez visto: {user_data.get('last_seen', '')}\n"
        f"Servidor: {server_data.get('name', '')}\n"
        f"Resumo do servidor: {server_data.get('summary', '') or '(sem resumo)'}\n"
        f"Memórias: {memory_text}"
    )




def hora_atual():
    # Padroniza data/hora no fuso de São Paulo.
    fuso_sp = ZoneInfo("America/Sao_Paulo")
    agora = datetime.now(fuso_sp).strftime("%Y-%m-%d %H:%M:%S")
    return agora


with open("system_prompt.md", "r", encoding="utf-8") as f:
    system_prompt_normal = f.read()

async def command_chat(mensagem, system_prompt, contexto=None):
    # Função assíncrona de chat com a IA, usada para comandos específicos.
    messages = [
        {
            "role": "system",
            "content": system_prompt
        }
    ]
    if contexto:
        messages.append({
            "role": "system",
            "content": f"Contexto: {contexto}"
        })
    messages.append({
        "role": "user",
        "content": mensagem
    })

    try:
        def generate():
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
            return dados

        return await asyncio.to_thread(generate)

    except json.JSONDecodeError as e:
        logging.exception("Erro ao interpretar JSON na command_chat: %s", e)
        return {"final_text": "A IA retornou um JSON inválido.", "tool": []}

    except Exception as e:
        logging.exception("Erro na geração (command_chat): %s", e)
        return {"final_text": "Ocorreu um erro na API da Groq.", "tool": []}



async def chat_with_ai(historico, long_term_context=""):
    # Combina prompt de sistema + hora atual + contexto longo + histórico recente.
    messages = [
        {
            "role": "system",
            "content": system_prompt_normal
        }
    ]
    messages.append({
        "role": "system",
        "content": f"Hora atual: {hora_atual()}"
    })
    if long_term_context:
        messages.append({
            "role": "system",
            "content": long_term_context
        })
    messages.extend(historico)

    try:
        def generate():
            # Chamada bloqueante da API fica em thread separada.
            logging.info("Enviando mensagens à API: %s", messages)
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
            logging.info("Think: %s", think)
            logging.info("Answer length: %d", len(answer or ""))
            if isinstance(tool, dict):
                name = tool.get("name")
                arguments = tool.get("arguments", {})
                if name:
                    logging.info("Tool detected: %s %s", name, arguments)

            return dados

        return await asyncio.to_thread(generate)

    except json.JSONDecodeError as e:
        logging.exception("Erro ao interpretar JSON (chat_with_ai): %s", e)
        return {"final_text": "A IA retornou um JSON inválido.", "tool": []}

    except Exception as e:
        logging.exception("Erro na geração (chat_with_ai): %s", e)
        return {"final_text": "Ocorreu um erro na API da Groq.", "tool": []}

@bot.event
async def on_ready():
    # Evento disparado quando o bot conecta ao Discord.
    load_memory()
    print("O bot iniciou!")
@bot.event
async def on_message(msg):
    # Filtro inicial para evitar respostas em massa e loops com bots.
    if conversation_count[msg.channel.id] > 10:
        return
    if msg.author.bot and msg.author.id not in bots_perm:
        return
    is_dm = isinstance(msg.channel, discord.DMChannel)
    mentioned = bot.user in msg.mentions
    if conversation_count[msg.channel.id] > 10:
        return
    chat_active = False

    now = time.time()
    # Limpeza de memória curta em RAM para controlar uso de recursos.
    if len(memory) > 100:
        oldest = next(iter(memory))
        del memory[oldest]
    expired = [
        cid
        for cid, t in active_chats.items()
        if now - t > 120
    ]

    for cid in expired:
        del active_chats[cid]
        conversation_count.pop(cid, None)
    if msg.channel.id in active_chats:
        if time.time() - active_chats[msg.channel.id] < 120:
            chat_active = True



    if not is_dm and not mentioned and not chat_active:
        return


    user_id = str(msg.author.id)
    # Contexto principal de memória longa: usuário e servidor.
    server_id = str(msg.guild.id) if msg.guild else "dm"
    server_name = msg.guild.name if msg.guild else "DM"
    user_data = get_user_data(user_id, msg.author.name)
    server_data = get_server_data(server_id, server_name)
    user_data["server_id"] = server_id
    update_last_seen(user_data)
    server_data["last_activity"] = hora_atual()

    if msg.content.startswith(bot.command_prefix):
        # Comandos são processados separadamente do fluxo de conversa com IA.
        await bot.process_commands(msg)
        save_memory()
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
    # Limita memória de curto prazo por canal.
    memory[channel_id] = memory[channel_id][-20:]

    long_term_context = build_long_term_context(user_data, server_data)

    response_data = await chat_with_ai(
        memory[channel_id],
        long_term_context
    )
    active_chats[msg.channel.id] = time.time()
    conversation_count[msg.channel.id] += 1
    # Extract final text and tools from the returned data (dict preferred).
    final_text = ""
    tools = []
    if isinstance(response_data, dict):
        final_text = response_data.get("final_text", "") or ""
        tools = response_data.get("tool", []) or []
    else:
        # Fallback: attempt to parse string content
        try:
            parsed = json.loads(str(response_data))
            final_text = parsed.get("final_text", "") or ""
            tools = parsed.get("tool", []) or []
        except Exception:
            final_text = str(response_data)

    # Salva resposta no histórico curto
    memory[channel_id].append({
        "role": "assistant",
        "content": final_text
    })

    # Processa tools da resposta e salva dados importantes em paralelo.
    try:
        if tools:
            await process_tools_parallel(user_data, tools, exact_text=content)
    except Exception:
        logging.exception("Erro ao processar tools")

    # Persiste mudanças da memória longa após responder.
    try:
        save_memory()
    except Exception:
        logging.exception("Falha ao salvar memória após processamento de mensagem")

    await msg.reply(final_text, mention_author=False)
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

@bot.command()
async def ameacar(ctx: commands.Context):
    membro = ctx.guild.members
    usuario = random.choice(membro)
    command_chat(f"Ameace o usuário de forma engraçada e leve, sem ofender ou ser agressivo com o usuario {usuario}.", system_prompt_normal)
    await ctx.send(f"{usuario.mention} você foi ameaçado!")
@bot.command()
async def cancelar(ctx: commands.context):
    membro = ctx.guild.members
    usuario = random.choice(membro)
    command_chat(f"gere um motivo de cancelamento engraçado com o {usuario}", system_prompt_normal)
    await ctx.send(f"{usuario.mention} você foi alvo de cancelamento!")
@bot.command()
async def fofoca(ctx: commands.Context):
    membro = ctx.guild.members
    usuario = random.choice(membro)
    command_chat(f"gere uma fofoca engraçada sobre o {usuario}", system_prompt_normal)
    await ctx.send(f"{usuario.mention} você foi alvo de fofoca!")
async def denuncia(ctx: commands.context):
    membro = ctx.guild.members
    usuario = random.choice(membro)
    command_chat(f"gere uma denuncia engraçada sobre o {usuario}", system_prompt_normal)
    await ctx.send(f"{usuario.mention} você foi alvo de uma denuncia!")


bot.run(DISCORD_TOKEN)
