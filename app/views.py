from pathlib import Path
from fastapi.templating import Jinja2Templates
from .security import csrf_token

templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))


def render(request, name, status_code=200, **context):
    settings = request.app.state.settings
    return templates.TemplateResponse(request=request, name=name, context={
        'app_name': settings.app_name,
        'google_enabled': settings.google_enabled,
        'csrf': csrf_token(request),
        **context,
    }, status_code=status_code)
