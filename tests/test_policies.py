import unittest

from ohrouting.policies import (
    CHEAP,
    FRONTIER,
    Decision,
    PolicyError,
    get_policy,
)

PHASES = ["explore"] * 8 + ["implement"] * 10 + ["test-fix"] * 7
TURNS = 25


def run(name, n=None, phases=PHASES):
    policy = get_policy(name, n)
    out, prev, prev_phase = [], None, None
    for turn, phase in enumerate(phases, start=1):
        d = policy(turn, phase, prev, prev_phase)
        out.append(d)
        prev, prev_phase = d.model, phase
    return out


def switch_turns(decisions):
    return [i for i, d in enumerate(decisions, start=1) if d.switched]


class PolicyTests(unittest.TestCase):
    def test_phase_fixture_length(self):
        self.assertEqual(len(PHASES), TURNS)

    def test_table(self):
        table = [
            ("sticky", None, []),
            ("alternate", None, list(range(2, 26))),
            ("phase-boundary", None, [9, 19]),
            ("switch-at-N", 5, [5]),
            ("switch-at-N", 10, [10]),
            ("switch-at-N", 15, [15]),
        ]
        for name, n, expected in table:
            with self.subTest(policy=name, n=n):
                d = run(name, n)
                self.assertEqual(switch_turns(d), expected)
                self.assertEqual(d[0], Decision(FRONTIER, False))

    def test_models(self):
        self.assertTrue(all(d.model == FRONTIER for d in run("sticky")))
        alt = [d.model for d in run("alternate")]
        self.assertEqual(alt[:4], [FRONTIER, CHEAP, FRONTIER, CHEAP])
        pb = [d.model for d in run("phase-boundary")]
        self.assertEqual((pb[7], pb[8], pb[17], pb[18]), (FRONTIER, CHEAP, CHEAP, FRONTIER))
        for n in (5, 10, 15):
            m = [d.model for d in run("switch-at-N", n)]
            self.assertEqual(m, [FRONTIER] * (n - 1) + [CHEAP] * (TURNS - n + 1))

    def test_switched_matches_model_change(self):
        for name, n in [
            ("sticky", None),
            ("alternate", None),
            ("phase-boundary", None),
            ("switch-at-N", 5),
            ("switch-at-N", 10),
            ("switch-at-N", 15),
        ]:
            with self.subTest(policy=name, n=n):
                d = run(name, n)
                for i in range(1, len(d)):
                    self.assertEqual(d[i].switched, d[i].model != d[i - 1].model)
                self.assertFalse(d[0].switched)

    def test_deterministic(self):
        for name, n in [("alternate", None), ("phase-boundary", None), ("switch-at-N", 10)]:
            self.assertEqual(run(name, n), run(name, n))
        p = get_policy("phase-boundary")
        self.assertEqual(
            p(9, "implement", FRONTIER, "explore"), p(9, "implement", FRONTIER, "explore")
        )

    def test_phase_boundary_ignores_repeated_phase(self):
        p = get_policy("phase-boundary")
        self.assertEqual(p(3, "explore", CHEAP, "explore"), Decision(CHEAP, False))

    def test_validation(self):
        with self.assertRaises(PolicyError):
            get_policy("nope")
        with self.assertRaises(PolicyError):
            get_policy("switch-at-N")
        for bad in (0, -3, True, 2.5, "5"):
            with self.subTest(n=bad), self.assertRaises(PolicyError):
                get_policy("switch-at-N", bad)
        with self.assertRaises(PolicyError):
            get_policy("sticky", 5)
        p = get_policy("sticky")
        for args in [
            (0, "x", None),
            (-1, "x", FRONTIER),
            (2, "x", "gpt"),
            (2, "x", None),
            (1, "x", FRONTIER),
        ]:
            with self.subTest(args=args), self.assertRaises(PolicyError):
                p(*args)


if __name__ == "__main__":
    unittest.main()
