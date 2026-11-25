import gzip
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path
import boto3
from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    help = 'Cria um dump PostgreSQL compactado e o envia para um bucket S3.'
    def handle(self, *args, **kwargs):
        bucket = os.getenv('BACKUP_S3_BUCKET')
        database_url = os.getenv('DATABASE_URL')
        pg_dump = os.getenv('PG_DUMP_PATH', 'pg_dump')
        if not bucket or not database_url: raise CommandError('BACKUP_S3_BUCKET e DATABASE_URL são obrigatórias.')
        name = f"backups/backup-{date.today():%Y-%m-%d}.sql.gz"
        with tempfile.TemporaryDirectory() as directory:
            dump = Path(directory) / 'backup.sql'; archive = Path(directory) / 'backup.sql.gz'
            try:
                subprocess.run(
                    [pg_dump, '--dbname', database_url, '--file', str(dump), '--no-owner', '--no-acl'],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as error:
                raise CommandError(f'pg_dump não foi encontrado em: {pg_dump}') from error
            except subprocess.CalledProcessError as error:
                detalhe = (error.stderr or error.stdout or str(error)).strip()
                raise CommandError(f'pg_dump falhou: {detalhe}') from error
            with open(dump, 'rb') as source, gzip.open(archive, 'wb') as target: target.writelines(source)
            client_options = {'region_name': os.getenv('AWS_REGION')}
            endpoint_url = os.getenv('AWS_S3_ENDPOINT_URL')
            if endpoint_url:
                client_options['endpoint_url'] = endpoint_url

            client = boto3.client('s3', **client_options)
            extra_args = {'ServerSideEncryption': 'AES256'} if not endpoint_url else None
            client.upload_file(str(archive), bucket, name, ExtraArgs=extra_args)
        self.stdout.write(self.style.SUCCESS(f'Backup enviado: s3://{bucket}/{name}'))
