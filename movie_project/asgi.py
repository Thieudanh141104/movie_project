"""
ASGI config for movie_project project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.urls import path
from app import consumers

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'movie_project.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter([
            # path("ws/app/movies/<str:movie_id>/", consumers.MovieConsumer.as_asgi()),
            # path("ws/app/users/<str:user_id>/", consumers.UserConsumer.as_asgi()),
        ])
    ),
})
