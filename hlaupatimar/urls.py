from django.contrib import admin
from django.urls import path, include
from ninja import NinjaAPI
from races.api import router as races_router

# Create the main API instance
api = NinjaAPI(
    title="Hlaupatimar API",
    description="API for Icelandic running competitions data aggregation",
    version="1.0.0"
)

# Add routers
api.add_router("/races", races_router, tags=["Races"])

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
]
