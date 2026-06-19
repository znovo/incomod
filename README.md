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
* Ollama
* python-dotenv

## Instalação

Clone o repositório:

```bash
git clone https://github.com/SEU_USUARIO/incomod-bot.git
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
SYSTEM_PROMPT=Seu prompt personalizado
```

Nunca envie o arquivo `.env` para o GitHub.

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
| `;ask <pergunta>`            | Gera uma resposta usando Ollama                    |
| `;groq <pergunta>`           | Gera uma resposta usando a API da Groq             |
| `;evil on/off`               | Ativa ou desativa modos especiais de comportamento |
| `;ttp <pedra/papel/tesoura>` | Jogo de pedra, papel e tesoura                     |

## Estrutura do projeto

```text
.
├── bot.py
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

## Aviso

Este projeto deve ser utilizado de forma responsável e respeitando os Termos de Serviço do Discord.

Evite implementar funcionalidades que possam causar spam, assédio ou abuso da plataforma.

## Licença

Este projeto está disponível sob a licença MIT. Consulte o arquivo `LICENSE` para mais informações.
