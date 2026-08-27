"""
URL 配置：前台路由与自建管理后台路由。
"""

from django.http import HttpResponse
from django.urls import include, path


def quiet_well_known(request, path=""):
    """浏览器/调试工具探测 .well-known/ 路径时静默返回，避免 404 刷屏。"""
    return HttpResponse(status=204)


urlpatterns = [
    path("admin/", include("cms.urls_admin")),
    path("", include("cms.urls")),
    path(".well-known/<path:path>", quiet_well_known, name="well_known"),
]
