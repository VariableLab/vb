import os
import json
import time
import random
import threading
import requests
import streamlit as st
import base64
from openai import OpenAI

# ================= 配置区 =================
BASE_URL = "https://apihub.agnes-ai.com/v1"

# 预设的多版本视频美学提示词库
STYLES = {
    "Vox 风格 (复古拼贴/信息图表)": {
        "role": "Vox 风格 YouTube 纪录片导演和视觉设计专家",
        "aesthetic": "充分运用复古剪纸拼贴 (paper collage)、半调网点 (halftone)、极简数据图表 (minimalist infographics)。配色应具有高级感（如芥末黄、藏青色、复古褪色感）。",
        "image_prefix": "Vox documentary style, paper collage, vintage aesthetic"
    },
    "墨必斯风格 (Moebius 科幻漫画)": {
        "role": "墨必斯 (Moebius) 风格的科幻动画视觉导演",
        "aesthetic": "法国漫画大师墨必斯风格，清晰明快的线条 (ligne claire)、细腻的点阵阴影 (stippling)、超现实的科幻或奇幻构图、平涂的鲜艳复古色彩。",
        "image_prefix": "Jean Giraud Moebius style, comic book art, ligne claire, surreal sci-fi landscape, vibrant flat colors, intricate stippling"
    },
    "Kurzgesagt 风格 (扁平矢量/可爱科普)": {
        "role": "Kurzgesagt 风格科普动画导演",
        "aesthetic": "极简扁平化矢量插画 (flat vector art)，色彩极其鲜艳明亮 (vibrant neon colors)，科学/宇宙主题，可能包含可爱的卡通形象。",
        "image_prefix": "Kurzgesagt in a nutshell style, flat vector illustration, colorful vibrant neon palette, minimalist educational animation frame"
    },
    "国家地理风格 (Cinematic 电影感)": {
        "role": "国家地理风格的电影级纪录片导演",
        "aesthetic": "极其逼真的摄影质感，电影级打光 (cinematic lighting)，景深效果 (depth of field)，宏大的构图，展现自然或人文的壮丽景观。",
        "image_prefix": "National Geographic style, cinematic photography, hyper-realistic, dramatic lighting, 8k resolution, highly detailed"
    }
}

# ================= 核心逻辑 =================

# 模型名称（集中配置，便于后续升级）
TEXT_MODEL = "agnes-3.0-flash"       # 文本/分镜脚本（原 agnes-2.5-flash）
IMAGE_MODEL = "agnes-image-2.5-flash"  # 首尾帧生图（原 agnes-image-2.1-flash）
VIDEO_MODEL = "agnes-video-2.5-flash"  # 首尾帧关键帧视频
VIDEO_MODEL_FALLBACK = "agnes-video-v2.0"  # 队列满时的降级池（老模型，容量更宽松）

# 视频提交串行锁 + 指数退避重试（修复 video_queue_full）
# 免费档视频 RPM 极低（约 1 次/分钟），并发提交会撑爆队列；
# 这里把「提交视频任务」全局串行化，并对队列满/限流做指数退避重试。
_VIDEO_SUBMIT_LOCK = threading.Lock()


def _is_retryable(exc_text):
    """判断是否为可重试的队列/限流错误。"""
    markers = ("video_queue_full", "queue is full", "rate limit", "429",
               "503", "502", "service busy", "try again later", "too many")
    return any(m in exc_text.lower() for m in markers)


def _retry_on_submit(fn, *args, max_attempts=6, base_wait=2, cap=60, on_wait=None, **kwargs):
    """对「提交」类请求做指数退避重试；遇到队列满/限流则等待后重试。

    base_wait/cap: 控制退避节奏（视频共享队列高峰期需要更长的等待预算）。
    on_wait: 可选回调 on_wait(attempt, waited_seconds)，用于 UI 实时展示等待进度。
    """
    last_err = None
    waited = 0
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _is_retryable(str(e)) and attempt < max_attempts - 1:
                delay = min(cap, base_wait * (2 ** min(attempt, 8)))
                delay += random.uniform(0, 1.0)
                waited += delay
                if on_wait:
                    on_wait(attempt + 1, waited)
                time.sleep(delay)
                continue
            raise
    raise last_err


def analyze_article_to_script(article_text, api_key, style_key):
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    style_info = STYLES[style_key]
    
    system_prompt = f"""你是一位顶级的 {style_info['role']}。
你的任务是深度理解用户提供的文章，精准提炼核心逻辑，并严格按时间轴顺序，将其转化为高度定制化的视频分镜脚本。

【核心要求：分镜密度与顺序】
1. 严格按原文顺序：必须逐段落、逐句推进，绝不能跳跃、颠倒或省略文章的任何实质性内容。
2. 高频的分镜节奏：信息密度极高。请预估文案朗读时间（按200字/分钟），大约每 10-15 秒（即每 30-50 个字）就必须切换或演进一个新分镜。例如，6分钟的内容必须生成 25 到 40 幕分镜。绝不能用少量分镜糊弄长文。

【核心要求：精准的视觉转译】
1. 深度内容映射：画面绝不能是宽泛的装饰！必须是对当前这句话的“视觉解释”。
   - 提到数据/趋势 -> 必须设计折线图、柱状图或数字动画。
   - 提到地理/路线 -> 必须设计地图、航线或发光锚点。
   - 提到抽象概念 -> 必须使用具体的物理隐喻（如多米诺骨牌代表连锁反应）。
2. 视觉美学：{style_info['aesthetic']}
3. 镜头连贯性：相邻两幕若描述同一事物的演变，上一幕的“尾帧”与下一幕的“首帧”必须在逻辑或构图上高度连贯。

【输出格式】
请严格返回如下 JSON 格式数组，确保可以直接被程序解析（只返回JSON，禁止其他文字）：
[
  {{
    "scene": 1,
    "narration": "当前幕对应的旁白文案（严格摘自原文，约30-50字）",
    "image_prompt_first_frame": "{style_info['image_prefix']}, (此处将你理解的中文画面用纯英文详细描述起手画面，包括具体物体、场景细节、色彩搭配等)",
    "image_prompt_last_frame": "{style_info['image_prefix']}, (此处用纯英文详细描述镜头运动结束后的画面，必须与首帧连贯演变)",
    "video_prompt": "(此处用纯英文描述具体且富有逻辑的镜头运动，例如：Camera slowly zooms in to reveal details)"
  }}
]

【特别注意】
1. 虽然输入的文章是中文，但为了保证生图引擎的最佳效果，`image_prompt_first_frame`、`image_prompt_last_frame` 和 `video_prompt` 必须**全部使用纯英文**生成！
2. 请直接输出纯英文描述，**不要**在英文描述中带有括号或占位符，**不要**加上 `--ar 16:9` 这样的画幅参数。"""
    
    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请处理以下文章：\n{article_text}"}
        ]
    )
    content = response.choices[0].message.content
    content = content.replace("```json", "").replace("```", "").strip()
    
    start_idx = content.find('[')
    end_idx = content.rfind(']') + 1
    if start_idx != -1 and end_idx != 0:
        content = content[start_idx:end_idx]
        
    return json.loads(content)

def generate_scene_image(image_prompt, api_key):
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    def _do():
        resp = client.images.generate(
            model=IMAGE_MODEL,
            prompt=image_prompt,
            n=1,
            size="1920x1080"
        )
        return resp.data[0].url

    # 生图 RPM 也偏低（1K≈20/分钟，2K≈10/分钟），1920x1080 属 2K 档，
    # 加指数退避避免限流。
    return _retry_on_submit(_do, max_attempts=5)

def _post_video(payload, api_key):
    """单次提交视频任务（不重试、不加锁），识别 HTTP 200 里的错误体。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    response = requests.post(f"{BASE_URL}/videos", headers=headers, json=payload, timeout=60)
    if response.status_code == 200:
        body = response.json()
        # 服务端有时用 HTTP 200 返回错误体（如 {"code":"video_queue_full",...}），
        # 必须识别错误码并抛出，否则会被误判为提交成功。
        if isinstance(body, dict) and body.get("code") and body.get("code") not in ("success", "ok"):
            raise Exception(f"视频生成失败: {response.text}")
        return body
    raise Exception(f"视频生成失败: {response.text}")


def _build_keyframe_payload(first_url, video_prompt, seconds, last_url):
    """主路径：2.5-flash 首尾帧 keyframe（保留镜头连贯）。"""
    return {
        "model": VIDEO_MODEL,
        "prompt": video_prompt,
        "mode": "keyframe",
        "size": "720P",
        "seconds": str(seconds),
        "first_frame": first_url,
        **({"last_frame": last_url} if last_url else {}),
    }


def _v2_frames(seconds):
    """把秒数换算成 v2.0 的合法帧数（8n+1 规则，81~441）。"""
    target = int(seconds) * 24
    n = int(round((target - 1) / 8))
    return max(81, min(441, 8 * n + 1))


# 稳定版（v2.0）音效控制：v2.0 默认自带一条混合音轨（BGM+音效混在一起，后期无法拆分），
# 只能在生成时用「正向要求 + 负向排除」把背景音乐压掉、保留环境/拟音音效。
_V2_SFX_POSITIVE = (" (Audio: keep only natural diegetic sound effects such as ambient room tone and "
                    "subtle Foley; no background music, no melody, no soundtrack.)")
_V2_SFX_NEGATIVE = "background music, BGM, melody, orchestral music, soundtrack, singing, beat drop, rhythm track"


def _build_v2_payload(first_url, video_prompt, seconds, last_url, sfx_only=False):
    """v2.0 payload（稳定版池）。

    若提供了首/尾帧，优先用 keyframes 关键帧模式保留镜头衔接；
    否则退回纯文生视频。始终落在容量更宽松的老模型池，保证出片。
    sfx_only=True 时，追加音效约束：去掉背景音乐，仅保留环境/拟音音效。
    """
    images = [u for u in (first_url, last_url) if u]
    prompt = video_prompt
    if sfx_only:
        prompt = f"{prompt}{_V2_SFX_POSITIVE}"
    payload = {
        "model": VIDEO_MODEL_FALLBACK,
        "prompt": prompt,
        "height": 640,
        "width": 1138,
        "num_frames": _v2_frames(seconds),
        "frame_rate": 24,
    }
    if sfx_only:
        payload["negative_prompt"] = _V2_SFX_NEGATIVE
    if images:
        payload["image"] = images[0]          # 首帧动画化
        if len(images) > 1:
            payload["extra_body"] = {"image": images, "mode": "keyframes"}
    return payload


def animate_scene_video(first_image_url, video_prompt, seconds, api_key,
                        last_image_url=None, on_wait=None, prefer="2.5", sfx_only=False):
    """提交视频任务。

    prefer="2.5"（高品质）：主路径 2.5-flash keyframe（保留首尾帧连贯）+
        指数退避 + 全局串行锁；队列满/限流耗尽后自动降级到 v2.0（标记 _fallback_used）。
    prefer="v2"（稳定版）：直接走 v2.0 池（能带首尾帧就带），轻重试，不做跨池降级。
    sfx_only=True：v2.0 路径去背景音乐、仅保留环境/拟音音效（prompt + negative_prompt 控制）。
    """
    with _VIDEO_SUBMIT_LOCK:
        if prefer == "v2":
            def _stable():
                return _post_video(_build_v2_payload(first_image_url, video_prompt, seconds, last_image_url, sfx_only=sfx_only), api_key)
            result = _retry_on_submit(_stable, max_attempts=5, base_wait=10, cap=60, on_wait=on_wait)
            result.setdefault("_model", VIDEO_MODEL_FALLBACK)
            if sfx_only:
                result["_sfx_only"] = True
            return result

        def _primary():
            return _post_video(_build_keyframe_payload(first_image_url, video_prompt, seconds, last_image_url), api_key)

        try:
            result = _retry_on_submit(
                _primary,
                max_attempts=10, base_wait=5, cap=90, on_wait=on_wait,
            )
            result.setdefault("_model", VIDEO_MODEL)
            return result
        except Exception as e:
            # 非队列/限流类错误（如参数/鉴权问题）不降级，直接抛出。
            if not _is_retryable(str(e)):
                raise
            # 兜底：v2.0 池（能带首尾帧就带，否则文生）
            if on_wait:
                on_wait(-1, 0)
            def _fallback():
                return _post_video(_build_v2_payload(first_image_url, video_prompt, seconds, last_image_url, sfx_only=sfx_only), api_key)
            result = _retry_on_submit(_fallback, max_attempts=4, base_wait=15, cap=60, on_wait=None)
            result.setdefault("_model", VIDEO_MODEL_FALLBACK)
            result["_fallback_used"] = True
            result["_fallback_reason"] = str(e)
            return result


def check_video_status(video_id, api_key, model=VIDEO_MODEL):
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    # 2.5-flash 必须带 model_name 查询；v2.0 用 video_id 即可
    if model == VIDEO_MODEL:
        url = f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}&model_name={model}"
    else:
        url = f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"查询失败: {response.text}")

# ================= Web 界面 (Streamlit) =================
st.set_page_config(page_title="AI 自动化视频 SaaS 平台", layout="wide")

# SaaS 侧边栏配置
st.sidebar.title("⚙️ SaaS 配置面板")
st.sidebar.markdown("由于服务运行在 SaaS 模式下，请在此输入您的私有 API Key：")
user_api_key = st.sidebar.text_input("专属 API Key", type="password", placeholder="sk-...")

st.sidebar.markdown("---")
st.sidebar.subheader("🎨 视觉风格选择")
st.sidebar.markdown("切换风格后，AI 将自动套用该美学流派的色彩、画风和提示词公式。")
selected_style = st.sidebar.selectbox("请选择视频的美学风格：", list(STYLES.keys()))

st.sidebar.markdown("---")
st.sidebar.subheader("🎞️ 视频模型选择")
video_model_choice = st.sidebar.radio(
    "视频模型池：",
    options=["高品质（2.5-flash）", "稳定版（v2.0）"],
    index=0,
)
video_model_prefer = "v2" if video_model_choice.startswith("稳定版") else "2.5"

st.sidebar.markdown("---")
st.sidebar.subheader("🔊 音频模式")
audio_mode = st.sidebar.radio(
    "背景音乐：",
    options=["保留背景音乐", "仅保留音效（去背景音乐）"],
    index=0,
    help="稳定版（v2.0）默认会生成一条混合音轨（BGM+音效）。选「仅保留音效」时，"
         "生成会要求去掉背景音乐、只保留环境/拟音音效（通过正向+负向提示词控制）。"
         "该选项对稳定版（v2.0）最明显。",
)
video_sfx_only = audio_mode.startswith("仅保留音效")

st.title(f"🎬 AI 视频生成引擎 ({selected_style.split(' ')[0]})")
st.markdown("通过文本、图像、视频大模型的组合，将您的文章全自动转化为高密度、专业级的视频片段。")

if not user_api_key:
    st.warning("⚠️ 请先在左侧侧边栏填入您的 API Key 才能继续使用！")
    st.stop()

# --- 状态管理 ---
if "scenes" not in st.session_state:
    st.session_state.scenes = []

# --- 第一步：文章输入与分镜生成 ---
st.header("1. 输入文章")
article = st.text_area("粘贴您的长文章或文案：", height=150, value="最近几年，全球咖啡豆价格飙升。主要原因有两个：一是巴西等主要产区遭遇极端干旱天气，导致阿拉比卡咖啡豆减产；二是全球海运物流成本上升。")

if st.button("🌟 智能拆解并生成分镜"):
    with st.spinner(f"🧠 正在以 {selected_style.split(' ')[0]} 风格分析文案逻辑..."):
        try:
            st.session_state.scenes = analyze_article_to_script(article, user_api_key, selected_style)
            st.success("分镜生成成功！")
        except Exception as e:
            st.error(f"生成失败：{e}")

# --- 第二步 & 第三步：展示分镜并提供生成功能 ---
if st.session_state.scenes:
    st.header("2. 分镜设计与视效生成")
    st.markdown("下面是 AI 为你设计的视频分镜脚本。您可以手动微调提示词或上传自定义图片，然后一键生成。")
    
    for i, scene in enumerate(st.session_state.scenes):
        with st.expander(f"🎬 第 {scene.get('scene', i+1)} 幕：{scene.get('narration', '')[:15]}...", expanded=True):
            st.markdown(f"**🗣️ 旁白 (Narration)：** {scene.get('narration', '')}")
            
            # 允许用户微调提示词
            edited_img_prompt_first = st.text_area(f"🎨 首帧提示词 (第 {i+1} 幕)", value=scene.get('image_prompt_first_frame', ''), key=f"img_first_input_{i}")
            edited_img_prompt_last = st.text_area(f"🎨 尾帧提示词 (第 {i+1} 幕)", value=scene.get('image_prompt_last_frame', ''), key=f"img_last_input_{i}")
            edited_vid_prompt = st.text_area(f"🎥 镜头运动提示词 (第 {i+1} 幕)", value=scene.get('video_prompt', ''), key=f"vid_input_{i}")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("### 🖼️ 首帧设置")
                img_first_key = f"img_url_first_{i}"
                
                # 继承上一幕尾帧
                if i > 0:
                    prev_last_key = f"img_url_last_{i-1}"
                    if prev_last_key in st.session_state:
                        if st.button("🔗 继承上一幕尾帧", key=f"btn_inherit_{i}"):
                            st.session_state[img_first_key] = st.session_state[prev_last_key]
                
                # 用户上传首帧
                uploaded_first = st.file_uploader(f"上传首帧 (可选)", type=["png", "jpg", "jpeg"], key=f"up_first_{i}")
                if uploaded_first is not None:
                    base64_str = base64.b64encode(uploaded_first.getvalue()).decode("utf-8")
                    st.session_state[img_first_key] = f"data:{uploaded_first.type};base64,{base64_str}"
                
                if st.button(f"AI 生成第 {i+1} 幕首帧", key=f"btn_img_first_{i}"):
                    with st.spinner("正在绘制首帧..."):
                        try:
                            url = generate_scene_image(edited_img_prompt_first, user_api_key)
                            st.session_state[img_first_key] = url
                        except Exception as e:
                            st.error(f"生图失败: {e}")
                
                if img_first_key in st.session_state:
                    st.image(st.session_state[img_first_key], caption="首帧底图", use_container_width=True)

            with col2:
                st.markdown("### 🖼️ 尾帧设置")
                img_last_key = f"img_url_last_{i}"
                
                # 用户上传尾帧
                uploaded_last = st.file_uploader(f"上传尾帧 (可选)", type=["png", "jpg", "jpeg"], key=f"up_last_{i}")
                if uploaded_last is not None:
                    base64_str = base64.b64encode(uploaded_last.getvalue()).decode("utf-8")
                    st.session_state[img_last_key] = f"data:{uploaded_last.type};base64,{base64_str}"
                
                if st.button(f"AI 生成第 {i+1} 幕尾帧 (可选)", key=f"btn_img_last_{i}"):
                    with st.spinner("正在绘制尾帧..."):
                        try:
                            url = generate_scene_image(edited_img_prompt_last, user_api_key)
                            st.session_state[img_last_key] = url
                        except Exception as e:
                            st.error(f"生图失败: {e}")
                
                if img_last_key in st.session_state:
                    st.image(st.session_state[img_last_key], caption="尾帧底图", use_container_width=True)
            
            with col3:
                st.markdown("### 🎥 视频生成")
                video_seconds = st.slider(f"时长 (秒) - 第 {i+1} 幕", min_value=4, max_value=12, value=5, key=f"sec_slider_{i}")
                
                vid_key = f"vid_data_{i}"
                btn_label = "🎥 生成视频（稳定版 v2.0）" if video_model_prefer == "v2" else "🎥 生成视频（高品质 2.5）"
                if st.button(btn_label, key=f"btn_vid_{i}"):
                    has_first = img_first_key in st.session_state
                    if not has_first and video_model_prefer == "2.5":
                        st.warning("⚠️ 高品质池需要首帧底图，请先生成/上传首帧；或切到「稳定版（v2.0）」池直接文生。")
                    else:
                        wait_msg = st.empty()
                        def _on_wait(attempt, total_waited):
                            if attempt == -1:
                                wait_msg.warning("🛟 高品质池（2.5-flash）持续繁忙，正在自动降级到 v2.0 稳定池重试…")
                            else:
                                eta_min = int(total_waited // 60)
                                eta_rem = int(total_waited % 60)
                                wait_msg.info(
                                    f"⏳ 服务端视频队列繁忙，自动排队中 "
                                    f"(第 {attempt} 次重试，已等待 {eta_min}分{eta_rem}秒，"
                                    f"最多再等约 12 分钟)…"
                                )
                        with st.spinner("正在提交视频生成任务（如遇队列繁忙会自动排队重试）..."):
                            try:
                                first_url = st.session_state.get(img_first_key)
                                last_url = st.session_state.get(img_last_key)
                                vid_result = animate_scene_video(
                                    first_url, edited_vid_prompt, video_seconds,
                                    user_api_key, last_url, on_wait=_on_wait,
                                    prefer=video_model_prefer,
                                    sfx_only=video_sfx_only,
                                )
                                st.session_state[vid_key] = vid_result
                                if vid_result.get("_fallback_used"):
                                    st.info(
                                        "🛟 高品质池（2.5-flash）繁忙，本幕已**自动降级到 v2.0 稳定池**"
                                        "（能带首尾帧就带，否则文生，保证出片）。队列恢复后可重跑本幕拿回最佳效果。"
                                    )
                            except Exception as e:
                                err_text = str(e)
                                if "video_queue_full" in err_text.lower() or "queue is full" in err_text.lower():
                                    st.warning(
                                        "🚦 服务端视频共享队列当前非常繁忙，已等待超时仍未入队成功。\n\n"
                                        "建议：① 过几分钟再点一次；② 侧边栏切到「稳定版（v2.0）」池；"
                                        "③ 错开高峰时段（UTC 08:00–14:00 即北京时间 16:00–22:00 最忙）；"
                                        "④ 减少同屏分镜数（先只出 1–2 幕视频）。"
                                    )
                                else:
                                    st.error(f"视频生成失败：{err_text}")
                
                if vid_key in st.session_state:
                    task_data = st.session_state[vid_key]
                    video_id = task_data.get("video_id") or task_data.get("id")
                    
                    if video_id:
                        model_tag = task_data.get("_model", "")
                        st.success(
                            f"✅ 任务下发成功! 视频ID: `{video_id}`"
                            + (f"（本幕实际使用 {model_tag}）" if model_tag else "")
                        )
                        
                        if st.button(f"🔄 检查视频是否生成完毕", key=f"btn_check_{i}"):
                            with st.spinner("查询中..."):
                                try:
                                    used_model = task_data.get("_model") or VIDEO_MODEL
                                    status_data = check_video_status(video_id, user_api_key, model=used_model)
                                    # 保留降级/模型标记，避免被轮询结果覆盖
                                    status_data.setdefault("_model", task_data.get("_model", VIDEO_MODEL))
                                    if task_data.get("_fallback_used"):
                                        status_data["_fallback_used"] = True
                                    st.session_state[vid_key] = status_data
                                except Exception as e:
                                    st.error(str(e))
                                    
                        current_status = st.session_state[vid_key].get("status", "unknown")
                        if current_status == "completed":
                            st.success("🎉 视频生成完成！")
                            video_url = st.session_state[vid_key].get("video_url") or st.session_state[vid_key].get("url")
                            if video_url:
                                st.video(video_url)
                                st.markdown(f"[点击下载视频]({video_url})")
                            else:
                                st.json(st.session_state[vid_key])
                        elif current_status in ["queued", "processing", "running", "starting"]:
                            st.info(f"⏳ 视频正在生成中...当前状态: {current_status}")
                            st.json(st.session_state[vid_key])
                        else:
                            st.error(f"❌ 视频生成失败，状态: {current_status}")
                            st.json(st.session_state[vid_key])
                    else:
                        st.json(task_data)

    # --- 最终视频合成 ---
    st.markdown("---")
    st.header("3. 最终视频合成 (一键拼接)")
    st.markdown("将上述所有生成的视频片段，加上转场效果，无缝拼接成一段完整的长视频。")
    
    col_s1, col_s2 = st.columns(2)
    transition_type = col_s1.selectbox("转场效果", ["交叉淡化 (Crossfade - 推荐)", "硬切 (Cut - 极速)"])
    if st.button("🌟 一键拼接为长视频", type="primary"):
        import tempfile
        from stitcher import stitch_videos_crossfade, stitch_videos_concat
        
        valid_clips = []
        for i in range(len(st.session_state.scenes)):
            vid_key = f"vid_data_{i}"
            if vid_key in st.session_state:
                status = st.session_state[vid_key].get("status")
                url = st.session_state[vid_key].get("video_url") or st.session_state[vid_key].get("url")
                if status == "completed" and url:
                    valid_clips.append(url)
                    
        if len(valid_clips) < 2:
            st.warning("⚠️ 至少需要 2 个已生成的视频片段才能进行拼接！请先生成每一幕的视频。")
        else:
            with st.spinner(f"正在下载 {len(valid_clips)} 个视频片段并处理转场 (依赖 FFmpeg)..."):
                try:
                    temp_dir = tempfile.mkdtemp()
                    local_files = []
                    for idx, url in enumerate(valid_clips):
                        r = requests.get(url, timeout=60)
                        path = os.path.join(temp_dir, f"clip_{idx}.mp4")
                        with open(path, "wb") as f:
                            f.write(r.content)
                        local_files.append(path)
                    
                    output_path = os.path.join(temp_dir, "final_stitched_video.mp4")
                    
                    if "Crossfade" in transition_type:
                        stitch_videos_crossfade(local_files, output_path, transition_duration=0.5)
                    else:
                        stitch_videos_concat(local_files, output_path)
                        
                    st.success("🎉 合成完毕！您可以直接预览或下载。")
                    st.video(output_path)
                    
                    with open(output_path, "rb") as f:
                        video_bytes = f.read()
                    st.download_button(label="💾 下载最终成片", data=video_bytes, file_name="final_video.mp4", mime="video/mp4")
                    
                except Exception as e:
                    st.error(f"合成失败，请检查是否已正确安装 FFmpeg。详细报错：{e}")
