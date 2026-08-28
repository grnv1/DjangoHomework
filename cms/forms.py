"""表单定义：注册、栏目、文章、后台用户管理等。"""

import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group, User
from django.utils import timezone

from .models import Category, Item

# 后台用户角色选项
ROLE_CHOICES = [
    ("user", "普通用户"),
    ("editor", "内容管理员"),
    ("superuser", "超级管理员"),
]


def get_role(user):
    """根据用户的权限字段推导其角色（用于表单初始值）。"""
    if user.is_superuser:
        return "superuser"
    if user.is_staff:
        return "editor"
    return "user"


def apply_role(user, role):
    """按角色设置权限字段并维护"内容管理员"用户组。

    权限设计：超级管理员（is_superuser）、内容管理员（is_staff + 用户组）、普通用户。
    """
    user.is_staff = role in ("editor", "superuser")
    user.is_superuser = role == "superuser"
    group, _ = Group.objects.get_or_create(name="内容管理员")
    if role == "editor":
        user.groups.add(group)
    else:
        user.groups.remove(group)


class CategoryForm(forms.ModelForm):
    """栏目表单：名称与简介。"""

    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class ItemForm(forms.ModelForm):
    """文章表单：标题、正文、栏目、标签、发表时间、作者。

    标签支持勾选已有标签，也可直接输入新标签名（保存时自动创建并关联）。
    状态与发表时间由视图根据"存草稿 / 发布"动作统一处理。
    """

    new_tags = forms.CharField(
        required=False,
        label="新增标签（可选）",
        widget=forms.TextInput(attrs={"placeholder": "例如：交通、智慧城市"}),
    )

    class Meta:
        model = Item
        fields = ["title", "content", "category", "tags", "publish_time", "author"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 14}),
            # datetime-local 输入框，值为 ISO 格式 %Y-%m-%dT%H:%M
            "publish_time": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "tags": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 不渲染 HTML5 required 属性，避免浏览器在存草稿时拦截空字段；
        # 必填校验统一交给服务端（发布时仍强制标题 / 正文 / 栏目 / 作者必填）。
        self.use_required_attribute = False
        # 发表时间可空：草稿时为空，发布时为空则由视图自动取当前时间
        self.fields["publish_time"].required = False
        self.fields["author"].label = "作者"
        # 存草稿时允许内容不完整：标题 / 正文 / 栏目 / 作者均可空；
        # 发布时保持必填，保证发布出去的文章信息完整。
        is_draft = (self.data or {}).get("action") == "draft"
        for name in ("title", "content", "category", "author"):
            if name in self.fields:
                self.fields[name].required = not is_draft

    def get_new_tag_names(self):
        """解析"新增标签"输入：按逗号 / 顿号 / 空白分隔并去除空项。"""
        raw = self.cleaned_data.get("new_tags", "")
        return [name for name in re.split(r"[,，、;；\s]+", raw) if name]

    def clean_publish_time(self):
        """校验发布时间：点「发布」时不允许早于当前时间。

        仅当浏览器本次实际提交了 publish_time（raw 非空）时才拦截；
        编辑已发布文章时该字段被 disabled，浏览器不提交，故校验自动跳过，
        避免已发布的旧文章（时间在过去）无法保存。
        """
        raw = (self.data or {}).get("publish_time", "").strip()
        publish_time = self.cleaned_data.get("publish_time")
        action = (self.data or {}).get("action")
        if (
            action == "publish"
            and publish_time
            and publish_time < timezone.now()
            and raw
        ):
            raise forms.ValidationError("发布时间不能早于当前时间")
        return publish_time


class RegisterForm(UserCreationForm):
    """前台用户自助注册表单（仅创建普通用户）。"""

    email = forms.EmailField(required=False, label="邮箱")

    class Meta:
        model = User
        fields = ["username", "email"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user


class UserCreateForm(forms.ModelForm):
    """后台新建用户表单：可创建普通用户 / 内容管理员 / 超级管理员。"""

    role = forms.ChoiceField(choices=ROLE_CHOICES, label="角色")
    password = forms.CharField(widget=forms.PasswordInput, label="密码")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="确认密码")

    class Meta:
        model = User
        fields = ["username", "email", "role", "password", "confirm_password"]

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            raise forms.ValidationError("两次输入的密码不一致。")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        apply_role(user, self.cleaned_data["role"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    """后台编辑用户表单：修改角色、启停账号、重置密码。"""

    role = forms.ChoiceField(choices=ROLE_CHOICES, label="角色")
    new_password = forms.CharField(
        required=False, widget=forms.PasswordInput, label="新密码（留空则不修改）"
    )

    class Meta:
        model = User
        fields = ["username", "email", "is_active", "role"]

    def save(self, commit=True):
        user = super().save(commit=False)
        apply_role(user, self.cleaned_data["role"])
        new_password = self.cleaned_data.get("new_password")
        if new_password:
            user.set_password(new_password)
        if commit:
            user.save()
        return user
