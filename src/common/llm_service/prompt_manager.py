from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_VERSION_PREFIX = "# prompt_version:"
_DEFAULT_VERSION = "1"


class PromptManager:
    """Loads, renders, and versions prompt templates. Consumers never
    hand-format strings.
    """

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        self._prompts_dir = Path(prompts_dir) if prompts_dir is not None else _PROMPTS_DIR

    def render(self, template_name: str, **placeholders: str) -> tuple[str, str]:
        """Returns (rendered_prompt, prompt_version)."""
        template, version = self._load(template_name)
        return template.format(**placeholders), version

    def _load(self, template_name: str) -> tuple[str, str]:
        path = self._prompts_dir / template_name
        lines = path.read_text().splitlines()

        version = _DEFAULT_VERSION
        if lines and lines[0].strip().startswith(_VERSION_PREFIX):
            version = lines[0].strip()[len(_VERSION_PREFIX) :].strip()
            lines = lines[1:]

        return "\n".join(lines).strip("\n"), version
