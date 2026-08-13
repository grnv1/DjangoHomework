"""
URL 配置：前台路由与自建管理后台路由。
"""

from django.urls import include, path

urlpatterns = [
    path("admin/", include("cms.urls_admin")),
    path("", include("cms.urls")),
]
