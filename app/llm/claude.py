"""Host-native proxy integration; this process never receives a provider key."""
import os
from llm.config import DEFAULT_MODELS
from llm.proxy_client import request


def generate_with_claude(system_prompt: str, user_prompt: str):
    payload = {
        'model': os.getenv('ANTHROPIC_MODEL') or DEFAULT_MODELS['anthropic'],
        'max_tokens': 800,
        'system': system_prompt,
        'messages': [{'role': 'user', 'content': user_prompt}],
    }
    result = None
    for event in request('/Library/Application Support/CredentialProxy/run/api.sock', {'integration': 'linkedin-anthropic', 'operation': 'messages.create', 'payload': payload}):
        if event['type'] == 'response':
            result = event['body']
    if result is None:
        raise RuntimeError('proxy returned no response')
    return {
        'text': ''.join(block['text'] for block in result['content'] if block['type'] == 'text'),
        'model': result['model'],
        'input_tokens': result['usage']['input_tokens'],
        'output_tokens': result['usage']['output_tokens'],
    }
