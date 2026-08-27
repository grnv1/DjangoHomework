"""示例数据脚本。

用法：python manage.py seed
创建演示用的用户、栏目、标签与文章，便于快速体验系统功能。
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from cms.forms import apply_role
from cms.models import Category, Favorite, Item, OperationLog, Tag


class Command(BaseCommand):
    help = "创建演示用示例数据（用户、栏目、标签、文章）"

    def handle(self, *args, **options):
        # ---------- 用户 ----------
        admin = self._create_user("admin", "admin12345", "admin@bjtu.edu.cn", "superuser")
        editor = self._create_user("wang", "wang12345", "wang@bjtu.edu.cn", "editor")
        zhangsan = self._create_user("zhangsan", "zhangsan123", "zhangsan@example.com", "user")

        # ---------- 栏目 ----------
        category_data = [
            ("教学动态", "教学安排与课堂改革信息"),
            ("科研成果", "各学科科研团队最新成果"),
            ("校园通知", "学校公告与通知事项"),
        ]
        categories = {}
        for name, desc in category_data:
            category, _ = Category.objects.get_or_create(
                name=name,
                defaults={"description": desc, "created_by": admin, "updated_by": admin},
            )
            categories[name] = category

        # ---------- 标签 ----------
        tags = {name: Tag.objects.get_or_create(name=name)[0] for name in ["科研", "就业", "招生"]}

        # ---------- 文章 ----------
        now = timezone.now()
        articles = [
            # (标题, 栏目, 标签列表, 作者, 发表时间)；发表时间为 None 表示草稿
            ("交大轨道交通新型轴承技术取得阶段性突破", "科研成果", ["科研"], editor,
             now - timedelta(days=8)),
            ("智能交通系统在城市道路中的应用研究", "科研成果", ["科研"], editor,
             now - timedelta(days=16)),
            ("2026年秋季学期本科教学安排", "教学动态", [], admin, now - timedelta(days=3)),
            # 定时发布：发表时间为未来时间
            ("2026年硕士研究生招生简章", "校园通知", ["招生"], admin, now + timedelta(days=5)),
            # 草稿：发表时间为空
            ("大学生就业指导讲座预告（草稿）", "校园通知", ["就业"], editor, None),
            # 一篇文章可关联多个标签（关键词）
            ("轨道交通领域产学研协同育人模式研究", "科研成果", ["科研", "就业"], editor,
             now - timedelta(days=5)),
            ("研究生招生政策与就业前景解读", "校园通知", ["招生", "就业"], admin,
             now - timedelta(days=2)),
            ("2026届毕业生求职与深造策略分析", "教学动态", ["就业", "科研"], editor,
             now - timedelta(days=1)),
        ]
        for title, category_name, tag_names, author, publish_time in articles:
            item, created = Item.objects.get_or_create(
                title=title,
                defaults={
                    "content": f"这里是《{title}》的正文内容示例，用于演示系统功能。",
                    "category": categories[category_name],
                    "author": author,
                    "created_by": author,
                    "updated_by": author,
                    "status": Item.Status.PUBLISHED if publish_time else Item.Status.DRAFT,
                    "publish_time": publish_time,
                },
            )
            if created:
                for tag_name in tag_names:
                    item.tags.add(tags[tag_name])
                description = f"创建文章《{item.title}》"
                OperationLog.log(author, OperationLog.Action.CREATE, item, description)

        # ---------- 批量生成文章，便于测试分页 ----------
        category_names = list(categories)
        tag_names_list = list(tags)
        batch_count = 30
        for i in range(1, batch_count + 1):
            title = f"分页测试文章 {i:02d}"
            category_name = category_names[i % len(category_names)]
            author = editor if i % 2 else admin
            publish_time = now - timedelta(days=i)
            item, created = Item.objects.get_or_create(
                title=title,
                defaults={
                    "content": f"这是用于验证分页效果的测试文章《{title}》。",
                    "category": categories[category_name],
                    "author": author,
                    "created_by": author,
                    "updated_by": author,
                    "status": Item.Status.PUBLISHED,
                    "publish_time": publish_time,
                    "views": i * 7 % 100,
                },
            )
            if created:
                item.tags.add(tags[tag_names_list[i % len(tag_names_list)]])
                OperationLog.log(author, OperationLog.Action.CREATE, item, f"创建文章《{title}》")

        # ---------- 为普通用户 zhangsan 添加收藏 ----------
        fav_targets = Item.objects.filter(status=Item.Status.PUBLISHED).order_by("-publish_time")[:5]
        for item in fav_targets:
            Favorite.objects.get_or_create(user=zhangsan, item=item)

        self.stdout.write(self.style.SUCCESS("示例数据创建完成。"))
        self.stdout.write(f"已生成 {Item.objects.count()} 篇文章，其中可见（已发布且已到时间）"
                          f"{sum(1 for it in Item.objects.all() if it.is_visible())} 篇。")
        self.stdout.write("超级管理员：admin / admin12345")
        self.stdout.write("内容管理员：wang / wang12345")
        self.stdout.write("普通用户：zhangsan / zhangsan123")

    def _create_user(self, username, password, email, role):
        """创建或更新演示用户并应用角色。"""
        user, _ = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.email = email
        user.is_active = True
        apply_role(user, role)
        user.save()
        return user
