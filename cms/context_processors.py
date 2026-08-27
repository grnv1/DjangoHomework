"""模板上下文处理器：分页相关全局变量。"""

from django.conf import settings


def pagination(request):
    """向模板注入前端可选每页条数白名单。"""
    return {"page_size_choices": getattr(settings, "PAGE_SIZE_CHOICES", ())}
