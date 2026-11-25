import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings


class DeploymentTests(TestCase):
    def test_frontend_deep_link_does_not_capture_api_or_missing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'index.html').write_text('<html>Gestão de Operações</html>')
            with override_settings(SERVE_FRONTEND=True, FRONTEND_DIST=root):
                response = self.client.get('/animais')
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'Gest', b''.join(response.streaming_content))
                self.assertEqual(response['Cache-Control'], 'no-store')
                self.assertEqual(self.client.get('/api/inexistente/').status_code, 404)
                self.assertEqual(self.client.get('/assets/inexistente.js').status_code, 404)

    def test_bootstrap_creates_admin_once_and_preserves_password(self):
        with patch.dict(os.environ, INITIAL_ADMIN_USERNAME='admin-teste', INITIAL_ADMIN_PASSWORD='senha-inicial-para-testes-123'):
            call_command('bootstrap_admin')
            user = get_user_model().objects.get(username='admin-teste')
            self.assertTrue(user.is_superuser)
            user.set_password('outra-senha-de-teste')
            user.save()
            call_command('bootstrap_admin')
            user.refresh_from_db()
            self.assertTrue(user.check_password('outra-senha-de-teste'))
