"""AstrBot Denpa Echo 插件主入口。

接入 Minimax 官方 TTS API 的全功能语音合成插件：
- 同步/异步/流式语音合成
- 语音克隆与音色管理
- LLM 合成前润色
- 拦截/追加双发送模式
- Signal 声场控制台（亚克力/Mica 材质，动/静态取色）
"""
import os
import time
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Plain, Record
from astrbot.api.web import error_response, file_response, json_response, request

from .core.audio_utils import AudioConverter
from .core.polisher import TextPolisher
from .core.sender import MessageSender
from .core.tts_engine import TTSEngine
from .minimax.client import MinimaxAPIError, MinimaxClient
from .minimax.voice_clone import VoiceCloneService
from .minimax.voice_manage import VoiceManageService

PLUGIN_NAME = "astrbot_plugin_denpa_echo"


class Main(Star):
    """Denpa Echo 插件主类。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self._api_ok: bool = False
        self._today_count: int = 0
        self._today_date: str = time.strftime("%Y-%m-%d")
        self._stats: list[dict] = []  # 最近合成记录

        # 插件数据目录
        self.plugin_data_dir = os.path.join(
            str(Path.home()), "AstrBot", "data", PLUGIN_NAME
        )
        # 优先使用 AstrBot 标准数据目录
        try:
            from astrbot.core.utils.astrbot_path import (
                get_astrbot_data_path,
            )
            self.plugin_data_dir = os.path.join(
                get_astrbot_data_path(), "plugin_data", PLUGIN_NAME
            )
        except Exception:
            pass
        os.makedirs(self.plugin_data_dir, exist_ok=True)

        # 初始化 Minimax 客户端
        adv = config.get("advanced", {}) or {}
        self.client = MinimaxClient(
            api_key=config.get("api_key", ""),
            group_id=config.get("group_id", ""),
            region=config.get("api_region", "china"),
            timeout=int(adv.get("request_timeout", 60)),
            retry_times=int(adv.get("retry_times", 2)),
            retry_backoff=float(adv.get("retry_backoff", 1.5)),
        )

        # 初始化各模块
        self.polisher = TextPolisher(context, config.get("polish", {}) or {})
        self.converter = AudioConverter()
        self.tts_engine = TTSEngine(
            client=self.client,
            polisher=self.polisher,
            converter=self.converter,
            config=config,
            plugin_data_dir=self.plugin_data_dir,
            context=context,
        )
        self.sender = MessageSender(
            tts_engine=self.tts_engine,
            context=context,
            config=config,
        )

        # 注册 Plugin Page 后端 API
        self._register_web_apis(context)

        logger.info(
            f"[Denpa Echo] 插件已加载，模式={self.sender.mode}, "
            f"模型={config.get('tts', {}).get('model', 'speech-02-hd')}"
        )

    def _register_web_apis(self, context: Context) -> None:
        """注册 Plugin Page 后端 API。"""
        apis = [
            ("stats", self._api_stats, ["GET"], "运行状态"),
            ("voices", self._api_voices, ["GET"], "音色列表"),
            ("voices/static", self._api_voices_static, ["GET"], "内置音色列表"),
            ("voice/get", self._api_voice_get, ["GET"], "按 ID 查询音色"),
            ("voice/set_default", self._api_voice_set_default, ["POST"], "设置默认音色"),
            ("preview", self._api_preview, ["POST"], "试听合成"),
            ("clone/upload", self._api_clone_upload, ["POST"], "上传克隆音频"),
            ("clone/start", self._api_clone_start, ["POST"], "执行语音克隆"),
            ("debug/synth", self._api_debug_synth, ["POST"], "调试合成"),
            ("config/ui", self._api_config_ui, ["GET"], "UI 配置"),
            ("config/full", self._api_config_full, ["GET"], "完整配置"),
            ("config/save", self._api_config_save, ["POST"], "保存配置"),
            ("audio", self._api_audio, ["GET"], "音频文件"),
            ("bg/upload", self._api_bg_upload, ["POST"], "上传背景图"),
            ("bg", self._api_bg, ["GET"], "背景图文件"),
            ("bg/remove", self._api_bg_remove, ["POST"], "移除背景图"),
            ("cache/clear", self._api_cache_clear, ["POST"], "清空缓存"),
            ("cache/size", self._api_cache_size, ["GET"], "缓存大小"),
            ("logs", self._api_logs, ["GET"], "运行日志"),
        ]
        for route, handler, methods, desc in apis:
            context.register_web_api(
                f"/{PLUGIN_NAME}/{route}", handler, methods, desc
            )

    async def initialize(self) -> None:
        """异步初始化：检测 API 连通性。"""
        if not self.config.get("api_key"):
            logger.warning("[Denpa Echo] 未配置 API Key，插件功能不可用")
            self._api_ok = False
            return
        try:
            vm = VoiceManageService(self.client)
            await vm.list_voices("system")
            self._api_ok = True
            logger.info("[Denpa Echo] API 连通性检测通过")
        except Exception as e:
            self._api_ok = False
            logger.error(f"[Denpa Echo] API 连通性检测失败: {e}")

    # ===== 事件钩子 =====

    @filter.on_decorating_result()
    async def on_message_decorating(self, event: AstrMessageEvent):
        """发送前拦截，根据模式处理。"""
        if not self._api_ok:
            return
        if not self.sender.should_process(event):
            return

        # 检查是否包含可合成文本（避免对纯图片/表情消息触发）
        result = event.get_result()
        chain = result.chain if result and result.chain else []
        has_text = any(
            isinstance(c, Plain) and c.text.strip() for c in chain
        )
        if not has_text:
            return

        if self.sender.mode == "intercept":
            await self.sender.handle_intercept(event)
        elif self.sender.mode == "append":
            await self.sender.handle_append(event)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        """LLM 回复生成后回调（可选记录）。"""
        if (self.config.get("advanced", {}) or {}).get("log_level") == "DEBUG":
            text = getattr(resp, "completion_text", str(resp))
            logger.debug(
                f"[Denpa Echo] LLM 回复: {text[:100]}..."
            )

    # ===== 指令 =====

    @filter.command("tts", alias={"语音合成", "t"})
    async def cmd_tts(self, event: AstrMessageEvent, text: str):
        """手动触发 TTS 合成。用法：/tts <文本>"""
        if not self._api_ok:
            yield event.plain_result("Minimax TTS 未就绪，请检查 API Key 配置")
            return
        if not text.strip():
            yield event.plain_result("用法：/tts <要合成的文本>")
            return
        try:
            tts_params = self.tts_engine.build_tts_params()
            umo = event.unified_msg_origin
            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo=umo,
                use_async=False,
            )
            self._record_stat(text, meta)
            yield event.chain_result([Record(file=wav_path, url=wav_path)])
        except MinimaxAPIError as e:
            yield event.plain_result(f"语音合成失败: {e}")
        except Exception as e:
            yield event.plain_result(f"语音合成异常: {e}")

    @filter.command("tts_voices", alias={"音色列表", "tts音色"})
    async def cmd_voices(self, event: AstrMessageEvent):
        """列出可用音色。"""
        if not self._api_ok:
            # 降级：返回内置列表
            from .minimax.models import ALL_SYSTEM_VOICES
            lines = ["API 未就绪，内置系统音色（部分）："]
            for name, vid in ALL_SYSTEM_VOICES[:15]:
                lines.append(f"  · {name} → {vid}")
            yield event.plain_result("\n".join(lines))
            return
        try:
            vm = VoiceManageService(self.client)
            data = await vm.list_voices("all")
            voices = []
            for key in ("system_voice", "voice_cloning", "voice_generation"):
                for v in data.get(key, []) or []:
                    voices.append(v)
            lines = ["可用音色："]
            for v in voices[:20]:
                name = v.get("voice_name") or v.get("voice_id", "?")
                vid = v.get("voice_id", "?")
                lines.append(f"  · {name} → {vid}")
            if len(voices) > 20:
                lines.append(f"  ...共 {len(voices)} 个，完整列表见 WebUI 面板")
            yield event.plain_result("\n".join(lines))
        except Exception as e:
            yield event.plain_result(f"获取音色失败: {e}")

    @filter.command("tts_panel", alias={"tts面板", "tts控制台"})
    async def cmd_panel(self, event: AstrMessageEvent):
        """提示打开 WebUI 面板。"""
        yield event.plain_result(
            "请在 AstrBot WebUI → 插件管理 → Minimax TTS → "
            "打开「控制台」页面进行音色试听、语音克隆等高级操作。"
        )

    @filter.command("tts_mode", alias={"tts模式"})
    async def cmd_mode(self, event: AstrMessageEvent, mode: str = ""):
        """查看或切换发送模式。用法：/tts_mode [intercept|append|disabled]"""
        if not mode:
            yield event.plain_result(
                f"当前模式：{self.sender.mode}\n"
                "可选：intercept（拦截）/ append（追加）/ disabled（关闭）\n"
                "用法：/tts_mode intercept"
            )
            return
        mode = mode.strip().lower()
        if mode not in ("intercept", "append", "disabled"):
            yield event.plain_result(
                "无效模式，可选：intercept / append / disabled"
            )
            return
        self.config.setdefault("send_mode", {})["mode"] = mode
        try:
            self.config.save_config()
        except Exception:
            pass
        mode_name = {
            "intercept": "拦截模式（与文本一起发）",
            "append": "追加模式（先发文本后追加语音）",
            "disabled": "已关闭",
        }[mode]
        yield event.plain_result(f"已切换为：{mode_name}")

    @filter.command("tts_clear_cache", alias={"清空tts缓存"})
    async def cmd_clear_cache(self, event: AstrMessageEvent):
        """清空音频缓存。"""
        count = self.tts_engine.clear_cache()
        yield event.plain_result(f"已清空缓存，删除 {count} 个文件")

    # ===== Plugin Page 后端 API =====

    async def _api_stats(self):
        """运行状态。"""
        self._reset_daily_count_if_needed()
        return json_response({
            "api_ok": self._api_ok,
            "today_count": self._today_count,
            "cache_size_mb": round(self.tts_engine.cache_size_mb(), 2),
            "mode": self.sender.mode,
            "model": (self.config.get("tts", {}) or {}).get("model", ""),
            "voice_id": (self.config.get("tts", {}) or {}).get("voice_id", ""),
            "ffmpeg_available": self.converter.available,
        })

    async def _api_voices(self):
        """从 Minimax API 获取音色列表（合并系统/克隆/生成音色）。"""
        try:
            vm = VoiceManageService(self.client)
            data = await vm.list_voices("all")
            voices = []
            for key, label in (
                ("system_voice", "system"),
                ("voice_cloning", "voice_cloning"),
                ("voice_generation", "voice_generation"),
            ):
                for v in data.get(key, []) or []:
                    item = dict(v)
                    item.setdefault("type", label)
                    # 统一 name 字段（官方返回 voice_name）
                    item.setdefault(
                        "name", v.get("voice_name") or v.get("voice_id")
                    )
                    voices.append(item)
            return json_response({"voices": voices, "raw": data})
        except Exception as e:
            return error_response(f"获取音色失败: {e}", status_code=500)

    async def _api_voices_static(self):
        """返回内置系统音色列表（不调用 API）。"""
        from .minimax.models import ALL_SYSTEM_VOICES
        voices = [
            {"name": name, "voice_id": vid, "type": "system"}
            for name, vid in ALL_SYSTEM_VOICES
        ]
        return json_response({"voices": voices})

    async def _api_preview(self):
        """试听合成。"""
        payload = await request.json(default={})
        text = payload.get("text", "你好，这是该音色的试听样本。")
        voice_id = payload.get("voice_id", "")
        speed = payload.get("speed", 1.0)
        emotion = payload.get("emotion", "")
        if not voice_id:
            voice_id = (self.config.get("tts", {}) or {}).get(
                "voice_id", "female-shaonv"
            )
        try:
            tts_params = self.tts_engine.build_tts_params()
            tts_params["voice_id"] = voice_id
            tts_params["use_timbre_weights"] = False
            tts_params["speed"] = float(speed)
            if emotion:
                tts_params["emotion"] = emotion
            else:
                tts_params.pop("emotion", None)

            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo="preview",
                use_async=False,
                skip_polish=True,
                skip_emotion_classify=True,
            )
            self._record_stat(text, meta)
            return json_response({
                "audio_path": wav_path,
                "elapsed_ms": meta.get("elapsed_ms", 0),
                "usage_chars": meta.get("usage_chars", len(text)),
            })
        except Exception as e:
            return error_response(f"试听合成失败: {e}", status_code=500)

    async def _api_clone_upload(self):
        """上传克隆源音频，返回 file_id。"""
        from astrbot.api.web import PluginUploadFile
        files = await request.files()
        upload = files.get("file")
        if not isinstance(upload, PluginUploadFile):
            return error_response("缺少上传文件（字段名应为 file）", status_code=400)

        # 保存到插件数据目录
        upload_dir = os.path.join(self.plugin_data_dir, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, os.path.basename(upload.filename))
        await upload.save(save_path)

        try:
            vc = VoiceCloneService(self.client)
            file_id = await vc.upload_clone_audio(save_path)
            return json_response({
                "file_id": file_id,
                "filename": upload.filename,
                "saved_path": save_path,
            })
        except Exception as e:
            return error_response(f"上传到 Minimax 失败: {e}", status_code=500)

    async def _api_clone_start(self):
        """执行语音克隆。"""
        payload = await request.json(default={})
        source_file_id = payload.get("source_file_id")
        voice_id = payload.get("voice_id", "")
        model = payload.get("model", "speech-02-hd")
        preview_text = payload.get("preview_text", "你好，这是克隆音色的试听样本。")
        prompt_audio_file_id = payload.get("prompt_audio_file_id")
        prompt_text = payload.get("prompt_text")

        if not source_file_id:
            return error_response("缺少 source_file_id", status_code=400)
        if not voice_id:
            return error_response("缺少 voice_id", status_code=400)

        try:
            vc = VoiceCloneService(self.client)
            result = await vc.clone(
                source_file_id=int(source_file_id),
                voice_id=voice_id,
                model=model,
                prompt_audio_file_id=int(prompt_audio_file_id)
                if prompt_audio_file_id
                else None,
                prompt_text=prompt_text,
                preview_text=preview_text,
            )
            # 下载试听音频到本地（voice_clone 响应里的 demo_audio 是试听 URL）
            demo_audio_url = result.get("demo_audio")
            audio_url = None
            if demo_audio_url:
                preview_path = os.path.join(
                    self.plugin_data_dir, "clone_preview",
                    f"{voice_id}_{int(time.time())}.mp3",
                )
                try:
                    await vc.get_clone_preview_audio(result, preview_path)
                    audio_url = preview_path
                except Exception as e:
                    logger.warning(f"[Denpa Echo] 下载克隆试听失败: {e}")
            return json_response({
                "success": True,
                "voice_id": voice_id,
                "demo_audio": demo_audio_url,
                "audio_path": audio_url,
                "raw": result,
            })
        except Exception as e:
            return error_response(f"克隆失败: {e}", status_code=500)

    async def _api_voice_get(self):
        """按音色 ID 查询音色信息（支持已有克隆音色 ID 直接加载）。"""
        voice_id = request.query.get("voice_id", "")
        if not voice_id:
            return error_response("缺少 voice_id 参数", status_code=400)
        try:
            vm = VoiceManageService(self.client)
            data = await vm.list_voices("all")
            found = None
            for key, label in (
                ("voice_cloning", "voice_cloning"),
                ("voice_generation", "voice_generation"),
                ("system_voice", "system"),
            ):
                lst = data.get(key, []) or []
                for v in lst:
                    if v.get("voice_id") == voice_id:
                        found = dict(v)
                        found.setdefault("type", label)
                        found.setdefault(
                            "name", v.get("voice_name") or v.get("voice_id")
                        )
                        break
                if found:
                    break
            if found:
                return json_response({
                    "found": True,
                    "voice": found,
                    "voice_id": voice_id,
                })
            # 未在列表中找到，仍允许使用（跨账号或已不在列表的克隆音色）
            return json_response({
                "found": False,
                "voice_id": voice_id,
                "note": "未在音色列表中找到该 ID，若 Minimax 端仍有效即可试听/设为默认",
            })
        except Exception as e:
            return error_response(f"查询音色失败: {e}", status_code=500)

    async def _api_voice_set_default(self):
        """将指定音色 ID 设为默认音色（写入 tts.voice_id）。"""
        payload = await request.json(default={})
        voice_id = payload.get("voice_id", "")
        if not voice_id:
            return error_response("缺少 voice_id", status_code=400)
        try:
            self.config.setdefault("tts", {})["voice_id"] = voice_id
            self.config.save_config()
            return json_response({"saved": True, "voice_id": voice_id})
        except Exception as e:
            return error_response(f"保存失败: {e}", status_code=500)

    async def _api_debug_synth(self):
        """调试合成（带完整参数）。"""
        payload = await request.json(default={})
        text = payload.get("text", "你好")
        if not text.strip():
            return error_response("text 不能为空", status_code=400)
        # 允许覆盖任意 TTS 参数
        tts_params = self.tts_engine.build_tts_params()
        for k in (
            "voice_id", "speed", "vol", "pitch", "emotion",
            "language_boost", "model", "format", "sample_rate",
        ):
            if k in payload and payload[k] != "":
                tts_params[k] = payload[k]
        if "voice_id" not in tts_params or not tts_params["voice_id"]:
            tts_params["voice_id"] = "female-shaonv"
        tts_params["use_timbre_weights"] = False
        try:
            t0 = time.time()
            wav_path, meta = await self.tts_engine.synthesize_to_wav(
                text=text,
                tts_params=tts_params,
                umo="debug",
                use_async=False,
                skip_polish=True,
                skip_emotion_classify=True,
            )
            elapsed = int((time.time() - t0) * 1000)
            self._record_stat(text, meta)
            return json_response({
                "audio_path": wav_path,
                "elapsed_ms": elapsed,
                "usage_chars": meta.get("usage_chars", len(text)),
                "meta": meta,
            })
        except Exception as e:
            return error_response(f"调试合成失败: {e}", status_code=500)

    async def _api_config_ui(self):
        """返回 UI 配置（供面板读取取色等）。"""
        ui = self.config.get("ui", {}) or {}
        return json_response(ui)

    async def _api_config_full(self):
        """返回完整配置（敏感字段脱敏）。"""
        cfg = dict(self.config)
        if cfg.get("api_key"):
            cfg["api_key"] = cfg["api_key"][:4] + "***" + cfg["api_key"][-4:]
        return json_response(cfg)

    async def _api_config_save(self):
        """保存配置（仅允许保存非敏感 UI / 发送模式相关字段）。"""
        payload = await request.json(default={})
        ui_new = payload.get("ui")
        if ui_new:
            self.config["ui"] = ui_new
        sm_new = payload.get("send_mode")
        if sm_new:
            self.config["send_mode"] = sm_new
        try:
            self.config.save_config()
            return json_response({"saved": True})
        except Exception as e:
            return error_response(f"保存失败: {e}", status_code=500)

    async def _api_audio(self):
        """返回音频文件（供面板 <audio> 播放）。"""
        path = request.query.get("path", "")
        if not path:
            return error_response("缺少 path 参数", status_code=400)
        # 安全校验：路径必须在缓存目录 / 插件数据目录 / 系统临时目录下
        # (未配置 cache_dir 时合成临时 wav 落在系统临时目录, 必须放行否则 403 空响应 → 音频时长 0)
        import tempfile
        allowed_prefixes = [
            os.path.abspath(self.tts_engine.cache_dir) if self.tts_engine.cache_dir else "",
            os.path.abspath(self.plugin_data_dir),
            os.path.abspath(tempfile.gettempdir()),
        ]
        allowed_prefixes = [os.path.normcase(p) for p in allowed_prefixes if p]
        abs_path = os.path.abspath(path)
        # normcase: Windows 下统一小写 + 正斜杠→反斜杠, 避免大小写不一致导致 403
        if not any(os.path.normcase(abs_path).startswith(p) for p in allowed_prefixes):
            return error_response("路径不在允许范围内", status_code=403)
        if not os.path.isfile(abs_path):
            return error_response("文件不存在", status_code=404)
        return file_response(abs_path, content_type="audio/wav")

    async def _api_bg_upload(self):
        """上传 UI 背景图，以 base64 data URI 内联存储，不再依赖服务端文件路径。"""
        import base64
        from astrbot.api.web import PluginUploadFile
        files = await request.files()
        upload = files.get("file")
        if not isinstance(upload, PluginUploadFile):
            return error_response("缺少上传文件（字段名应为 file）", status_code=400)

        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return error_response("仅支持 jpg/png/webp/gif 图片", status_code=400)

        # 取文件字节：优先用 body 属性，否则临时落盘读取后删除
        body = getattr(upload, "body", None)
        if body is None:
            bg_dir = os.path.join(self.plugin_data_dir, "backgrounds")
            os.makedirs(bg_dir, exist_ok=True)
            tmp_path = os.path.join(bg_dir, f"tmp_{int(time.time())}{ext}")
            await upload.save(tmp_path)
            try:
                with open(tmp_path, "rb") as f:
                    body = f.read()
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        if len(body) > 20 * 1024 * 1024:
            return error_response("图片不能超过 20MB", status_code=400)

        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        data_uri = f"data:{mime};base64," + base64.b64encode(body).decode("ascii")

        self.config.setdefault("ui", {})["background_image"] = data_uri
        try:
            self.config.save_config()
        except Exception as e:
            logger.warning(f"[Denpa Echo] 保存背景图配置失败: {e}")
        logger.info(f"[Denpa Echo] 背景图已上传（base64 内联，{len(body)} 字节）")
        return json_response({
            "saved": True,
            "data": data_uri,
            "filename": upload.filename,
        })

    async def _api_bg(self):
        """返回当前背景图文件。"""
        ui = self.config.get("ui", {}) or {}
        path = ui.get("background_image", "")
        if not path:
            return error_response("未设置背景图", status_code=404)
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(os.path.abspath(self.plugin_data_dir)):
            return error_response("路径不在允许范围内", status_code=403)
        if not os.path.isfile(abs_path):
            return error_response("背景图文件不存在", status_code=404)
        ext = os.path.splitext(abs_path)[1].lower()
        ct = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "application/octet-stream")
        return file_response(abs_path, content_type=ct)

    async def _api_bg_remove(self):
        """移除背景图配置。"""
        self.config.setdefault("ui", {})["background_image"] = ""
        try:
            self.config.save_config()
        except Exception:
            pass
        return json_response({"removed": True})

    async def _api_cache_clear(self):
        """清空缓存。"""
        count = self.tts_engine.clear_cache()
        return json_response({"deleted": count})

    async def _api_cache_size(self):
        """缓存大小。"""
        return json_response({
            "size_mb": round(self.tts_engine.cache_size_mb(), 2),
        })

    async def _api_logs(self):
        """返回最近合成记录。"""
        limit = request.query.get("limit", 50, type=int)
        return json_response({"logs": self._stats[-limit:]})

    # ===== 辅助方法 =====

    def _reset_daily_count_if_needed(self) -> None:
        """跨天重置计数。"""
        today = time.strftime("%Y-%m-%d")
        if today != self._today_date:
            self._today_date = today
            self._today_count = 0

    def _record_stat(self, text: str, meta: dict) -> None:
        """记录一次合成。"""
        self._reset_daily_count_if_needed()
        self._today_count += 1
        self._stats.append({
            "time": time.strftime("%H:%M:%S"),
            "chars": len(text),
            "mode": meta.get("mode", ""),
            "elapsed_ms": meta.get("elapsed_ms", 0),
            "cached": meta.get("cached", False),
            "preview": text[:50],
        })
        # 仅保留最近 200 条
        if len(self._stats) > 200:
            self._stats = self._stats[-200:]

    async def terminate(self):
        """插件卸载时清理资源。"""
        await self.client.close()
        logger.info("[Denpa Echo] 插件已卸载")
