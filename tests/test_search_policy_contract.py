from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "scirepro"


def read(*relative_paths: str) -> str:
    return "\n".join((SKILL / relative).read_text(encoding="utf-8") for relative in relative_paths)


def nearby(left: str, right: str, distance: int = 420) -> re.Pattern[str]:
    """Match related policy ideas without depending on their order or exact sentence."""
    return re.compile(
        rf"(?:{left}).{{0,{distance}}}(?:{right})|(?:{right}).{{0,{distance}}}(?:{left})",
        re.IGNORECASE | re.DOTALL,
    )


class SearchPolicyContractTests(unittest.TestCase):
    def test_missingness_alone_does_not_trigger_open_ended_discovery(self) -> None:
        policy = read("SKILL.md", "references/source-environment-audit.md")

        self.assertRegex(
            policy,
            nearby(
                r"(?:mere|mere(?:ly)?|simple|alone|by itself).{0,80}(?:missing|absence|unreported|unspecified)|"
                r"(?:missing|absence|unreported|unspecified).{0,80}(?:alone|by itself)",
                r"(?:do not|does not|must not|never).{0,100}(?:trigger|justify|require).{0,100}(?:web|online|internet|discover|search)",
                520,
            ),
        )
        self.assertRegex(
            policy,
            nearby(
                r"decision[- ]changing|change.{0,80}(?:route|claim|acceptance|action|safety|deliverable)",
                r"(?:web|online|internet|discover|search|lookup)",
            ),
            "external discovery should be justified by a decision it can change",
        )

    def test_local_evidence_precedes_discovery_and_v0_is_not_delayed(self) -> None:
        policy = read("SKILL.md", "references/source-environment-audit.md")

        self.assertRegex(
            policy,
            r"(?is)(?:local|user[- ]supplied|paper|target).{0,260}(?:evidence|artifact|attachment|citation).{0,520}"
            r"(?:before|prior to|first).{0,180}(?:open[- ]ended|broad|discovery|web search)|"
            r"(?:before|prior to|first).{0,180}(?:open[- ]ended|broad|discovery|web search).{0,520}"
            r"(?:local|user[- ]supplied|paper|target).{0,260}(?:evidence|artifact|attachment|citation)",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:no|without).{0,100}(?:claim[- ]defining|critical|essential).{0,100}(?:blocker|unknown|gap)",
                r"(?:start|run|execute|proceed.{0,80}with).{0,100}(?:meaningful\s+)?V0",
                520,
            ),
            "a defensible provisional run should start when no scientific blocker remains",
        )

    def test_only_decision_items_enter_a_short_internal_queue(self) -> None:
        policy = read("SKILL.md", "references/source-environment-audit.md")

        self.assertRegex(
            policy,
            nearby(
                r"(?:short|compact|bounded|minimal).{0,100}(?:internal\s+)?(?:decision|search|investigation).{0,80}(?:queue|list)|"
                r"(?:internal\s+)?(?:decision|search|investigation).{0,80}(?:queue|list).{0,100}(?:short|compact|bounded|minimal)",
                r"decision[- ]changing|change.{0,80}(?:route|claim|acceptance|action|safety|deliverable)",
                520,
            ),
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:queue|list).{0,140}(?:unknown|gap|question|item)",
                r"(?:internal|transient|not.{0,60}(?:artifact|ledger|report)|no.{0,60}(?:artifact|ledger|report))",
                480,
            ),
            "the search queue should guide reasoning, not become a customer-facing artifact",
        )

    def test_search_queue_is_adaptive_not_an_exhaustive_batch(self) -> None:
        policy = read("SKILL.md", "references/source-environment-audit.md")

        self.assertRegex(
            policy,
            r"(?is)(?:do not|never|avoid).{0,140}(?:batch|search|resolve).{0,140}(?:all|every).{0,120}(?:missing|gap|unknown)|"
            r"(?:all|every).{0,100}(?:missing|gap|unknown).{0,180}(?:do not|never|avoid).{0,120}(?:batch|search|resolve)",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:group|merge|batch).{0,140}(?:related|overlap|shared|same)",
                r"(?:one|same|shared).{0,100}(?:authoritative|official|paper[- ]cited).{0,80}(?:source|artifact|repository)",
                560,
            ),
            "only gaps likely answered by one authoritative source should share a lookup",
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:highest|greatest).{0,100}(?:information|decision).{0,80}(?:value|impact|gain)|"
                r"(?:information|decision).{0,80}(?:value|impact|gain).{0,100}(?:highest|greatest)|"
                r"(?:highest|greatest).{0,100}(?:expected[- ]information|information[- ]value|decision[- ]impact)",
                r"(?:first|priority|prioritize|resolve)",
            ),
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:after|on).{0,80}(?:each|a|new).{0,80}(?:result|finding|evidence)",
                r"(?:re[- ]?evaluate|recompute|update|reassess).{0,100}(?:queue|remaining|next).{0,140}(?:cancel|drop|prune|remove|skip).{0,100}(?:obsolete|irrelevant|unnecessary|superseded)",
                620,
            ),
        )

    def test_directed_paper_retrieval_is_distinct_from_open_discovery(self) -> None:
        investigation = read("references/source-environment-audit.md")

        self.assertRegex(
            investigation,
            nearby(
                r"(?:paper[- ]cited|explicit(?:ly)? cited|direct citation|direct link|named repository|named artifact)",
                r"(?:directed|targeted).{0,100}(?:retrieval|lookup|source check)",
                460,
            ),
        )
        self.assertRegex(
            investigation,
            nearby(
                r"open[- ]ended|broad|discovery",
                r"(?:web|online|internet|search)",
                180,
            ),
        )
        self.assertRegex(
            investigation,
            nearby(
                r"(?:directed|targeted).{0,100}(?:retrieval|lookup)",
                r"(?:not|different|distinct|separate).{0,100}(?:open[- ]ended|broad|discovery)",
                480,
            ),
        )

    def test_candidate_is_screened_before_minimal_download(self) -> None:
        investigation = read("references/source-environment-audit.md")
        before_download = r"(?:before|prior to).{0,100}(?:download|retriev|acquir)|(?:pre[- ]download|pre[- ]retrieval)"

        for expected_check in (
            r"identity|correspondence|target match",
            r"authority|provenance|official",
            r"access.{0,80}licen[cs]e|licen[cs]e.{0,80}access",
            r"size.{0,80}format|format.{0,80}size",
            r"(?:specific|named|expected).{0,100}(?:gap|unknown|question).{0,80}(?:close|resolve|answer|fill)|"
            r"(?:gap|unknown|question|queue item).{0,80}(?:expected|intend).{0,80}(?:close|resolve|answer|fill)|"
            r"(?:exact|specific|named).{0,80}(?:queue item|gap|unknown|question).{0,80}(?:expected|intend).{0,80}(?:close|resolve|answer|fill)|"
            r"(?:queue item|gap|unknown|question).{0,100}(?:it is )?expected to (?:close|resolve|answer|fill)",
        ):
            self.assertRegex(
                investigation,
                nearby(before_download, expected_check, 620),
                f"missing pre-download screening dimension: {expected_check}",
            )

        self.assertRegex(
            investigation,
            nearby(
                r"(?:smallest|minimal|only.{0,80}(?:needed|required|relevant)).{0,100}(?:artifact|file|download|retrieval)",
                r"(?:download|retriev|acquir)",
            ),
        )

    def test_downloaded_evidence_is_classified_by_actual_fit(self) -> None:
        investigation = read("references/source-environment-audit.md")

        self.assertRegex(
            investigation,
            r"(?is)(?:download|retriev|acquir).{0,260}(?:inspect|review|open).{0,220}"
            r"classif.{0,140}(?:evidential|evidence|fit|exact|partial)",
            "retrieved material should be inspected before its evidential fit is classified",
        )
        for evidence_class in (
            r"exact(?: original)?",
            r"partial(?:ly)?",
            r"official example",
            r"substitute",
            r"irrelevant|unrelated",
            r"restricted",
        ):
            self.assertRegex(investigation, evidence_class)

    def test_search_stops_when_it_cannot_change_the_route_or_action(self) -> None:
        policy = read("SKILL.md", "references/source-environment-audit.md")

        self.assertRegex(
            policy,
            nearby(
                r"\bstop\b",
                r"(?:route|process).{0,100}(?:defensible|runnable|supported)",
                460,
            ),
        )
        self.assertRegex(
            policy,
            nearby(
                r"(?:next|another|additional|further).{0,100}(?:search|lookup|source|check)",
                r"(?:cannot|can no longer|would not|will not).{0,120}(?:change|alter).{0,100}(?:action|decision|route|claim|acceptance)",
                520,
            ),
        )

    def test_search_policy_adds_no_modes_or_pre_execution_web_gate(self) -> None:
        policy = read(
            "SKILL.md",
            "references/source-environment-audit.md",
            "references/execution-validation.md",
        )

        for named_tier in (
            r"(?i)\b(?:quick|standard|forensic|audit)\s+(?:mode|tier|workflow)\b",
            r"(?m)^#{1,6}\s*(?:快速|标准|取证|审计)(?:档|模式|流程)?\s*$",
        ):
            self.assertNotRegex(policy, named_tier)

        for forbidden_gate in (
            r"(?i)approval required before execution",
            r"(?i)review the report before execution",
            r"执行前.{0,40}(?:网页|报告).{0,40}(?:审核|批准)",
        ):
            self.assertNotRegex(policy, forbidden_gate)

        self.assertRegex(
            policy,
            nearby(
                r"(?:do not|never|without).{0,120}(?:create|require|use)?",
                r"pre[- ]execution.{0,100}(?:webpage|web report|approval|gate)",
                260,
            ),
        )


if __name__ == "__main__":
    unittest.main()
