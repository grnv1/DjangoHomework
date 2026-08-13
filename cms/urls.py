"""前台与账号路由。"""

from django.urls import path

from cms import views

app_name = "cms"

urlpatterns = [
    # 前台浏览
    path("", views.front.item_list, name="item_list"),
    path("item/<int:id>/", views.front.item_detail, name="item_detail"),
    path("category/<int:id>/", views.front.category_detail, name="category_detail"),
    # 账号
    path("register/", views.auth.register, name="register"),
    path("login/", views.auth.login_view, name="login"),
    path("logout/", views.auth.logout_view, name="logout"),
    # 收藏
    path("favorites/", views.front.favorites, name="favorites"),
    path("favorite/toggle/<int:item_id>/", views.front.favorite_toggle, name="favorite_toggle"),
]
