"""CMS 数据模型定义。

包含：Category（栏目）、Item（文章）、Tag（标签）、Favorite（收藏）、
OperationLog（操作日志），以及公共抽象基类 BaseModel。
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class ActiveManager(models.Manager):
    """默认管理器：仅返回未删除（软删除标记为 False）的记录。"""

    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class BaseModel(models.Model):
    """公共抽象基类：记录创建/更新信息与软删除标记。

    所有内容实体（栏目、文章）继承此类，保证
    创建时间/操作人、更新时间/操作人、软删除信息的一致性。
    """

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="创建人",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="更新人",
    )
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="是否已删除")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="删除时间")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name="删除人",
    )

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user):
        """软删除：仅置删除标记并记录删除人与时间，不物理删除数据。"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


class Category(BaseModel):
    """栏目：内容分组，如"教学动态""科研成果"。"""

    name = models.CharField(max_length=50, unique=True, verbose_name="栏目名称")
    description = models.TextField(blank=True, verbose_name="栏目简介")

    class Meta:
        verbose_name = "栏目"
        verbose_name_plural = "栏目"
        ordering = ["id"]
        # 反向关系（如 category.items）默认使用过滤了软删除的默认管理器
        base_manager_name = "objects"

    def __str__(self):
        return self.name

    def can_delete(self):
        """是否可删除：栏目下无未删除的文章。"""
        return not self.items.exists()


class Tag(models.Model):
    """标签：文章的多对多标签。"""

    name = models.CharField(max_length=50, unique=True, verbose_name="标签名称")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "标签"
        verbose_name_plural = "标签"
        ordering = ["id"]

    def __str__(self):
        return self.name


class Item(BaseModel):
    """文章：CMS 的核心内容实体。"""

    class Status(models.IntegerChoices):
        DRAFT = 0, "草稿"
        PUBLISHED = 1, "已发布"

    title = models.CharField(max_length=200, verbose_name="题目")
    content = models.TextField(verbose_name="正文")
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="所属栏目",
    )
    status = models.IntegerField(
        choices=Status.choices, default=Status.DRAFT, db_index=True, verbose_name="状态"
    )
    views = models.PositiveIntegerField(default=0, verbose_name="浏览量")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_items",
        verbose_name="作者",
    )
    # 发表时间仅在发布时才有值，草稿时为空，支持定时发布
    publish_time = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="发表时间"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="items", verbose_name="标签")

    class Meta:
        verbose_name = "文章"
        verbose_name_plural = "文章"
        ordering = ["-publish_time", "-id"]
        # 反向关系（如 Favorite.item、category.items）使用过滤了软删除的默认管理器
        base_manager_name = "objects"

    def __str__(self):
        return self.title

    def is_visible(self):
        """前台是否可见：已发布且已到发表时间。"""
        return (
            self.status == self.Status.PUBLISHED
            and self.publish_time is not None
            and self.publish_time <= timezone.now()
        )


class Favorite(models.Model):
    """收藏：用户与文章的多对多关系（通过独立表）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="收藏者",
    )
    item = models.ForeignKey(
        Item,
        on_delete=models.CASCADE,
        related_name="favorites",
        verbose_name="被收藏文章",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="收藏时间")

    class Meta:
        verbose_name = "收藏"
        verbose_name_plural = "收藏"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "item"], name="unique_user_item_favorite"),
        ]

    def __str__(self):
        return f"{self.user} 收藏《{self.item.title}》"


class OperationLog(models.Model):
    """操作日志：记录栏目/文章的关键操作（创建、更新、删除）。"""

    class Action(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "更新"
        DELETE = "delete", "删除"

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="operation_logs",
        verbose_name="操作人",
    )
    action = models.CharField(max_length=10, choices=Action.choices, verbose_name="操作类型")
    target_type = models.CharField(max_length=20, verbose_name="对象类型")
    target_id = models.PositiveIntegerField(verbose_name="对象ID")
    description = models.TextField(blank=True, verbose_name="操作说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="操作时间")

    class Meta:
        verbose_name = "操作日志"
        verbose_name_plural = "操作日志"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_display()} {self.target_type}#{self.target_id} by {self.operator}"

    @classmethod
    def log(cls, user, action, obj, description=None):
        """记录一条操作日志。"""
        return cls.objects.create(
            operator=user,
            action=action,
            target_type=obj._meta.model_name,
            target_id=obj.id,
            description=description or str(obj),
        )
