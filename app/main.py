from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.routers import home, orders, servers, validate_servers, assets, upload_assets, add_order, sites, ips, catalog, vlans

app = FastAPI()

app.include_router(home.router)
app.include_router(orders.router)
app.include_router(servers.router)
app.include_router(validate_servers.router)
app.include_router(assets.router)
app.include_router(upload_assets.router)
app.include_router(add_order.router)
app.include_router(sites.router)
app.include_router(ips.router)
app.include_router(catalog.router)
app.include_router(vlans.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
