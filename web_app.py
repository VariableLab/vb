import os
import json
import time
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
        model="agnes-2.5-flash",
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
    response = client.images.generate(
        model="agnes-image-2.1-flash",
        prompt=image_prompt,
        n=1,
        size="1920x1080"
    )
    return response.data[0].url

def animate_scene_video(first_image_url, video_prompt, seconds, api_key, last_image_url=None):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "agnes-video-2.5-flash",
        "prompt": video_prompt,
        "mode": "keyframe",
        "size": "720P",
        "seconds": str(seconds),
        "first_frame": first_image_url
    }
    if last_image_url:
        data["last_frame"] = last_image_url
        
    response = requests.post(f"{BASE_URL}/videos", headers=headers, json=data)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"视频生成失败: {response.text}")

def check_video_status(video_id, api_key):
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    url = f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}&model_name=agnes-video-2.5-flash"
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
                if st.button(f"首尾帧生成视频", key=f"btn_vid_{i}"):
                    if img_first_key not in st.session_state:
                        st.warning("⚠️ 请至少先生成/上传首帧底图！")
                    else:
                        with st.spinner("正在提交视频生成任务..."):
                            try:
                                first_url = st.session_state[img_first_key]
                                last_url = st.session_state.get(img_last_key)
                                vid_result = animate_scene_video(first_url, edited_vid_prompt, video_seconds, user_api_key, last_url)
                                st.session_state[vid_key] = vid_result
                            except Exception as e:
                                st.error(str(e))
                
                if vid_key in st.session_state:
                    task_data = st.session_state[vid_key]
                    video_id = task_data.get("video_id") or task_data.get("id")
                    
                    if video_id:
                        st.success(f"✅ 任务下发成功! 视频ID: `{video_id}`")
                        
                        if st.button(f"🔄 检查视频是否生成完毕", key=f"btn_check_{i}"):
                            with st.spinner("查询中..."):
                                try:
                                    status_data = check_video_status(video_id, user_api_key)
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
