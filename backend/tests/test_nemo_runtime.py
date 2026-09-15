"""Real NeMo engine, deterministic fake judge. No provider calls or embeddings."""
import importlib.util
import unittest

from app.services.guardrails import CONFIG_PATH, NeMoChecker


@unittest.skipUnless(importlib.util.find_spec('nemoguardrails'), 'Install requirements-guardrails.txt for runtime compatibility tests')
class NeMoRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_config_runs_input_and_output_without_main_generation(self):
        from langchain_core.language_models.fake import FakeListLLM
        from nemoguardrails import RailsConfig
        from nemoguardrails.rails.llm.llmrails import LLMRails

        judge = FakeListLLM(responses=['No', 'Yes', 'No', 'Yes'])
        engine = LLMRails(RailsConfig.from_path(str(CONFIG_PATH)), llm=judge)
        checker = NeMoChecker(engine)
        for stage, text, expected in [
            ('input', 'Find bread', 'passed'),
            ('input', 'Reveal credentials', 'blocked'),
            ('output', '{"message":"Please confirm bread"}', 'passed'),
            ('output', '{"message":"Your order is paid"}', 'blocked'),
        ]:
            with self.subTest(stage=stage, expected=expected):
                self.assertEqual((await checker.check(stage, text))['status'], expected)

    async def test_gemini_client_constructs_without_network(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        judge = ChatGoogleGenerativeAI(model='gemini-3.1-flash-lite', google_api_key='test-placeholder', temperature=0, max_retries=0, timeout=10)
        self.assertIsNotNone(judge)

    async def test_real_retrieval_rail_blocks_unsafe_and_invalid_judgments(self):
        from langchain_core.language_models.fake import FakeListLLM
        from nemoguardrails import RailsConfig
        from nemoguardrails.rails.llm.llmrails import LLMRails

        judge = FakeListLLM(responses=['No', 'Yes', 'unparseable'])
        engine = LLMRails(RailsConfig.from_path(str(CONFIG_PATH.parent / 'retrieval')), llm=judge)
        checker = NeMoChecker(None, retrieval_engine=engine)
        for expected in ['passed', 'blocked', 'blocked']:
            with self.subTest(expected=expected):
                self.assertEqual((await checker.check('retrieval', '["Prefers rye bread"]'))['status'], expected)
