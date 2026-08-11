import asyncio
import random
import unittest

from mental import CooldownManager, DecisionEngine, MentalLoop


class FakeUser:
    id = 999
    bot = False


class FakeBot:
    user = FakeUser()

    def is_ready(self):
        return True


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    async def execute(self, decision, message):
        self.calls += 1
        return type("Result", (), {"success": True, "reason": "ok"})()


class MentalDecisionTests(unittest.TestCase):
    def test_empty_observation_is_do_nothing(self):
        engine = DecisionEngine(rng=random.Random(1))
        decision = engine.decide({"candidates": [], "channels": []})
        self.assertEqual(decision.action, "do_nothing")

    def test_cooldown_blocks_same_user_and_action(self):
        clock = iter([100.0, 100.0, 100.0])
        cooldowns = CooldownManager(clock=lambda: next(clock))
        cooldowns.mark("send_dm", user_id="1", server_id="2", now=100.0)
        available, scope, remaining = cooldowns.check(
            "send_dm", user_id="1", server_id="2", now=100.0
        )
        self.assertFalse(available)
        self.assertEqual(scope, "global")
        self.assertGreater(remaining, 0)

    def test_dry_run_never_executes_action(self):
        executor = FakeExecutor()
        loop = MentalLoop(
            bot=FakeBot(),
            observer=lambda: {
                "autonomy_factor": 1.0,
                "candidates": [
                    {
                        "user_id": "1",
                        "user_name": "João",
                        "server_id": "2",
                        "channel_id": "3",
                        "relationship": 1.0,
                        "recency": 1.0,
                        "shared_interest": 1.0,
                        "conversational_interest": 1.0,
                        "inactivity": 1.0,
                        "dm_eligible": True,
                    }
                ],
                "channels": [],
            },
            decision_engine=DecisionEngine(rng=random.Random(1), action_threshold=0.1),
            cooldowns=CooldownManager(),
            executor=executor,
            message_generator=lambda *_: "não deve ser chamado",
            enabled=True,
            dry_run=True,
        )
        decision = asyncio.run(loop.tick())
        self.assertNotEqual(decision.action, "do_nothing")
        self.assertEqual(executor.calls, 0)


if __name__ == "__main__":
    unittest.main()
