"""Capture exact API inputs with a mock; never calls a paid model."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from news import generation, selected_news
from news.provenance import generation_record


class ProvenanceTests(unittest.TestCase):
    def test_selected_record_matches_actual_request(self):
        evidence = {'analysis_tracks': [{'track_name': '테스트'}]}
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.return_value = SimpleNamespace(status='completed', output_text='TEST DRAFT')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-not-a-key'}), \
             patch('dotenv.load_dotenv', return_value=False), patch('openai.OpenAI', return_value=client):
            selected_news.generate_paid_article(evidence)
        request = client.responses.create.call_args.kwargs
        record = generation_record(evidence)
        self.assertEqual(record['instructions'], request['instructions'])
        self.assertEqual(record['input_json'], request['input'])
        self.assertEqual(record['input_sha256'], hashlib.sha256(request['input'].encode()).hexdigest())
        self.assertEqual(record['max_output_tokens'], request['max_output_tokens'])
        self.assertNotIn('synthetic-not-a-key', json.dumps(record))

    def test_legacy_cli_saves_exact_prompt_and_evidence(self):
        facts = selected_news.load_verified_facts('2026-10-08')
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.return_value = SimpleNamespace(status='completed', output_text='TEST DRAFT')
        with tempfile.TemporaryDirectory(dir=generation.ROOT) as tmp, patch.object(generation, 'OUTPUT_DIR', Path(tmp)), \
             patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-not-a-key'}), \
             patch('dotenv.load_dotenv', return_value=False), patch('openai.OpenAI', return_value=client), \
             patch('sys.argv', ['generation', '--mode', 'openai', '--confirm-paid']):
            generation.main()
            output = json.loads(next(Path(tmp).glob('*.json')).read_text(encoding='utf-8'))
        request = client.responses.create.call_args.kwargs
        self.assertEqual(output['generation_provenance']['instructions'], request['instructions'])
        self.assertEqual(output['generation_provenance']['input_json'], request['input'])
        self.assertFalse(output['publication_approved'])

    def test_template_does_not_claim_model_prompt(self):
        record = generation_record({'value': 1}, ai_generated=False)
        self.assertIsNone(record['instructions'])
        self.assertIsNone(record['max_output_tokens'])
        self.assertEqual(record['prompt_version'], 'template-v1')
