from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from video.models import Tag


@method_decorator(csrf_exempt, name="dispatch")
class TagListView(View):
    """获取所有标签列表"""

    def get(self, request):
        try:
            tags = Tag.objects.all()
            tags_data = [
                {
                    "id": tag.id,
                    "name": tag.name,
                    "color": tag.color,
                }
                for tag in tags
            ]
            return JsonResponse({"success": True, "tags": tags_data})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TagCreateView(View):
    """创建新标签"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            name = data.get("name", "").strip()
            color = data.get("color", "#3B82F6")

            if not name:
                return JsonResponse(
                    {"success": False, "error": "标签名称不能为空"}, status=400
                )

            if Tag.objects.filter(name=name).exists():
                return JsonResponse(
                    {"success": False, "error": "标签名称已存在"}, status=400
                )

            tag = Tag.objects.create(name=name, color=color)
            return JsonResponse(
                {
                    "success": True,
                    "tag": {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                    },
                }
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "error": "无效的JSON数据"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TagActionView(View):
    """标签编辑和删除操作"""

    def put(self, request, tag_id):
        """更新标签"""
        try:
            tag = Tag.objects.get(id=tag_id)
            data = json.loads(request.body)

            if "name" in data:
                new_name = data["name"].strip()
                if not new_name:
                    return JsonResponse(
                        {"success": False, "error": "标签名称不能为空"}, status=400
                    )
                if Tag.objects.filter(name=new_name).exclude(id=tag_id).exists():
                    return JsonResponse(
                        {"success": False, "error": "标签名称已存在"}, status=400
                    )
                tag.name = new_name

            if "color" in data:
                tag.color = data["color"]

            tag.save()
            return JsonResponse(
                {
                    "success": True,
                    "tag": {
                        "id": tag.id,
                        "name": tag.name,
                        "color": tag.color,
                    },
                }
            )
        except Tag.DoesNotExist:
            return JsonResponse({"success": False, "error": "标签不存在"}, status=404)
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "error": "无效的JSON数据"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    def delete(self, request, tag_id):
        """删除标签"""
        try:
            tag = Tag.objects.get(id=tag_id)
            tag_name = tag.name
            tag.delete()
            return JsonResponse(
                {"success": True, "message": f'标签 "{tag_name}" 已删除'}
            )
        except Tag.DoesNotExist:
            return JsonResponse({"success": False, "error": "标签不存在"}, status=404)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TagBatchDeleteView(View):
    """批量删除标签"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            tag_ids = data.get("tag_ids", [])

            if not tag_ids:
                return JsonResponse(
                    {"success": False, "error": "未提供标签ID"}, status=400
                )

            deleted_count = Tag.objects.filter(id__in=tag_ids).delete()[0]
            return JsonResponse(
                {"success": True, "message": f"已删除 {deleted_count} 个标签"}
            )
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "error": "无效的JSON数据"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


@method_decorator(csrf_exempt, name="dispatch")
class TagMergeView(View):
    """合并标签（将源标签合并到目标标签，然后删除源标签）"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            source_tag_id = data.get("source_tag_id")
            target_tag_id = data.get("target_tag_id")

            if not source_tag_id or not target_tag_id:
                return JsonResponse(
                    {"success": False, "error": "缺少源标签或目标标签ID"}, status=400
                )

            if source_tag_id == target_tag_id:
                return JsonResponse(
                    {"success": False, "error": "源标签和目标标签不能相同"}, status=400
                )

            source_tag = Tag.objects.get(id=source_tag_id)
            target_tag = Tag.objects.get(id=target_tag_id)

            # 从所有视频中替换标签
            from video.models import Video

            videos = Video.objects.filter(tags__isnull=False)
            updated_count = 0
            for video in videos:
                if video.tags and source_tag.name in video.tags:
                    # 移除源标签，添加目标标签（如果不存在）
                    new_tags = [t for t in video.tags if t != source_tag.name]
                    if target_tag.name not in new_tags:
                        new_tags.append(target_tag.name)
                    video.tags = new_tags
                    video.save(update_fields=["tags"])
                    updated_count += 1

            # 删除源标签
            source_tag.delete()

            return JsonResponse(
                {
                    "success": True,
                    "message": f'已将 {updated_count} 个视频的标签从 "{source_tag.name}" 替换为 "{target_tag.name}"',
                }
            )
        except Tag.DoesNotExist:
            return JsonResponse({"success": False, "error": "标签不存在"}, status=404)
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "error": "无效的JSON数据"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
