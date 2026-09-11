import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.adapters.elevenlabs import ElevenLabsVoice, VoiceUnavailable
from app.api.voice import router, voice_user, _requests
from app.shared.auth import CurrentUser, get_current_user
from app.shared.config import Settings


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        with patch('app.adapters.elevenlabs.get_settings', return_value=Settings(
            elevenlabs_enabled=True, elevenlabs_api_key='test-secret', elevenlabs_voice_id='test-voice',
        )):
            return ElevenLabsVoice()

    async def test_transcription_is_multipart_and_disables_retention(self):
        def handler(request):
            self.assertEqual(str(request.url).split('?')[0], 'https://api.elevenlabs.io/v1/speech-to-text')
            self.assertEqual(request.url.params['enable_logging'], 'false')
            self.assertEqual(request.headers['xi-api-key'], 'test-secret')
            self.assertIn(b'scribe_v2', request.content)
            self.assertIn(b'example-audio', request.content)
            return httpx.Response(200, json={'text': ' two tubs of curd '})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch('app.adapters.elevenlabs.httpx.AsyncClient', return_value=client):
            self.assertEqual(await self.service().transcribe(b'example-audio', 'audio/webm'), 'two tubs of curd')

    async def test_playback_uses_server_voice_and_model(self):
        def handler(request):
            self.assertIn('/text-to-speech/test-voice', str(request.url))
            self.assertEqual(request.url.params['enable_logging'], 'false')
            self.assertEqual(json.loads(request.content)['model_id'], 'eleven_multilingual_v2')
            return httpx.Response(200, content=b'ID3-audio', headers={'content-type': 'audio/mpeg'})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch('app.adapters.elevenlabs.httpx.AsyncClient', return_value=client):
            self.assertEqual(await self.service().speak('Review before confirming.'), b'ID3-audio')

    async def test_provider_failures_do_not_leak_body_or_retry_with_logging(self):
        for code in [401, 403, 429, 500]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(code, text='secret-provider-diagnostic')
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with patch('app.adapters.elevenlabs.httpx.AsyncClient', return_value=client):
                with self.assertRaises(VoiceUnavailable) as error:
                    await self.service().transcribe(b'audio', 'audio/webm')
            self.assertNotIn('secret-provider', str(error.exception))
            self.assertEqual(len(calls), 1)

    async def test_timeout_and_invalid_transcript_are_safe(self):
        for response in [None, {'text': ''}, {'text': 42}, {'text': 'x' * 4001}]:
            def handler(request):
                if response is None:
                    raise httpx.ReadTimeout('sensitive details', request=request)
                return httpx.Response(200, json=response)
            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            with patch('app.adapters.elevenlabs.httpx.AsyncClient', return_value=client):
                with self.assertRaises(VoiceUnavailable):
                    await self.service().transcribe(b'audio', 'audio/webm')

    async def test_disabled_provider_never_sends_audio(self):
        service = self.service()
        service.enabled = False
        with patch('app.adapters.elevenlabs.httpx.AsyncClient') as client:
            with self.assertRaises(VoiceUnavailable):
                await service.transcribe(b'audio', 'audio/webm')
            client.assert_not_called()

    async def test_audio_response_size_and_type_are_bounded(self):
        for content, mime in [(b'x' * 2_000_001, 'audio/mpeg'), (b'{}', 'application/json')]:
            client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content, headers={'content-type': mime})))
            with patch('app.adapters.elevenlabs.httpx.AsyncClient', return_value=client):
                with self.assertRaises(VoiceUnavailable):
                    await self.service().speak('Hello')


class RouteTests(unittest.TestCase):
    def setUp(self):
        _requests.clear()
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        self.user = CurrentUser('test-user', None)

    def authorize(self):
        self.app.dependency_overrides[voice_user] = lambda: self.user
        self.app.dependency_overrides[get_current_user] = lambda: self.user

    def test_authentication_required_for_both_actions(self):
        for path, payload in [('transcribe', {'content': b'audio', 'headers': {'content-type': 'audio/webm'}}), ('speak', {'json': {'text': 'hello'}})]:
            self.assertEqual(self.client.post('/api/voice/' + path, **payload).status_code, 401)

    def test_non_shopper_rejected_before_provider(self):
        async def deny():
            raise HTTPException(403, 'Inactive profile')
        self.app.dependency_overrides[voice_user] = deny
        with patch('app.api.voice.ElevenLabsVoice') as provider:
            self.assertEqual(self.client.post('/api/voice/speak', json={'text': 'hello'}).status_code, 403)
            provider.assert_not_called()

    def test_transcript_does_not_mutate_and_requires_review(self):
        self.authorize()
        service = AsyncMock()
        service.transcribe.return_value = 'Add two yogurts'
        with patch('app.api.voice.ElevenLabsVoice', return_value=service):
            response = self.client.post('/api/voice/transcribe', content=b'audio', headers={'content-type': 'audio/webm;codecs=opus'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'transcript': 'Add two yogurts', 'requiresConfirmation': True})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        service.transcribe.assert_awaited_once_with(b'audio', 'audio/webm')
        service.speak.assert_not_called()

    def test_invalid_or_oversized_inputs_never_reach_provider(self):
        self.authorize()
        with patch('app.api.voice.ElevenLabsVoice') as provider:
            self.assertEqual(self.client.post('/api/voice/transcribe', content=b'audio', headers={'content-type': 'text/html'}).status_code, 415)
            self.assertEqual(self.client.post('/api/voice/transcribe', content=b'', headers={'content-type': 'audio/webm'}).status_code, 422)
            with patch('app.api.voice.MAX_AUDIO_BYTES', 4):
                self.assertEqual(self.client.post('/api/voice/transcribe', content=b'12345', headers={'content-type': 'audio/webm'}).status_code, 413)
            for text in [' ', 'x' * 1201]:
                self.assertEqual(self.client.post('/api/voice/speak', json={'text': text}).status_code, 422)
            provider.assert_not_called()

    def test_limits_are_per_user_and_audio_not_cached(self):
        self.authorize()
        service = AsyncMock()
        service.speak.return_value = b'audio'
        with patch('app.api.voice.ElevenLabsVoice', return_value=service):
            for _ in range(10):
                response = self.client.post('/api/voice/speak', json={'text': 'hello'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertEqual(self.client.post('/api/voice/speak', json={'text': 'hello'}).status_code, 429)
            self.user = CurrentUser('other-user', None)
            self.assertEqual(self.client.post('/api/voice/speak', json={'text': 'hello'}).status_code, 200)

    def test_unavailable_service_returns_text_fallback(self):
        self.authorize()
        service = AsyncMock()
        service.transcribe.side_effect = VoiceUnavailable('Voice unavailable. Please use text.')
        with patch('app.api.voice.ElevenLabsVoice', return_value=service):
            response = self.client.post('/api/voice/transcribe', content=b'audio', headers={'content-type': 'audio/webm'})
        self.assertEqual(response.status_code, 503)
        self.assertIn('text', response.json()['detail'])
