from common.llm_service.prompt_manager import PromptManager


def test_render_familiarity_score_template():
    manager = PromptManager()

    text, version = manager.render(
        "familiarity_score.txt",
        title="Kal Ho Naa Ho",
        film="Kal Ho Naa Ho",
        year="2003",
        artist="Sonu Nigam",
    )

    assert "Kal Ho Naa Ho" in text
    assert "2003" in text
    assert version == "1"
    assert "prompt_version" not in text


def test_render_with_fixture_template(tmp_path):
    template_path = tmp_path / "greeting.txt"
    template_path.write_text("# prompt_version: 7\nHello {name}!\n")

    manager = PromptManager(prompts_dir=tmp_path)
    text, version = manager.render("greeting.txt", name="World")

    assert text == "Hello World!"
    assert version == "7"


def test_render_defaults_version_when_no_header(tmp_path):
    template_path = tmp_path / "plain.txt"
    template_path.write_text("Just text, no version header.")

    manager = PromptManager(prompts_dir=tmp_path)
    text, version = manager.render("plain.txt")

    assert version == "1"
    assert text == "Just text, no version header."
