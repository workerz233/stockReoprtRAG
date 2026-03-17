import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


class FakeRoute:
    def __init__(self, name: str, utterances: list[str], description: str = "") -> None:
        self.name = name
        self.utterances = utterances
        self.description = description


class FakeSemanticRouter:
    def __init__(self, encoder, routes, auto_sync=None) -> None:
        self.encoder = encoder
        self.routes = routes
        self.auto_sync = auto_sync

    def __call__(self, text: str):
        if "总结" in text or "上文" in text:
            return types.SimpleNamespace(name="history_qa", similarity_score=0.96)
        if text in {"它怎么样", "那个呢", "这个结论呢"}:
            return types.SimpleNamespace(name="clarification", similarity_score=0.88)
        if text in {"那2025年呢", "它的毛利率呢"}:
            return types.SimpleNamespace(name="history_rewrite_retrieval", similarity_score=0.91)
        if text in {"你好", "你是谁"}:
            return types.SimpleNamespace(name="chitchat", similarity_score=0.98)
        return types.SimpleNamespace(name="direct_retrieval", similarity_score=0.83)


class FakeOllamaEncoder:
    def __init__(self, name: str, base_url: str) -> None:
        self.name = name
        self.base_url = base_url


class IntentRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_dotenv = types.ModuleType("dotenv")
        fake_dotenv.load_dotenv = lambda: None
        sys.modules["dotenv"] = fake_dotenv

        semantic_router_module = types.ModuleType("semantic_router")
        semantic_router_module.Route = FakeRoute
        sys.modules["semantic_router"] = semantic_router_module

        routers_module = types.ModuleType("semantic_router.routers")
        routers_module.SemanticRouter = FakeSemanticRouter
        sys.modules["semantic_router.routers"] = routers_module

        encoders_module = types.ModuleType("semantic_router.encoders")
        encoders_module.OllamaEncoder = FakeOllamaEncoder
        sys.modules["semantic_router.encoders"] = encoders_module

        sys.modules.pop("backend.rag.intent_router", None)
        self.module = importlib.import_module("backend.rag.intent_router")
        self.settings = types.SimpleNamespace(
            embedding_model="test-embedding",
            embedding_url="http://localhost:11434/api/embeddings",
        )

    def test_load_route_definitions_from_json(self) -> None:
        router = self.module.IntentRouter(settings=self.settings)

        routes = router._load_route_definitions()

        self.assertEqual(
            {route.name for route in routes},
            {
                "chitchat",
                "history_qa",
                "history_rewrite_retrieval",
                "direct_retrieval",
                "clarification",
            },
        )
        self.assertTrue(all(route.utterances for route in routes))

    def test_builds_semantic_router_from_loaded_routes(self) -> None:
        router = self.module.IntentRouter(settings=self.settings)

        self.assertIsNotNone(router.router)
        self.assertEqual(router.router.encoder.name, "test-embedding")
        self.assertEqual(router.router.encoder.base_url, "http://localhost:11434")
        self.assertEqual(router.router.auto_sync, "local")

    def test_route_history_summary_to_history_qa(self) -> None:
        router = self.module.IntentRouter(settings=self.settings)

        decision = router.route(
            "总结一下上文",
            history_messages=[
                {"role": "user", "content": "上一问"},
                {"role": "assistant", "content": "上一答"},
            ],
        )

        self.assertEqual(decision.route_name, "history_qa")
        self.assertEqual(decision.query, "总结一下上文")
        self.assertGreater(decision.confidence, 0.0)

    def test_route_short_pronoun_to_clarification_when_history_is_insufficient(self) -> None:
        router = self.module.IntentRouter(settings=self.settings)

        decision = router.route(
            "它怎么样",
            history_messages=[
                {"role": "user", "content": "上一问"},
                {"role": "assistant", "content": "上一答"},
            ],
        )

        self.assertEqual(decision.route_name, "clarification")
        self.assertIn("semantic-router", decision.reason)

    def test_router_falls_back_to_direct_retrieval_when_config_is_unavailable(self) -> None:
        missing_path = Path(tempfile.gettempdir()) / "missing-semantic-routes.json"
        router = self.module.IntentRouter(settings=self.settings, route_config_path=missing_path)

        decision = router.route("宁德时代2025年盈利预测是多少", history_messages=[])

        self.assertEqual(decision.route_name, "direct_retrieval")
        self.assertEqual(decision.confidence, 0.0)
        self.assertIn("fallback", decision.reason)

    def test_load_route_definitions_from_custom_json_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            route_path = Path(temp_dir) / "semantic_routes.json"
            route_path.write_text(
                json.dumps(
                    [
                        {
                            "name": "chitchat",
                            "description": "闲聊",
                            "utterances": ["你好"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            router = self.module.IntentRouter(settings=self.settings, route_config_path=route_path)

            routes = router._load_route_definitions()

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].name, "chitchat")


if __name__ == "__main__":
    unittest.main()
