import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = 'Cria o administrador inicial, sem alterar contas existentes.'

    @transaction.atomic
    def handle(self, *args, **options):
        username = os.getenv('INITIAL_ADMIN_USERNAME', '')
        password = os.getenv('INITIAL_ADMIN_PASSWORD', '')
        if not username or not password:
            self.stdout.write('Administrador inicial não solicitado.')
            return
        if len(password) < 16:
            raise CommandError('A senha inicial deve ter pelo menos 16 caracteres.')
        users = get_user_model().objects
        if users.filter(username=username).exists():
            self.stdout.write('Administrador existente preservado.')
            return
        users.create_superuser(username=username, password=password)
        self.stdout.write('Administrador inicial criado.')
