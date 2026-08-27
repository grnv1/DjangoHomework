"""公共工具：权限装饰器、查询过滤、分页等辅助函数。"""

import secrets
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import redirect
from django.utils import timezone

from .models import Item


def staff_required(view_func):
    """要求登录且为管理员（is_staff），否则重定向到前台首页。"""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            return redirect("cms:item_list")
        return view_func(request, *args, **kwargs)

    return wrapper


def superuser_required(view_func):
    """要求超级管理员，否则返回 403。"""

    @wraps(view_func)
    @staff_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def generate_form_token(request):
    """为表单生成一次性提交令牌（防重复提交），存入 session。

    渲染表单页时调用；仅在保存成功后由 consume_form_token 消费，
    从而拦截双击 / 重复提交导致的重复写入。
    """
    token = secrets.token_hex(16)
    pending = list(request.session.get("_pending_tokens", []))
    pending.append(token)
    # 仅保留最近 20 个令牌，防止 session 无限膨胀
    del pending[:-20]
    request.session["_pending_tokens"] = pending
    return token


def consume_form_token(request, token):
    """校验并消费提交令牌。

    令牌存在则移除并返回 True；缺失或已被使用（即重复提交）返回 False。
    """
    if not token:
        return False
    pending = list(request.session.get("_pending_tokens", []))
    if token in pending:
        pending.remove(token)
        request.session["_pending_tokens"] = pending
        return True
    return False


def get_visible_items():
    """返回前台可见文章查询集：已发布且已到发表时间。

    未删除记录由默认管理器（ActiveManager）自动过滤。
    """
    return Item.objects.filter(
        status=Item.Status.PUBLISHED,
        publish_time__lte=timezone.now(),
    )


def build_search_queryset(request, base_qs=None):
    """根据 GET 查询参数过滤文章，返回 (qs, form_values, error)。

    支持查询项：标题（模糊）、发表时间区间（起止日期）、栏目（精确）、标签（精确）。
    多个条件同时填写时为 AND 组合过滤；日期区间反转时返回错误提示。
    """
    if base_qs is None:
        base_qs = get_visible_items()

    title = request.GET.get("title", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    category_id = request.GET.get("category", "").strip()
    tag_id = request.GET.get("tag", "").strip()
    error = ""

    if title:
        base_qs = base_qs.filter(title__icontains=title)
    if date_from and date_to and date_from > date_to:
        error = "起始日期不能晚于结束日期。"
    if date_from:
        base_qs = base_qs.filter(publish_time__date__gte=date_from)
    if date_to:
        base_qs = base_qs.filter(publish_time__date__lte=date_to)
    if category_id:
        base_qs = base_qs.filter(category_id=category_id)
    if tag_id:
        base_qs = base_qs.filter(tags__id=tag_id)

    form_values = {
        "title": title,
        "date_from": date_from,
        "date_to": date_to,
        "category": category_id,
        "tag": tag_id,
    }
    return base_qs, form_values, error


def paginate(request, queryset, per_page):
    """按页码分页，返回 Paginator 页面对象。"""
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


def query_string_without_page(request):
    """保留除 page 外的查询参数，用于分页链接拼接。"""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()
