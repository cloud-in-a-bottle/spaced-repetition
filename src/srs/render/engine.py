import attr
from jinja2 import StrictUndefined
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

from srs.domain.errors import InvalidRequest
from srs.render.context import RenderValue
from srs.repo.templates import Template

# Shown next to the lemma by the default templates, so left out of the features list.
_FEATURES_SHOWN_ELSEWHERE = frozenset({"article"})


def _features(value: dict[str, str]) -> str:
    return " · ".join(v for k, v in value.items() if v and k not in _FEATURES_SHOWN_ELSEWHERE)


def _make_env() -> SandboxedEnvironment:
    env = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    env.filters["features"] = _features
    return env


_ENV = _make_env()


@attr.s(auto_attribs=True, frozen=True)
class RenderedCard:
    front_html: str
    back_html: str


def _wrap(template: Template, body: str) -> str:
    return f'<style>{template.css}</style><div class="card kind-{template.kind} skill-{template.skill}">{body}</div>'


def render_card(template: Template, context: dict[str, RenderValue]) -> RenderedCard:
    """Render both sides. The back can include the rendered front with `{{ front_side }}`. Output is self-contained HTML (css
    included) that the client shows inside a shadow root, so template css can't leak into the app's own styling."""
    try:
        front = _ENV.from_string(template.front).render(context)
        back = _ENV.from_string(template.back).render({**context, "front_side": Markup(front)})
    except TemplateError as e:
        raise InvalidRequest(f"template {template.name!r} failed to render: {e}") from e
    return RenderedCard(front_html=_wrap(template, front), back_html=_wrap(template, back))
