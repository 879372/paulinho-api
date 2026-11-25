#!/bin/sh
set -eu
# O web aplica as migrações. Aguarda a conclusão antes de consultar cobranças.
tentativas=0
until python manage.py migrate --check >/dev/null 2>&1; do
    tentativas=$((tentativas + 1))
    if [ "$tentativas" -ge 30 ]; then
        echo 'Migrações pendentes ou banco indisponível; lembretes não executados.' >&2
        exit 1
    fi
    sleep 2
done
exec python manage.py enviar_lembretes_diarios
