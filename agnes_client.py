import os
import re
import time
import requests
from typing import Optional, List, Dict, Any, Union, Generator

class AgnesAIClient:
    """
    Agnes AI 统一 SDK 客户端封装
    封装三款核心模型：
    1. Text Model: agnes-2.5-flash
    2. Image Model: agnes-image-2.5-flash (支持文生图、图生图与多图合成)
    3. Video Model: agnes-video-2.5-flash (支持文生视频、首尾帧与参考图视频)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://apihub.agnes-ai.com/v1",
        config_file_path: Optional[str] = None
    ):
        """
        初始化客户端。优先顺序：显式传入 api_key -> 环境变量 AGNES_API_KEY -> 从 agnes ai.md 读取
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("AGNES_API_KEY")

        # 如果没有传入 API Key，自动尝试解析配置文件
        if not self.api_key:
            target_path = config_file_path or os.path.join(os.path.dirname(__file__), "agnes ai.md")
            if os.path.exists(target_path):
                self.api_key = self._extract_key_from_file(target_path)

        if not self.api_key:
            raise ValueError("未查找到有效的 API Key！请传入 api_key 或设置 AGNES_API_KEY 环境变量，或确保 'agnes ai.md' 文件存在。")

        # 默认三款模型 ID
        self.text_model = "agnes-2.5-flash"
        self.image_model = "agnes-image-2.5-flash"
        self.video_model = "agnes-video-2.5-flash"

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _extract_key_from_file(self, file_path: str) -> Optional[str]:
        """从 agnes ai.md 提取 API Key"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r"sk-[A-Za-z0-9]+", content)
                if match:
                    return match.group(0)
        except Exception:
            pass
        return None

    # ==========================================
    # 1. 文本生成接口 (agnes-2.5-flash)
    # ==========================================
    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Union[str, Generator[str, None, None]]:
        """
        文本生成 (支持系统提示词、采样温度及流式输出)
        """
        model_name = model or self.text_model
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        response = requests.post(url, headers=self.headers, json=payload, stream=stream, timeout=120)
        response.raise_for_status()

        if stream:
            def stream_generator():
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data_content = line_str[6:]
                            if data_content.strip() == "[DONE]":
                                break
                            try:
                                import json
                                json_data = json.loads(data_content)
                                delta = json_data["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except Exception:
                                pass
            return stream_generator()
        else:
            result = response.json()
            return result["choices"][0]["message"]["content"]

    # ==========================================
    # 2. 图像生成与编辑接口 (agnes-image-2.1-flash)
    # ==========================================
    def generate_image(
        self,
        prompt: str,
        size: str = "2K",
        ratio: str = "16:9",
        image_urls: Optional[List[str]] = None,
        model: Optional[str] = None,
        n: int = 1,
        **kwargs
    ) -> List[str]:
        """
        图像生成与编辑接口 (支持文生图、图生图与多图合成)
        :param prompt: 图像提示词 / 编辑指令
        :param size: 尺寸档位 ("1K", "2K", "3K", "4K")
        :param ratio: 宽高比 ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9" 等)
        :param image_urls: 图生图或多图合成时的参考图片 URL 列表 (支持 HTTP URL 或 Base64 Data URI)
        :return: 生成的图片 URL 列表
        """
        model_name = model or self.image_model
        extra_body = {
            "ratio": ratio,
            "response_format": "url"
        }
        if image_urls and len(image_urls) > 0:
            extra_body["image"] = image_urls

        payload = {
            "model": model_name,
            "prompt": prompt,
            "size": size,
            "n": n,
            "extra_body": extra_body,
            **kwargs
        }

        url = f"{self.base_url}/images/generations"
        response = requests.post(url, headers=self.headers, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        urls = []
        if "data" in result:
            for item in result["data"]:
                if "url" in item and item["url"]:
                    urls.append(item["url"])
                elif "b64_json" in item and item["b64_json"]:
                    urls.append(item["b64_json"])
        return urls

    # ==========================================
    # 3. 视频生成接口 (agnes-video-2.5-flash)
    # ==========================================
    def create_video_task(
        self,
        prompt: str,
        mode: str = "text",
        seconds: str = "5",
        aspect_ratio: str = "16:9",
        size: str = "720P",
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        images: Optional[List[str]] = None,
        audios: Optional[List[str]] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建异步视频生成任务
        :param mode: "text" (文生视频), "keyframe" (首尾帧控制), "reference" (参考图控制)
        :param seconds: 视频时长字符串 (如 "4", "5", "8", "12")
        :param aspect_ratio: "16:9", "9:16", "1:1", "4:3", "21:9"
        """
        model_name = model or self.video_model
        payload = {
            "model": model_name,
            "prompt": prompt,
            "mode": mode,
            "seconds": str(seconds),
            "size": size,
            **kwargs
        }

        if mode == "keyframe":
            if first_frame:
                payload["first_frame"] = first_frame
            if last_frame:
                payload["last_frame"] = last_frame
        elif mode == "reference":
            if images:
                payload["images"] = images
            if audios:
                payload["audios"] = audios

        url = f"{self.base_url}/videos"
        response = requests.post(url, headers=self.headers, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    def query_video_status(self, video_id: str, model_name: Optional[str] = None) -> Dict[str, Any]:
        """
        查询视频任务状态
        """
        m_name = model_name or self.video_model
        query_url = f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}&model_name={m_name}"
        response = requests.get(query_url, headers=self.headers, timeout=30)
        response.raise_for_status()
        return response.json()

    def generate_video(
        self,
        prompt: str,
        mode: str = "text",
        seconds: str = "5",
        aspect_ratio: str = "16:9",
        first_frame: Optional[str] = None,
        last_frame: Optional[str] = None,
        images: Optional[List[str]] = None,
        wait_for_completion: bool = True,
        poll_interval: float = 2.0,
        timeout: int = 600,
        **kwargs
    ) -> Dict[str, Any]:
        """
        一键生成视频 (创建任务 + 自动轮询直到完成)
        :return: 包含任务状态和视频 URL 的字典
        """
        task_res = self.create_video_task(
            prompt=prompt,
            mode=mode,
            seconds=seconds,
            aspect_ratio=aspect_ratio,
            first_frame=first_frame,
            last_frame=last_frame,
            images=images,
            **kwargs
        )

        video_id = task_res.get("video_id") or task_res.get("id") or task_res.get("task_id")
        if not video_id:
            return {"status": "failed", "error": "创建视频任务未返回有效的 video_id", "raw": task_res}

        if not wait_for_completion:
            return {"status": "pending", "video_id": video_id, "raw": task_res}

        start_time = time.time()
        print(f"🎥 视频任务已提交 (ID: {video_id})，正在轮询生成状态...")

        while time.time() - start_time < timeout:
            try:
                status_res = self.query_video_status(video_id)
                status = str(status_res.get("status", "")).lower()
                
                if status in ["completed", "succeeded", "success"]:
                    metadata = status_res.get("metadata") or {}
                    result = status_res.get("result") or {}
                    video_url = (
                        metadata.get("url") or
                        status_res.get("video_url") or
                        status_res.get("url") or
                        result.get("video_url") or
                        result.get("url")
                    )
                    print(f"✅ 视频生成成功！")
                    return {
                        "status": "completed",
                        "video_id": video_id,
                        "video_url": video_url,
                        "raw": status_res
                    }
                elif status in ["failed", "error"]:
                    print(f"❌ 视频生成失败！")
                    return {
                        "status": "failed",
                        "video_id": video_id,
                        "error": status_res.get("error") or status_res.get("message") or "Unknown error",
                        "raw": status_res
                    }
                else:
                    print(f"⏳ 生成中... 状态: {status or 'processing'} (已等待 {int(time.time() - start_time)}s)")
            except Exception as e:
                print(f"⚠️ 查询警告: {e}")

            time.sleep(poll_interval)

        return {"status": "timeout", "video_id": video_id, "error": f"等待超时 ({timeout}秒)"}


_default_client = None

def get_client() -> AgnesAIClient:
    global _default_client
    if _default_client is None:
        _default_client = AgnesAIClient()
    return _default_client
