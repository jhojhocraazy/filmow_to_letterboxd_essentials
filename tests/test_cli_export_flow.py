"""Testes offline do fluxo de configuração da CLI.

Estes testes descrevem o contrato público planejado para a seleção de formato,
origem da nota e confirmação antes de iniciar uma exportação. Eles não acessam a
rede, não carregam a credencial do TMDb e não leem ``tmdb_api.txt``.
"""

import io
import unittest
from unittest.mock import Mock, patch

from rich.console import Console

import filmow_to_letterboxd_essentials as app


class MenuSelectionTests(unittest.TestCase):
    def setUp(self):
        # A CLI usa o console global; isolá-lo mantém os testes offline e evita
        # depender de terminal, terminal virtual ou da credencial carregada pelo main.
        self.console = Mock()
        self.console_patcher = patch.object(app, "console", self.console)
        self.console_patcher.start()
        self.addCleanup(self.console_patcher.stop)

    def test_menu_accepts_all_export_choices_and_help(self):
        expected = {
            "1": "analitica",
            "2": "sintetica",
            "3": "letterboxd",
            "4": "trakt",
        }
        for entrada, modo in expected.items():
            with self.subTest(entrada=entrada), patch("builtins.input", return_value=entrada):
                self.assertEqual(app.exibir_menu_e_obter_selecao(), modo)

        # H é a entrada de ajuda planejada; não se fornece outra entrada para
        # que uma implementação sem suporte a H falhe, em vez de ficar em loop.
        with patch("builtins.input", side_effect=["H"]):
            self.assertEqual(app.exibir_menu_e_obter_selecao(), "DOC")

    def test_help_renders_with_real_rich_console(self):
        output = io.StringIO()
        console_real = Console(file=output, force_terminal=False, width=80)
        with patch.object(app, "console", console_real):
            app.exibir_documentacao()
        rendered = output.getvalue()
        self.assertIn("GUIA RÁPIDO", rendered)
        self.assertIn("DESEMPENHO", rendered)
        self.assertIn("AJUDA E ARQUITETURA", rendered)

    def test_help_input_is_not_interpreted_as_markup(self):
        output = io.StringIO()
        console_real = Console(file=output, force_terminal=False, width=80)
        with patch.object(app, "console", console_real), patch(
            "builtins.input", return_value="1"
        ):
            self.assertTrue(
                app.confirmar_configuracao_exportacao(
                    "perfil[/bold white]", "letterboxd", "filmow"
                )
            )
        self.assertIn("perfil", output.getvalue())
    def test_menu_transition_clears_screen_before_new_screen(self):
        with patch.object(app, "limpar_tela") as limpar:
            app.limpar_para_menu()
        limpar.assert_called_once_with()

    def test_menu_rejects_invalid_choice_before_accepting_a_valid_one(self):
        with patch("builtins.input", side_effect=["x", "2"]):
            self.assertEqual(app.exibir_menu_e_obter_selecao(), "sintetica")
        self.assertTrue(self.console.print.called)

    def test_menu_zero_exits_without_returning_a_mode(self):
        with patch("builtins.input", return_value="0"), self.assertRaises(SystemExit) as exit_info:
            app.exibir_menu_e_obter_selecao()
        self.assertEqual(exit_info.exception.code, 0)


class ExportConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.console = Mock()
        self.console_patcher = patch.object(app, "console", self.console)
        self.console_patcher.start()
        self.addCleanup(self.console_patcher.stop)

    def test_modes_requiring_imdb_follow_the_selected_contract(self):
        self.assertTrue(app.modo_precisa_imdb("analitica"))
        self.assertFalse(app.modo_precisa_imdb("sintetica"))
        self.assertTrue(app.modo_precisa_imdb("letterboxd", "imdb"))
        self.assertTrue(app.modo_precisa_imdb("trakt", "imdb"))

    def test_origin_prompt_accepts_both_supported_choices(self):
        with patch("builtins.input", side_effect=["1", "2"]):
            self.assertEqual(app.obter_origem_nota("letterboxd"), "filmow")
            self.assertEqual(app.obter_origem_nota("trakt"), "imdb")

    def test_origin_prompt_rejects_an_unknown_choice(self):
        with patch("builtins.input", side_effect=["x", "2"]):
            self.assertEqual(app.obter_origem_nota("trakt"), "imdb")
        self.assertTrue(self.console.print.called)

    def test_confirmation_declines_before_export(self):
        with patch("builtins.input", return_value="2"):
            self.assertFalse(
                app.confirmar_configuracao_exportacao("usuario", "trakt", "imdb")
            )

    def test_confirmation_accepts_before_export(self):
        with patch("builtins.input", return_value="1"):
            self.assertTrue(
                app.confirmar_configuracao_exportacao("usuario", "letterboxd", "filmow")
            )


class MainFlowTests(unittest.TestCase):
    """Verifica o roteamento do menu sem executar a coleta de dados."""

    def setUp(self):
        self.console = Mock()
        self.console.input.return_value = ""
        self.console_patcher = patch.object(app, "console", self.console)
        self.console_patcher.start()
        self.addCleanup(self.console_patcher.stop)

    def _executar_ate_a_primeira_coleta(self, modo, origem):
        """Executa main até a extração, que é deliberadamente interrompida.

        O objetivo é observar somente a configuração; a exceção impede qualquer
        chamada de rede ou gravação de artefatos de exportação.
        """
        with patch.object(app, "limpar_tela"), \
             patch.object(app, "limpar_para_menu"), \
             patch.object(app, "carregar_credencial", return_value="offline"), \
             patch.object(app, "carregar_datasets_imdb", return_value={}), \
             patch.object(app, "criar_sessao_filmow", return_value=Mock()), \
             patch.object(app, "exibir_menu_e_obter_selecao", side_effect=[modo, SystemExit(0)]), \
             patch.object(app, "obter_origem_nota", return_value=origem) as obter_origem, \
             patch.object(app, "confirmar_configuracao_exportacao", return_value=True), \
             patch.object(app, "extrair_historico_completo", side_effect=RuntimeError("teste offline")), \
             patch("builtins.input", return_value="usuario"):
            with self.assertRaises(SystemExit):
                app.main()
        return obter_origem

    def test_analitica_does_not_ask_for_note_origin(self):
        obter_origem = self._executar_ate_a_primeira_coleta("analitica", "filmow")
        obter_origem.assert_not_called()

    def test_sintetica_does_not_ask_for_note_origin(self):
        obter_origem = self._executar_ate_a_primeira_coleta("sintetica", "imdb")
        obter_origem.assert_not_called()

    def test_letterboxd_asks_for_note_origin(self):
        obter_origem = self._executar_ate_a_primeira_coleta("letterboxd", "filmow")
        obter_origem.assert_called_once_with("letterboxd")

    def test_trakt_asks_for_note_origin(self):
        obter_origem = self._executar_ate_a_primeira_coleta("trakt", "imdb")
        obter_origem.assert_called_once_with("trakt")


if __name__ == "__main__":
    unittest.main()
