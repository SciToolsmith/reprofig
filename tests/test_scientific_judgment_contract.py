from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "scirepro"


def read(*relative_paths: str) -> str:
    return "\n".join((SKILL / relative).read_text(encoding="utf-8") for relative in relative_paths)


def nearby(left: str, right: str, distance: int = 360) -> re.Pattern[str]:
    """Match two semantic ideas near each other without pinning exact prose or order."""
    return re.compile(
        rf"(?:{left}).{{0,{distance}}}(?:{right})|(?:{right}).{{0,{distance}}}(?:{left})",
        re.IGNORECASE | re.DOTALL,
    )


class ScientificJudgmentContractTests(unittest.TestCase):
    def test_policy_remains_one_adaptive_flow_without_review_modes(self) -> None:
        active = read(
            "SKILL.md",
            "references/execution-validation.md",
            "references/source-environment-audit.md",
        )

        for tier_pattern in (
            r"(?im)^#{1,6}\s*(?:quick|standard|forensic|audit)(?:\s+(?:mode|tier|workflow))?\s*$",
            r"(?i)\b(?:quick|standard|forensic|audit)\s+(?:mode|tier|workflow)\b",
            r"(?m)^#{1,6}\s*(?:快速|标准|取证|审计)(?:档|模式|流程)?\s*$",
        ):
            self.assertNotRegex(active, tier_pattern)

        self.assertRegex(active, r"(?is)one\s+adaptive\s+workflow")
        for forbidden_gateway in (
            "Review the report before execution",
            "awaiting-approval",
            "approval required before execution",
            "pre-execution web report for review",
        ):
            self.assertNotIn(forbidden_gateway.casefold(), active.casefold())
        self.assertRegex(
            active,
            r"(?is)(?:do not|never|without).{0,100}pre[- ]execution.{0,100}(?:web|report|approval|gate)",
        )

    def test_unknowns_are_classified_by_effect_on_the_scientific_decision(self) -> None:
        policy = read("SKILL.md", "references/execution-validation.md")

        self.assertRegex(
            policy,
            nearby(
                r"(?:unknown|missing|unreported|unspecified|ambiguous)\w*",
                r"(?:mechanism|trend|magnitude|observable|acceptance|conclusion|claim)",
            ),
            "unknowns should be judged by whether they can change the scientific outcome",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:critical|material|decision[- ]changing|outcome[- ]changing)",
                r"(?:resolve|derive|verify|test|compare|block)",
            ),
            "scientifically material unknowns require evidence or a discriminating test",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:non[- ]critical|nuisance|incidental|cosmetic|presentation[- ]only)",
                r"(?:assum|infer|choose|fix|declare|disclos)",
            ),
            "non-critical details should permit transparent assumptions rather than archaeology",
        )

    def test_noncritical_randomness_can_be_fixed_but_never_cherry_picked(self) -> None:
        policy = read(
            "SKILL.md",
            "references/execution-validation.md",
            "references/source-environment-audit.md",
        )

        self.assertRegex(
            policy,
            nearby(
                r"(?:non[- ]critical|incidental|does not change|not material).{0,100}(?:seed|random)",
                r"(?:fixed|chosen|declared|disclosed|reproducible)",
            ),
            "an immaterial seed should be fixed transparently rather than recovered exactly",
        )
        self.assertRegex(
            policy,
            r"(?is)(?:do not|never|need not|not required).{0,180}(?:search|recover|infer|match).{0,120}(?:author(?:'s)?|original|exact).{0,80}(?:seed|random)|"
            r"(?:author(?:'s)?|original|exact).{0,80}(?:seed|random).{0,180}(?:do not|never|need not|not required).{0,180}(?:search|recover|infer|match)",
        )
        self.assertRegex(policy, r"(?is)(?:never|do not).{0,100}cherry[- ]pick.{0,120}(?:seed|random|result)")

    def test_material_unknowns_get_only_the_smallest_decisive_check(self) -> None:
        policy = read("SKILL.md", "references/execution-validation.md")

        self.assertRegex(
            policy,
            nearby(
                r"(?:claim[- ]defining|critical|material|decision[- ]changing).{0,100}(?:unknown|parameter|assumption|choice)|"
                r"(?:unknown|parameter|assumption|choice).{0,100}(?:claim[- ]defining|critical|material|decision[- ]changing)",
                r"(?:smallest|minimal|bounded|limited).{0,100}(?:test|comparison|contrast|sensitivity)",
                480,
            ),
        )
        self.assertRegex(
            policy,
            nearby(
                r"sensitivity",
                r"(?:change|flip|depend).{0,100}(?:claim|conclusion|acceptance|interpretation)",
            ),
            "sensitivity work should be conditional on a conclusion-changing uncertainty",
        )
        self.assertRegex(policy, r"(?is)(?:do not|no).{0,100}(?:default|exhaustive).{0,80}(?:grid|sweep|search)")

    def test_transparent_nuisance_assumptions_do_not_create_ceremonial_pauses(self) -> None:
        gates = read("references/permission-gates.md")

        self.assertRegex(
            gates,
            nearby(
                r"(?:non[- ]critical|nuisance).{0,100}assumption",
                r"(?:do not pause|proceed|without (?:asking|pausing))",
                420,
            ),
        )
        self.assertRegex(
            gates,
            nearby(
                r"mechanism[- ]reproduction|alternative[- ]validation",
                r"(?:same|stated).{0,80}objective",
                420,
            ),
        )

    def test_calibration_is_not_reused_as_independent_validation(self) -> None:
        validation = read("references/execution-validation.md")

        self.assertRegex(
            validation,
            nearby(
                r"(?:estimate|select|calibrat).{0,100}(?:parameter|assumption)",
                r"not independent validation",
                420,
            ),
        )
        self.assertRegex(
            validation,
            r"(?is)(?:another predeclared observable|held[- ]out).{0,220}(?:narrow|inconclusive)",
        )

    def test_failed_authoritative_lookup_can_switch_to_mechanism_route(self) -> None:
        policy = read(
            "SKILL.md",
            "references/execution-validation.md",
            "references/source-environment-audit.md",
        )

        self.assertRegex(
            policy,
            nearby(
                r"(?:one|single|bounded|targeted|focused).{0,120}(?:authoritative|author[- ]native|official).{0,100}(?:check|source|lookup|evidence|artifact)|"
                r"(?:authoritative|author[- ]native|official).{0,100}(?:check|source|lookup|evidence|artifact)",
                r"mechanism[- ]reproduction",
                720,
            ),
            "a bounded failed lookup should permit an honest mechanism reproduction",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:missing|absent|unavailable|not (?:found|published|recoverable)).{0,140}(?:exact|original).{0,120}(?:input|artifact|parameter|seed|configuration)",
                r"(?:switch|proceed|continue|use|choose).{0,100}mechanism[- ]reproduction",
                640,
            ),
        )
        self.assertRegex(
            policy,
            r"(?is)`direct-recompute`.{0,240}(?:verified|exact).{0,120}(?:original|official).{0,140}(?:input|data).{0,160}(?:implementation|code)",
        )
        self.assertRegex(
            policy,
            r"(?is)`direct-recompute`.{0,300}(?:do not|never|cannot).{0,120}(?:probable|inferred|assumed|uncertain)",
            "transparent assumptions must not be mislabeled as direct recomputation",
        )

    def test_image_only_assumptions_never_invent_hidden_science(self) -> None:
        image_only = read("references/image-derived-reconstruction.md")

        self.assertRegex(
            image_only,
            nearby(
                r"pixels? alone",
                r"(?:raw data|hidden exact values|preprocessing|model|method|implementation|parameter|seed)",
            ),
        )
        self.assertRegex(
            image_only,
            nearby(
                r"reasonable assumptions?|ordinary presentation assumptions?",
                r"(?:not|never|do not).{0,100}(?:hidden scientific data|coordinate mapping|series identity|generating method|invent data)",
                320,
            ),
        )
        self.assertRegex(
            image_only,
            r"(?is)(?:do not|never).{0,160}(?:guess|speculative|invent|fabricat).{0,160}(?:data|method|scientific|reconstruction)",
        )

    def test_scientific_acceptance_stops_cosmetic_pixel_chasing(self) -> None:
        policy = read("SKILL.md", "references/execution-validation.md")

        self.assertRegex(
            policy,
            nearby(
                r"(?:scientific (?:fidelity|content|observable)|acceptance criteria)",
                r"(?:presentation|styling|palette|typography|pixel)",
            ),
        )
        self.assertRegex(
            policy,
            r"(?is)stop.{0,180}(?:criteria pass|scientific observables? pass|acceptance passes).{0,240}(?:pixel|cosmetic|presentation|non[- ]critical)",
        )
        self.assertRegex(
            policy,
            r"(?is)(?:overlap|clipping|readability|legibility).{0,220}(?:fix|correct|adjust|preserve meaning|semantic)|"
            r"(?:fix|correct|adjust|preserve meaning|semantic).{0,220}(?:overlap|clipping|readability|legibility)",
            "presentation work should remain bounded to semantic correctness and readability",
        )


if __name__ == "__main__":
    unittest.main()
