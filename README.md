# paulinho-api

# Sistema de cobrança

Backend Django/DRF para vendas parceladas e empréstimos, com uma API JWT pronta para um front React mobile-first.

## Organização

`core/api/` é separado por domínio: `clientes`, `contratos`, `parcelas` e `cobrancas`. Cada módulo tem seus serializers, views, services e URLs; `core/urls.py` apenas os compõe. Os modelos permanecem juntos em `core/models.py` porque os contratos e parcelas são relações centrais do mesmo app Django e preservam a migração/banco já criado.

## Início rápido

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Produção

Use [`.env.example`](.env.example) apenas como referência. No Railway, cadastre cada variável no painel de ambiente; não faça upload do arquivo `.env`. Quando `DEBUG=false`, a aplicação bloqueia o boot se `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` ou `CSRF_TRUSTED_ORIGINS` estiverem ausentes/inseguros. HTTPS, HSTS, cookies seguros e o proxy TLS do Railway são habilitados automaticamente.

O login é `POST /api/auth/login/`. Crie usuários no Django Admin. Todas as rotas de dados exigem `Authorization: Bearer <access_token>`.

## Regras assumidas

- Empréstimo tradicional usa juros simples: `principal × (1 + taxa mensal × número de parcelas)`.
- Há um lembrete de WhatsApp por parcela atrasada.
- O resumo diário lista vencimentos de hoje e atrasados.

## Cron (Railway)

Execute diariamente: `python manage.py gerar_juros_mensais && python manage.py enviar_cobrancas_do_dia && python manage.py enviar_lembretes_atraso`.

Configure `DJANGO_SECRET_KEY`, `DEBUG=false`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE` e `OWNER_WHATSAPP` no Railway antes de habilitar os envios. A Evolution API fica desativada até configurar explicitamente uma URL, chave e instância próprias.

Para backup no S3, programe `python manage.py backup_database` no cron e configure `BACKUP_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` e `AWS_REGION`. O bucket aplica retenção/rotação por Lifecycle Rule (30 dias recomendado). A imagem Docker contém o serviço web; use um serviço/cron Railway separado para cada command.

## Publicação deste projeto

Railway usa a branch `main` de `879372/paulinho-api`. O Dockerfile executa `start.sh`, que aplica as migrações do banco próprio, cria o administrador inicial se solicitado e inicia Gunicorn na porta `$PORT` com IPv4/IPv6. Configure `DATABASE_URL`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` e `CSRF_TRUSTED_ORIGINS`. A API possui o endereço público https://gestao-web-production.up.railway.app; o frontend na Vercel encaminha os pedidos /api/ para ela. Não use `config.local` em produção.


## Lembretes automáticos de WhatsApp

O serviço Railway `lembretes-diarios` executa `python manage.py enviar_lembretes_diarios` às 08h de Fortaleza (cron UTC `0 11 * * *`). Usa o mesmo banco do web e as variáveis `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE` e `OWNER_WHATSAPP` por referências do Railway. O processo termina ao concluir; não executar Gunicorn nesse serviço.

Inclui parcelas de empréstimos/vendas e cobranças de aluguel vencendo hoje ou atrasadas. O responsável recebe o resumo dessas cobranças e as contas a pagar ativas que vencem hoje. Despesas já realizadas do Financeiro não são contas futuras. Cobranças pagas não entram; contratos cancelados, renegociados e quitados são excluídos.

`python manage.py enviar_lembretes_diarios --dry-run` verifica a conexão e conta as tarefas sem enviar mensagens ou registrar envios. A tabela `core_lembretediario` garante uma tentativa por cobrança/dia, inclusive em execuções simultâneas. O resumo do proprietário usa uma versão do conteúdo: se as contas ou cobranças mudarem, a próxima execução envia o resumo atualizado; conteúdo igual não é repetido. Para atualizar só o proprietário, execute `python manage.py enviar_lembretes_diarios --somente-resumo`. Falhas isoladas ficam registradas e não interrompem os outros destinatários; qualquer falha faz o comando terminar com erro. Evita-se reenvio automático no mesmo dia em caso de timeout, pois a Evolution pode ter recebido a mensagem. O dia seguinte cria uma nova tentativa para cobranças ainda abertas.

Não agendar simultaneamente os comandos antigos `enviar_cobrancas_do_dia` e `enviar_lembretes_atraso`: o novo comando já cobre os dois fluxos. Para mudar o horário, atualizar `cronSchedule` do serviço no Railway, sempre em UTC.

## Transferir saldo para a próxima cobrança

A opção **Somar à próxima** consulta uma prévia (valor atual + próxima cobrança e vencimento) e exige confirmação. O POST verifica se os valores continuam iguais, bloqueia o contrato durante a alteração e rejeita cobranças pagas ou já transferidas. A cobrança antiga mantém valor e histórico, com estado Transferida e vínculo para o destino. Ela não entra novamente nos saldos, lembretes ou recebimentos.

Sem próxima cobrança, prorroga somente o saldo para um período depois, sem inventar outra mensalidade. Em somente juros, soma o saldo aos juros normais do próximo período, sem capitalizar juros sobre o valor transferido. O período respeita a recorrência do contrato (semanal, quinzenal ou mensal). Não cria entrada de caixa.

O cron usa `sh start_lembretes.sh`, aguardando as migrações do web antes de executar os lembretes.
