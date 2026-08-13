"""自建管理后台路由。"""

from django.urls import path

from cms import views

app_name = "admin_cms"

urlpatterns = [
    path("", views.manager.dashboard, name="dashboard"),
    # 栏目管理
    path("category/", views.manager.category_list, name="category_list"),
    path("category/create/", views.manager.category_create, name="category_create"),
    path("category/<int:id>/edit/", views.manager.category_edit, name="category_edit"),
    path("category/<int:id>/delete/", views.manager.category_delete, name="category_delete"),
    # 文章管理
    path("item/", views.manager.item_list, name="item_list"),
    path("item/create/", views.manager.item_create, name="item_create"),
    path("item/<int:id>/edit/", views.manager.item_edit, name="item_edit"),
    path("item/<int:id>/delete/", views.manager.item_delete, name="item_delete"),
    # 用户管理（仅超管）
    path("user/", views.manager.user_list, name="user_list"),
    path("user/create/", views.manager.user_create, name="user_create"),
    path("user/<int:id>/edit/", views.manager.user_edit, name="user_edit"),
    # 操作日志（仅超管）
    path("log/", views.manager.log_list, name="log_list"),
]
