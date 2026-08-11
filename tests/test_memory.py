import json
import tempfile
import unittest
from pathlib import Path

from memory import JsonMemoryRepository


class MemoryRepositoryTests(unittest.TestCase):
    def test_rejects_filler_and_does_not_store_raw_message(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonMemoryRepository(Path(directory) / "memory.json")
            repository.load()
            self.assertEqual(
                repository.add_candidates(
                    "1",
                    "João",
                    [{"content": "kkkk sim", "type": "fact", "confidence": 1}],
                    source_text="kkkk sim",
                ),
                [],
            )
            self.assertEqual(repository.relevant_memories("1"), [])

    def test_structures_confidence_and_consolidates_contradiction(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = JsonMemoryRepository(Path(directory) / "memory.json")
            repository.load()
            repository.add_candidates(
                "1",
                "João",
                [{"content": "Gosta de Minecraft", "type": "preference", "confidence": 0.95}],
            )
            repository.add_candidates(
                "1",
                "João",
                [{"content": "Não gosto mais de Minecraft", "type": "preference", "confidence": 0.95}],
            )
            records = repository.relevant_memories("1")
            self.assertEqual(len(records), 1)
            self.assertIn("não gosto", records[0]["content"].lower())
            self.assertEqual(records[0]["type"], "preference")
            self.assertGreaterEqual(records[0]["confidence"], 0.95)

    def test_migrates_legacy_memory_items(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "users": {
                            "1": {
                                "name": "João",
                                "memory": ["Gosta de jogos"],
                                "bot_opinion": "É engraçado",
                            }
                        },
                        "servers": {"2": {"name": "Guilda"}},
                    }
                ),
                encoding="utf-8",
            )
            repository = JsonMemoryRepository(path)
            repository.load()
            self.assertEqual(repository.data["version"], 2)
            self.assertEqual(repository.data["users"]["1"]["facts"][0]["source"], "legacy")
            self.assertEqual(repository.data["servers"]["2"]["activity"], 0.0)
            self.assertNotIn("memory", repository.data["users"]["1"])


if __name__ == "__main__":
    unittest.main()
