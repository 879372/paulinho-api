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

Railway usa a branch `main` de `879372/paulinho-api`. O Dockerfile executa `start.sh`, que aplica as migrações do banco próprio, cria o administrador inicial se solicitado e inicia Gunicorn na porta `$PORT` com IPv4/IPv6. Configure `DATABASE_URL`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` e `CSRF_TRUSTED_ORIGINS`. A API fica na rede privada; o frontend encaminha os pedidos para ela. Não use `config.local` em produção.
