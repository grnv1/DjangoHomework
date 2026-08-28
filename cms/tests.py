"""CMS 单元测试：模型约束、可见性规则、软删除、权限、查询与收藏。"""

import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from cms.forms import apply_role
from cms.models import Category, Favorite, Item, Tag


class CmsModelTests(TestCase):
    """数据模型行为测试。"""

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@test.com", "admin12345")
        self.editor = User.objects.create_user("wang", "wang@test.com", "wang12345")
        apply_role(self.editor, "editor")
        self.editor.save()
        self.category = Category.objects.create(
            name="科研成果", description="科研", created_by=self.admin, updated_by=self.admin
        )
        self.tag = Tag.objects.create(name="科研")
        self.now = timezone.now()

    def create_item(self, title="测试文章", status=Item.Status.PUBLISHED, publish_time=None):
        return Item.objects.create(
            title=title,
            content="正文",
            category=self.category,
            author=self.editor,
            status=status,
            publish_time=publish_time,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def test_visibility_rule(self):
        """仅"已发布且已到发表时间"的文章可见。"""
        past = self.create_item(title="已发布", publish_time=self.now - timedelta(days=1))
        future = self.create_item(title="定时", publish_time=self.now + timedelta(days=1))
        draft = self.create_item(title="草稿", status=Item.Status.DRAFT)
        self.assertTrue(past.is_visible())
        self.assertFalse(future.is_visible())
        self.assertFalse(draft.is_visible())

    def test_soft_delete_filters_default_manager(self):
        """软删除后默认管理器不再返回该记录。"""
        item = self.create_item()
        item.soft_delete(self.admin)
        self.assertFalse(Item.objects.filter(id=item.id).exists())
        self.assertTrue(Item.all_objects.filter(id=item.id).exists())

    def test_category_can_delete(self):
        """含文章栏目不可删，空栏目可删。"""
        self.create_item()
        self.assertFalse(self.category.can_delete())
        empty = Category.objects.create(name="空栏目", created_by=self.admin, updated_by=self.admin)
        self.assertTrue(empty.can_delete())

    def test_favorite_unique_constraint(self):
        """同一用户不能重复收藏同一文章。"""
        item = self.create_item()
        Favorite.objects.create(user=self.admin, item=item)
        with self.assertRaises(Exception):
            Favorite.objects.create(user=self.admin, item=item)


class CmsViewTests(TestCase):
    """视图行为测试：前台可见性、查询、权限、收藏、注册。"""

    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "admin@test.com", "admin12345")
        self.editor = User.objects.create_user("wang", "wang@test.com", "wang12345")
        apply_role(self.editor, "editor")
        self.editor.save()
        self.user = User.objects.create_user("zhangsan", "zhangsan@test.com", "zhangsan123")
        self.category = Category.objects.create(
            name="科研成果", created_by=self.admin, updated_by=self.admin
        )
        self.tag = Tag.objects.create(name="科研")
        self.now = timezone.now()
        self.published = self._item("已发布文章", publish_time=self.now)
        self.draft = self._item("草稿文章", status=Item.Status.DRAFT)
        self.future = self._item("定时文章", publish_time=self.now + timedelta(days=1))

    def _item(self, title, status=Item.Status.PUBLISHED, publish_time=None, author=None):
        author = author or self.editor
        return Item.objects.create(
            title=title, content="正文", category=self.category, author=author,
            status=status, publish_time=publish_time,
            created_by=author, updated_by=author,
        )

    def test_home_lists_only_visible(self):
        """主页仅展示可见文章。"""
        resp = self.client.get(reverse("cms:item_list"))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("已发布文章", content)
        self.assertNotIn("草稿文章", content)
        self.assertNotIn("定时文章", content)

    def test_detail_404_for_draft_and_future(self):
        """草稿与未到发表时间的文章详情返回 404。"""
        self.assertEqual(self.client.get(f"/item/{self.draft.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/item/{self.future.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/item/{self.published.id}/").status_code, 200)

    def test_search_by_title(self):
        resp = self.client.get(reverse("cms:item_list"), {"title": "已发布"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "已发布文章")

    def test_search_by_category(self):
        resp = self.client.get(reverse("cms:item_list"), {"category": self.category.id})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "已发布文章")

    def test_search_date_range_invalid(self):
        """日期区间反转时给出提示。"""
        resp = self.client.get(
            reverse("cms:item_list"), {"date_from": "2026-08-08", "date_to": "2026-01-01"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "起始日期不能晚于结束日期")

    def test_editor_cannot_access_superuser_pages(self):
        """内容管理员访问超管页面返回 403。"""
        self.client.login(username="wang", password="wang12345")
        self.assertEqual(self.client.get("/admin/user/").status_code, 403)
        self.assertEqual(self.client.get("/admin/log/").status_code, 403)

    def test_editor_cannot_edit_others_item(self):
        """内容管理员不能编辑他人文章。"""
        other = User.objects.create_user("li", "li@test.com", "li12345")
        apply_role(other, "editor")
        other.save()
        item = self._item("他人文章", author=other)
        self.client.login(username="wang", password="wang12345")
        self.assertEqual(self.client.get(f"/admin/item/{item.id}/edit/").status_code, 403)

    def test_editor_can_edit_own_item(self):
        """内容管理员可编辑自己的文章。"""
        self.client.login(username="wang", password="wang12345")
        self.assertEqual(self.client.get(f"/admin/item/{self.published.id}/edit/").status_code, 200)

    def _item_form_token(self, url):
        """从文章表单页提取一次性提交令牌。"""
        resp = self.client.get(url)
        m = re.search(r'name="submit_token" value="([^"]+)"', resp.content.decode())
        self.assertIsNotNone(m, "表单页缺少 submit_token")
        return m.group(1)

    def test_item_create_publish_action(self):
        """发布：作者自动取当前登录人，未填时间自动取当前时间。"""
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token("/admin/item/create/")
        resp = self.client.post("/admin/item/create/", {
            "title": "新文章",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "tags": [self.tag.id],
            "publish_time": "",
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(title="新文章")
        self.assertEqual(item.author, self.editor)
        self.assertEqual(item.status, Item.Status.PUBLISHED)

    def test_item_create_superuser_author_is_self(self):
        """超管新建文章：作者固定为当前登录人，POST 提交他人作者被忽略。"""
        self.client.login(username="admin", password="admin12345")
        token = self._item_form_token("/admin/item/create/")
        resp = self.client.post("/admin/item/create/", {
            "title": "超管文章",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "author": self.editor.id,
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(title="超管文章")
        self.assertEqual(item.author, self.admin)

    def test_item_edit_superuser_cannot_change_author(self):
        """超管编辑他人文章：作者保持原值，不可修改。"""
        other = User.objects.create_user("li", "li@test.com", "li12345")
        apply_role(other, "editor")
        other.save()
        item = self._item("超管编辑的作者", author=other)
        self.client.login(username="admin", password="admin12345")
        token = self._item_form_token(f"/admin/item/{item.id}/edit/")
        resp = self.client.post(f"/admin/item/{item.id}/edit/", {
            "title": "超管编辑的作者",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "author": self.admin.id,
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.author, other)


    def test_item_create_draft_action_keeps_publish_time(self):
        """存草稿：状态为草稿但保留发表时间，且可输入新标签自动创建。"""
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token("/admin/item/create/")
        resp = self.client.post("/admin/item/create/", {
            "title": "新增草稿文章",
            "content": "正文",
            "category": self.category.id,
            "action": "draft",
            "publish_time": "2026-12-31T08:00",
            "new_tags": "交通、智慧城市",
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(title="新增草稿文章")
        self.assertEqual(item.status, Item.Status.DRAFT)
        self.assertIsNotNone(item.publish_time)
        self.assertEqual(item.author, self.editor)
        self.assertEqual(set(item.tags.values_list("name", flat=True)), {"交通", "智慧城市"})

    def test_item_create_publish_rejects_past_time(self):
        """发布时填写过去时间：表单校验失败，文章不创建。"""
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token("/admin/item/create/")
        past = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post("/admin/item/create/", {
            "title": "过去时间文章",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "publish_time": past,
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "发布时间不能早于当前时间")
        self.assertFalse(Item.objects.filter(title="过去时间文章").exists())

    def test_item_edit_draft_can_change_publish_time(self):
        """编辑草稿：可修改发布时间。"""
        draft = self._item("可编辑草稿", status=Item.Status.DRAFT, publish_time=None)
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token(f"/admin/item/{draft.id}/edit/")
        new_time = (timezone.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        resp = self.client.post(f"/admin/item/{draft.id}/edit/", {
            "title": "可编辑草稿",
            "content": "正文",
            "category": self.category.id,
            "action": "draft",
            "publish_time": new_time,
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Item.Status.DRAFT)
        self.assertIsNotNone(draft.publish_time)

    def test_item_edit_published_keeps_time(self):
        """编辑已发布文章：时间字段禁用（浏览器不提交），保存后仍为原值。"""
        past = timezone.now() - timedelta(days=3)
        published = self._item("已发布不可改时间", publish_time=past)
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token(f"/admin/item/{published.id}/edit/")
        resp = self.client.post(f"/admin/item/{published.id}/edit/", {
            "title": "已发布不可改时间",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        published.refresh_from_db()
        self.assertEqual(published.publish_time.replace(microsecond=0),
                         past.replace(microsecond=0))

    def test_item_edit_published_old_time_ok(self):
        """编辑已发布旧文章（时间在过去）：正常保存，不因校验卡死。"""
        past = timezone.now() - timedelta(days=3)
        published = self._item("已发布旧文", publish_time=past)
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token(f"/admin/item/{published.id}/edit/")
        resp = self.client.post(f"/admin/item/{published.id}/edit/", {
            "title": "已发布旧文",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        published.refresh_from_db()
        self.assertEqual(published.status, Item.Status.PUBLISHED)
        self.assertEqual(published.publish_time.replace(microsecond=0),
                         past.replace(microsecond=0))

    def test_item_edit_published_cannot_revert_draft(self):
        """编辑已发布文章提交存草稿动作：仍保持已发布（强制重新发布）。"""
        past = timezone.now() - timedelta(days=1)
        published = self._item("已发布不许退回草稿", publish_time=past)
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token(f"/admin/item/{published.id}/edit/")
        resp = self.client.post(f"/admin/item/{published.id}/edit/", {
            "title": "已发布不许退回草稿",
            "content": "正文",
            "category": self.category.id,
            "action": "draft",
            "submit_token": token,
        })
        self.assertEqual(resp.status_code, 302)
        published.refresh_from_db()
        self.assertEqual(published.status, Item.Status.PUBLISHED)

    def test_item_create_rejects_duplicate_submit(self):
        """同一提交令牌重复使用：只创建一篇，并拦截重复提交。"""
        self.client.login(username="wang", password="wang12345")
        token = self._item_form_token("/admin/item/create/")
        data = {
            "title": "重复提交文章",
            "content": "正文",
            "category": self.category.id,
            "action": "publish",
            "submit_token": token,
        }
        first = self.client.post("/admin/item/create/", data)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(Item.objects.filter(title="重复提交文章").count(), 1)
        # 第二次携带同一令牌提交：被拦截，不产生新文章
        second = self.client.post("/admin/item/create/", data)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(Item.objects.filter(title="重复提交文章").count(), 1)

    def test_anonymous_favorite_redirects_to_login(self):
        resp = self.client.post(f"/favorite/toggle/{self.published.id}/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp["Location"])

    def test_favorite_toggle(self):
        """收藏与取消收藏切换。"""
        self.client.login(username="zhangsan", password="zhangsan123")
        resp = self.client.post(f"/favorite/toggle/{self.published.id}/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Favorite.objects.filter(user=self.user, item=self.published).exists())
        self.client.post(f"/favorite/toggle/{self.published.id}/")
        self.assertFalse(Favorite.objects.filter(user=self.user, item=self.published).exists())

    def test_register_creates_normal_user(self):
        """注册创建普通用户。"""
        resp = self.client.post("/register/", {
            "username": "lisi", "password1": "lisi12345678", "password2": "lisi12345678"
        })
        self.assertEqual(resp.status_code, 302)
        user = User.objects.get(username="lisi")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_page_size_controls_items_per_page(self):
        """page_size 白名单内生效，非法值回退默认。"""
        for i in range(12):
            self._item(f"分页文章{i}", publish_time=self.now - timedelta(days=1))
        url = reverse("cms:item_list")
        self.assertEqual(self.client.get(url).context["page_obj"].paginator.per_page, 10)
        self.assertEqual(
            self.client.get(url, {"page_size": "20"}).context["page_obj"].paginator.per_page, 20
        )
        self.assertEqual(
            self.client.get(url, {"page_size": "50"}).context["page_obj"].paginator.per_page, 50
        )
        # 超出白名单与非数字均回退默认值
        self.assertEqual(
            self.client.get(url, {"page_size": "999"}).context["page_obj"].paginator.per_page, 10
        )
        self.assertEqual(
            self.client.get(url, {"page_size": "abc"}).context["page_obj"].paginator.per_page, 10
        )

    def test_pagination_links_preserve_page_size(self):
        """翻页链接保留用户选择的 page_size。"""
        for i in range(15):
            self._item(f"分页文章{i}", publish_time=self.now - timedelta(days=1))
        resp = self.client.get(reverse("cms:item_list"), {"page_size": "10"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "page_size=10")

    def test_well_known_probe_returns_quiet(self):
        """浏览器/调试工具探测 .well-known/ 路径应静默返回，不再 404。"""
        resp = self.client.get("/.well-known/appspecific/com.chrome.devtools.json")
        self.assertEqual(resp.status_code, 204)
