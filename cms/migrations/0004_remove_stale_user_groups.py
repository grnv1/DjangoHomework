"""清理遗留的用户组及成员关系。

项目权限判断仅依赖 is_staff / is_superuser，不依赖用户组。
此迁移删除历史数据中的"内容管理员"组，以及更早遗留的"内容编辑"组，
其成员关系（auth_user_groups）与组权限（auth_group_permissions）随组级联删除。
"""

from django.db import migrations

STALE_GROUP_NAMES = ["内容管理员", "内容编辑"]


def remove_stale_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=STALE_GROUP_NAMES).delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0003_alter_item_category_alter_item_content_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_stale_groups, noop),
    ]
