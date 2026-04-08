from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.services.tunator_service import TunatorService


def create_app() -> FastAPI:
    app = FastAPI(title="Tunator API", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            'http://127.0.0.1:8000',
            'http://localhost:8000',
            'http://127.0.0.1:5173',
            'http://localhost:5173',
        ],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    app.state.tunator = TunatorService.bootstrap()
    app.include_router(router)

    frontend_dist = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
    assets_dir = frontend_dist / 'assets'

    if assets_dir.exists():
        app.mount('/assets', StaticFiles(directory=assets_dir), name='assets')

    if frontend_dist.exists():
        @app.get('/', include_in_schema=False)
        def frontend_index() -> FileResponse:
            return FileResponse(frontend_dist / 'index.html')

        @app.get('/app', include_in_schema=False)
        def frontend_app() -> FileResponse:
            return FileResponse(frontend_dist / 'index.html')

    return app


app = create_app()
