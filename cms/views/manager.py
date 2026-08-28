"""管理后台视图：后台首页、栏目/文章/用户管理、操作日志。"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cms.forms import CategoryForm, ItemForm, UserCreateForm, UserEditForm, get_role
from cms.models import Category, Item, OperationLog, Tag
from cms.utils import (
    paginate,
    query_string_without_page,
    staff_required,
    superuser_required,
    consume_form_token,
    generate_form_token,
)


@staff_required
def dashboard(request):
    """后台首页：统计概览。

    统计范围与文章管理一致：超级管理员见全部，内容管理员仅见自己创建的文章。
    """
    items = _get_manageable_items(request.user)
    now = timezone.now()
    return render(request, "cms/admin/dashboard.html", {
        "total_items": items.count(),
        "published_items": items.filter(
            status=Item.Status.PUBLISHED, publish_time__lte=now
        ).count(),
        "scheduled_items": items.filter(
            status=Item.Status.PUBLISHED, publish_time__gt=now
        ).count(),
        "draft_items": items.filter(status=Item.Status.DRAFT).count(),
        "total_categories": Category.objects.count(),
    })


# ------------------------------ 栏目管理 ------------------------------

@staff_required
def category_list(request):
    """栏目列表。"""
    categories = Category.objects.all()
    return render(request, "cms/admin/category_list.html", {"categories": categories})


@staff_required
def category_create(request):
    """新建栏目。"""
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.updated_by = request.user
            obj.save()
            description = f"创建栏目《{obj.name}》"
            OperationLog.log(request.user, OperationLog.Action.CREATE, obj, description)
            messages.success(request, "栏目创建成功。")
            return redirect("admin_cms:category_list")
    else:
        form = CategoryForm()
    return render(request, "cms/admin/category_form.html", {"form": form, "title": "新建栏目"})


@staff_required
def category_edit(request, id):
    """编辑栏目。"""
    obj = get_object_or_404(Category, id=id)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            description = f"更新栏目《{obj.name}》"
            OperationLog.log(request.user, OperationLog.Action.UPDATE, obj, description)
            messages.success(request, "栏目更新成功。")
            return redirect("admin_cms:category_list")
    else:
        form = CategoryForm(instance=obj)
    return render(request, "cms/admin/category_form.html", {"form": form, "title": "编辑栏目"})


@staff_required
def category_delete(request, id):
    """删除栏目：软删除，且仅允许删除空栏目。"""
    obj = get_object_or_404(Category, id=id)
    if not obj.can_delete():
        messages.error(request, "该栏目下存在文章，不能删除。")
        return redirect("admin_cms:category_list")
    if request.method == "POST":
        obj.soft_delete(request.user)
        OperationLog.log(request.user, OperationLog.Action.DELETE, obj, f"删除栏目《{obj.name}》")
        messages.success(request, "栏目已删除。")
        return redirect("admin_cms:category_list")
    return render(request, "cms/admin/category_confirm_delete.html", {"obj": obj})


# ------------------------------ 文章管理 ------------------------------

def _get_manageable_items(user):
    """管理端可见文章：超级管理员全部，内容管理员仅本人创建。"""
    qs = Item.objects.select_related("category", "author")
    if not user.is_superuser:
        qs = qs.filter(author=user)
    return qs


def _check_item_permission(request, item):
    """内容管理员仅能操作自己创建的文章，否则 403。"""
    if not request.user.is_superuser and item.author_id != request.user.id:
        raise PermissionDenied


def _apply_item_action(obj, action):
    """按提交动作设置文章状态与发表时间。

    draft（存草稿）：状态置为草稿，保留已填写的发表时间（便于下次发布）；
    publish（发布）：状态置为已发布，发表时间为空则自动取当前时间。
    """
    if action == "draft":
        obj.status = Item.Status.DRAFT
    else:
        obj.status = Item.Status.PUBLISHED
        if not obj.publish_time:
            obj.publish_time = timezone.now()


def _add_new_tags(form, item):
    """创建表单中输入的新标签并关联到文章。"""
    for name in form.get_new_tag_names():
        tag, _ = Tag.objects.get_or_create(name=name)
        item.tags.add(tag)


@staff_required
def item_list(request):
    """文章列表：支持按标题 / 栏目 / 状态筛选。"""
    qs = _get_manageable_items(request.user)
    title = request.GET.get("title", "").strip()
    category_id = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    if title:
        qs = qs.filter(title__icontains=title)
    if category_id:
        qs = qs.filter(category_id=category_id)
    if status:
        qs = qs.filter(status=status)
    page_obj = paginate(request, qs, settings.ADMIN_PAGE_SIZE)
    return render(request, "cms/admin/item_list.html", {
        "page_obj": page_obj,
        "categories": Category.objects.all(),
        "form_values": {"title": title, "category": category_id, "status": status},
        "is_editor": not request.user.is_superuser,
        "query_string": query_string_without_page(request),
    })


@staff_required
def item_create(request):
    """新建文章：作者默认为当前登录人，不可指定或修改。"""
    form = ItemForm(request.POST or None)
    form.fields.pop("author")
    if request.method == "POST" and form.is_valid():
        if not consume_form_token(request, request.POST.get("submit_token")):
            # 令牌已使用：拦截重复提交，避免创建重复文章
            messages.warning(request, "请勿重复提交，该文章可能已保存。")
            return redirect("admin_cms:item_list")
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.updated_by = request.user
        obj.author = request.user
        _apply_item_action(obj, request.POST.get("action"))
        obj.save()
        form.save_m2m()
        _add_new_tags(form, obj)
        OperationLog.log(request.user, OperationLog.Action.CREATE, obj, f"创建文章《{obj.title}》")
        messages.success(request, "文章创建成功。")
        return redirect("admin_cms:item_list")
    return render(request, "cms/admin/item_form.html", {
        "form": form,
        "title": "新建文章",
        "is_editor": not request.user.is_superuser,
        "is_published": False,
        "submit_token": generate_form_token(request),
    })


@staff_required
def item_edit(request, id):
    """编辑文章：内容管理员仅可编辑自己创建的文章。

    已发布文章：发布时间锁定不可改，且只能「重新发布」（强制按发布处理，
    忽略存草稿动作，防止已发布文章退回草稿）；草稿文章：时间可修改。
    """
    obj = get_object_or_404(Item, id=id)
    _check_item_permission(request, obj)
    is_published = obj.status == Item.Status.PUBLISHED
    # 已发布文章只能「重新发布」，忽略存草稿动作，防止已发布文章退回草稿；
    # 需在创建表单前改写，保证表单校验按 publish 处理
    if is_published and request.method == "POST" and (request.POST or {}).get("action") == "draft":
        request.POST = request.POST.copy()
        request.POST["action"] = "publish"
    form = ItemForm(request.POST or None, instance=obj)
    form.fields.pop("author")
    if is_published:
        form.fields["publish_time"].disabled = True
    if request.method == "POST" and form.is_valid():
        if not consume_form_token(request, request.POST.get("submit_token")):
            # 令牌已使用：拦截重复提交，避免重复保存与重复记日志
            messages.warning(request, "请勿重复提交，该文章可能已保存。")
            return redirect("admin_cms:item_list")
        obj = form.save(commit=False)
        obj.updated_by = request.user
        _apply_item_action(obj, request.POST.get("action"))
        obj.save()
        form.save_m2m()
        _add_new_tags(form, obj)
        OperationLog.log(request.user, OperationLog.Action.UPDATE, obj, f"更新文章《{obj.title}》")
        messages.success(request, "文章更新成功。")
        return redirect("admin_cms:item_list")
    return render(request, "cms/admin/item_form.html", {
        "form": form,
        "title": "编辑文章",
        "is_editor": not request.user.is_superuser,
        "is_published": is_published,
        "submit_token": generate_form_token(request),
    })


@staff_required
def item_delete(request, id):
    """删除文章：软删除。"""
    obj = get_object_or_404(Item, id=id)
    _check_item_permission(request, obj)
    if request.method == "POST":
        obj.soft_delete(request.user)
        OperationLog.log(request.user, OperationLog.Action.DELETE, obj, f"删除文章《{obj.title}》")
        messages.success(request, "文章已删除。")
        return redirect("admin_cms:item_list")
    return render(request, "cms/admin/item_confirm_delete.html", {"obj": obj})


# ------------------------------ 用户管理（仅超管） ------------------------------

@superuser_required
def user_list(request):
    """用户列表。"""
    users = User.objects.order_by("id")
    return render(request, "cms/admin/user_list.html", {"users": users})


@superuser_required
def user_create(request):
    """新建用户：可创建普通用户 / 内容管理员 / 超级管理员。"""
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "用户创建成功。")
            return redirect("admin_cms:user_list")
    else:
        form = UserCreateForm()
    return render(request, "cms/admin/user_form.html", {"form": form, "title": "新建用户"})


@superuser_required
def user_edit(request, id):
    """编辑用户：禁止操作自己（不可停用 / 降权 / 移除管理角色）。"""
    user = get_object_or_404(User, id=id)
    is_self = user.id == request.user.id
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            if is_self:
                # 自保护：强制保持自身为启用的超级管理员
                if form.cleaned_data["role"] != "superuser" or form.cleaned_data["is_active"] != True:
                    form.add_error(None, "不能修改自己的角色或启用状态。")
                else:
                    form.save()
                    messages.success(request, "用户更新成功。")
                    return redirect("admin_cms:user_list")
    else:
        form = UserEditForm(instance=user, initial={"role": get_role(user)})
    return render(request, "cms/admin/user_form.html", {
        "form": form,
        "title": "编辑用户",
        "is_self": is_self,
    })


# ------------------------------ 操作日志（仅超管） ------------------------------

@superuser_required
def log_list(request):
    """操作日志列表。"""
    logs = OperationLog.objects.select_related("operator")
    page_obj = paginate(request, logs, settings.ADMIN_PAGE_SIZE)
    return render(request, "cms/admin/log_list.html", {
        "page_obj": page_obj,
        "query_string": query_string_without_page(request),
    })
