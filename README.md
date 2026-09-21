# Incomod Bot

Um bot para Discord com personalidade configurável e integração com modelos de IA.

O projeto combina comandos tradicionais do Discord com respostas geradas por IA usando a API da Groq e modelos locais via Ollama.

> Este projeto foi criado para fins de aprendizado, experimentação e entretenimento.

## Recursos

* Conversas contextuais com memória por canal
* Respostas automáticas quando mencionado
* Suporte a mensagens diretas (DM)
* Integração com a API da Groq
* Suporte a modelos locais usando Ollama
* Personalidade configurável através de variáveis de ambiente
* Sistema de comandos personalizados
* Histórico recente de conversas para manter contexto

## Tecnologias utilizadas

* Python 3.11+
* discord.py
* Groq API
* python-dotenv

## Instalação

Clone o repositório:

```bash
git clone https://github.com/znovo/incomod-bot.git
cd incomod-bot
```

Crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative o ambiente virtual:

### Windows

```bash
.venv\Scripts\activate
```

### Linux e macOS

```bash
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

## Configuração

Crie um arquivo chamado `.env` na raiz do projeto:

```env
DISCORD_TOKEN=seu_token_aqui
GROQ_API_KEY=sua_chave_aqui
```

Nunca envie o arquivo `.env` para o GitHub.

crie um arquivo md chamado system_prompt e coloque a personalidade do bot dentro dele ou apague a parte .example do arquivo system_prompt.example.md.

## Executando o bot

```bash
python main.py
```

Quando o bot iniciar corretamente, você verá uma mensagem semelhante a:

```text
O bot iniciou!
```

## Comandos disponíveis

| Comando                      | Descrição                                          |
| ---------------------------- | -------------------------------------------------- |
| `;falar <texto>`             | Faz o bot enviar uma mensagem                      |
| `;soma <n1> <n2>`            | Soma dois números                                  |
| `;incomodar <id> <mensagem>`  | envia 50 mensagens na dm do id escolhido (configuravel)|
| `;ttp <pedra/papel/tesoura>` | Jogo de pedra, papel e tesoura                     |
| `mencionar o bot ou conversar via dm` | resposta conforme a personalidade |
## Estrutura do projeto

```text
.
├── app.py
├── system_prompt_example.md
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md

```

## Segurança

* Nunca compartilhe seu token do Discord.
* Nunca compartilhe suas chaves de API.
* Mantenha o arquivo `.env` fora do GitHub.
* Caso uma credencial seja exposta, gere uma nova imediatamente.

## Hospedagem

O bot pode ser executado localmente ou hospedado em plataformas como Railway, Render ou em uma VPS.

Para hospedar, configure as variáveis de ambiente diretamente na plataforma escolhida.

## Mental Loop e memória estruturada

O Mental Loop é iniciado no `on_ready()` e executa em intervalo configurável. Ele observa atividade já disponível no cache do bot, escolhe entre uma ação segura e `do_nothing`, aplica cooldowns e só então entrega a ação ao executor do Discord.

Variáveis opcionais:

```env
MENTAL_LOOP_ENABLED=true
MENTAL_LOOP_DRY_RUN=true
MENTAL_LOOP_INTERVAL=60
```

Use `MENTAL_LOOP_DRY_RUN=true` para validar decisões e logs sem enviar mensagens. DM, servidor, usuário e ação possuem cooldowns separados, além do cooldown global.

A memória persistente continua em `memory.json`, mas agora é organizada por fatos, preferências, relações, eventos, interesses e opiniões. Cada item possui tipo, confiança, origem, datas e status. O carregamento migra automaticamente o formato antigo.

## Arquitetura

```text
app.py
├── memory/       extração, validação, migração e repositório JSON
├── social/       estatísticas observáveis do grafo social
├── mental/       intenções, decisão, cooldowns e loop periódico
└── actions/      validação final e chamadas de envio do Discord
```

O LLM não recebe acesso direto à API do Discord e não pode inventar IDs. O Decision Engine produz dados; o Action Executor valida objetos em cache, permissões, mensagens e usuários antes de executar.

## Testes

Execute:

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

Os testes cobrem migração e consolidação de memória, rejeição de mensagens triviais, confiança, `do_nothing`, cooldowns e execução em modo dry-run.

## Aviso

Este projeto deve ser utilizado de forma responsável e respeitando os Termos de Serviço do Discord.

Evite implementar funcionalidades que possam causar spam, assédio ou abuso da plataforma.

## Licença

Este projeto está disponível sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
