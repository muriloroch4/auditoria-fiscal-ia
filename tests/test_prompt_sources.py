from __future__ import annotations

from pathlib import Path
import unittest

from src.auditoria import report_ai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = PROJECT_ROOT / "prompts"


class PromptSourceTest(unittest.TestCase):
    def test_internal_quarterly_prompt_matches_single_source_file(self):
        prompt_path = PROMPTS_DIR / "relatorio_trimestral.md"

        self.assertEqual(report_ai._system_prompt(), prompt_path.read_text(encoding="utf-8").strip())

    def test_prompt_documentation_points_to_single_sources(self):
        docs = (PROJECT_ROOT / "docs" / "PROMPTS_IA.md").read_text(encoding="utf-8")

        self.assertIn("prompts/relatorio_trimestral.md", docs)
        self.assertIn("prompts/relatorio_anual.md", docs)
        self.assertNotIn("```markdown", docs)
        self.assertNotIn("REGRAS OBRIGATÓRIAS", docs)

    def test_quarterly_prompt_has_no_conflicting_page_guidance(self):
        prompt = (PROMPTS_DIR / "relatorio_trimestral.md").read_text(encoding="utf-8")

        self.assertNotIn("4 a 6 páginas", prompt)
        self.assertEqual(prompt.count("5 a 7 páginas"), 1)

    def test_annual_prompt_exists_for_external_chat(self):
        prompt = (PROMPTS_DIR / "relatorio_anual.md").read_text(encoding="utf-8")

        self.assertIn("Relatório Consultivo Anual Comparativo", prompt)
        self.assertIn("annual-1.2.0", prompt)


if __name__ == "__main__":
    unittest.main()
