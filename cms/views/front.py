"""前台视图：文章列表、文章详情、栏目页、收藏。"""

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cms.models import Category, Favorite, Item, Tag
from cms.utils import (
    build_search_queryset,
    get_visible_items,
    paginate,
    query_string_without_page,
)


def item_list(request):
    """前台主页：文章列表 + 查询 + 分页。"""
    qs, form_values, error = build_search_queryset(request)
    qs = qs.select_related("category").prefetch_related("tags")
    page_obj = paginate(request, qs, settings.PAGE_SIZE)
    return render(request, "cms/front/index.html", {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "tags": Tag.objects.all(),
        "form_values": form_values,
        "error": error,
        "action_url": "/",
        "include_category": True,
        "query_string": query_string_without_page(request),
    })


def item_detail(request, id):
    """文章详情：浏览量 +1，展示标签与收藏按钮。"""
    item = get_object_or_404(
        Item.objects.select_related("category", "author").prefetch_related("tags"),
        id=id,
    )
    # 草稿、未到发表时间或已删除的文章对普通用户一律 404
    if not item.is_visible():
        raise Http404("文章不存在或不可见")
    # 原子自增浏览量，避免并发重复读
    Item.objects.filter(id=item.id).update(views=F("views") + 1)
    item.views += 1
    is_favorited = (
        request.user.is_authenticated
        and Favorite.objects.filter(user=request.user, item=item).exists()
    )
    return render(request, "cms/front/item_detail.html", {
        "item": item,
        "is_favorited": is_favorited,
    })


def category_detail(request, id):
    """栏目页：栏目内查询（标题 / 时间 / 标签）+ 文章列表 + 分页。"""
    category = get_object_or_404(Category, id=id)
    base_qs = (
        get_visible_items()
        .filter(category=category)
        .select_related("category")
        .prefetch_related("tags")
    )
    qs, form_values, error = build_search_queryset(request, base_qs)
    page_obj = paginate(request, qs, settings.PAGE_SIZE)
    return render(request, "cms/front/category_detail.html", {
        "category": category,
        "page_obj": page_obj,
        "tags": Tag.objects.all(),
        "form_values": form_values,
        "error": error,
        "action_url": f"/category/{id}/",
        "include_category": False,
        "query_string": query_string_without_page(request),
    })


@login_required
def favorites(request):
    """我的收藏：仅展示未删除且可见的文章。"""
    favs = Favorite.objects.filter(
        user=request.user,
        item__is_deleted=False,
        item__status=Item.Status.PUBLISHED,
        item__publish_time__lte=timezone.now(),
    ).select_related("item", "item__category")
    page_obj = paginate(request, favs, settings.PAGE_SIZE)
    return render(request, "cms/front/favorites.html", {
        "page_obj": page_obj,
        "query_string": query_string_without_page(request),
    })


@login_required
def favorite_toggle(request, item_id):
    """收藏 / 取消收藏（PRG 模式，重定向回文章详情页）。"""
    item = get_object_or_404(Item, id=item_id)
    if not item.is_visible():
        raise Http404("文章不存在或不可见")
    favorite, created = Favorite.objects.get_or_create(user=request.user, item=item)
    if not created:
        # 已收藏则取消
        favorite.delete()
    return redirect("cms:item_detail", id=item_id)
