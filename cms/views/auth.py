"""账号视图：注册、登录、登出。"""

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from cms.forms import RegisterForm


def register(request):
    """前台用户自助注册。"""
    if request.user.is_authenticated:
        return redirect("cms:item_list")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("cms:login")
    else:
        form = RegisterForm()
    return render(request, "cms/front/register.html", {"form": form})


def login_view(request):
    """用户登录（管理员与前台用户共用此入口）。"""
    if request.user.is_authenticated:
        return redirect("cms:item_list")
    next_url = request.GET.get("next", "")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            target = request.POST.get("next", "") or "/"
            # 防开放重定向：仅允许站内相对路径
            if not target.startswith("/") or target.startswith("//"):
                target = "/"
            return redirect(target)
    else:
        form = AuthenticationForm(request)
    return render(request, "cms/front/login.html", {"form": form, "next": next_url})


@login_required
@require_POST
def logout_view(request):
    """登出。"""
    logout(request)
    return redirect("cms:item_list")
