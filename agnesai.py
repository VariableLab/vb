import os
import json
import time
import requests
import streamlit as st
from openai import OpenAI

# ================= 配置区 =================
API_KEY = "sk-1849NzbTlGk3StGVjlNju4EPefyp5DGRYmiCzXgIE1uladyT"
BASE_URL = "https://apihub.agnes-ai.com/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ================= 核心逻辑 =================
def analyze_article_to_vox_script(article_text):
    system_prompt = """你是一个专业的 Vox 风格 YouTube 视频制作人。
我将给你一段文章内容，请根据文章内容的长度和逻辑层次，将其转化为合适数量的连续视频分镜（通常为 3 到 8 幕，如果文章长可以更多）。
Vox 风格特点：复古拼贴、信息图表、地图、强烈的色彩对比、平滑的过渡。

请严格返回如下 JSON 格式数组：
[
  {
    "scene": 1,
    "narration": "旁白文案",
    "image_prompt": "Vox documentary style, paper collage, muted yellow and navy blue, [具体画面描述] --ar 16:9",
    "video_prompt": "具体的镜头运动，例如：Camera slowly zooms in."
  }
]"""
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

def generate_scene_image(image_prompt):
    response = client.images.generate(
        model="agnes-image-2.1-flash",
        prompt=image_prompt,
        n=1,
        size="1920x1080"
    )
    return response.data[0].url

def animate_scene_video(image_url, video_prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "agnes-video-2.5-flash",
        "prompt": video_prompt,
        "mode": "keyframe",
        "size": "720P",
        "first_frame": image_url
    }
    response = requests.post(f"{BASE_URL}/videos", headers=headers, json=data)
    if response.status_code == 200:
        # 这里假设返回格式包含 url，或者 id。为了演示，直接返回整个 dict
        return response.json()
    else:
        raise Exception(f"视频生成失败: {response.text}")

def check_video_status(video_id):
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    url = f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}&model_name=agnes-video-2.5-flash"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"查询失败: {response.text}")

# ================= Web 界面 (Streamlit) =================
st.set_page_config(page_title="Vox 风格视频生成器", layout="wide")

st.title("🎬 Vox 风格 AI 视频一键生成平台")
st.markdown("通过 Agnes AI 强大的文本、图像、视频模型，自动将文章转化为带分镜的 Vox 风格纪录片。")

# --- 状态管理 ---
if "scenes" not in st.session_state:
    st.session_state.scenes = []

# --- 第一步：文章输入与分镜生成 ---
st.header("1. 输入文章")
article = st.text_area("粘贴你的长文章或文案：", height=150, value="最近几年，全球咖啡豆价格飙升。主要原因有两个：一是巴西等主要产区遭遇极端干旱天气，导致阿拉比卡咖啡豆减产；二是全球海运物流成本上升。")

if st.button("🌟 智能拆解并生成分镜 (Text Model)"):
    with st.spinner("🧠 正在使用 agnes-2.5-flash 分析文案逻辑..."):
        try:
            st.session_state.scenes = analyze_article_to_vox_script(article)
            st.success("分镜生成成功！")
        except Exception as e:
            st.error(f"生成失败：{e}")

# --- 第二步 & 第三步：展示分镜并提供生成功能 ---
if st.session_state.scenes:
    st.header("2. 分镜设计与视效生成")
    st.markdown("下面是 AI 为你设计的视频分镜脚本。你可以一键生成图像和视频。")
    
    for i, scene in enumerate(st.session_state.scenes):
        with st.expander(f"🎬 第 {scene['scene']} 幕：{scene.get('narration', '')[:15]}...", expanded=True):
            st.markdown(f"**🗣️ 旁白 (Narration)：** {scene.get('narration', '')}")
            st.markdown(f"**🎨 图像提示词 (Image Prompt)：** {scene.get('image_prompt', '')}")
            st.markdown(f"**🎥 镜头运动 (Video Prompt)：** {scene.get('video_prompt', '')}")
            
            # 使用列来并排显示生成的图和视频
            col1, col2 = st.columns(2)
            
            with col1:
                # 记录该场景生成的图片 URL
                img_key = f"img_url_{i}"
                if st.button(f"生成第 {i+1} 幕图像 (Image Model)", key=f"btn_img_{i}"):
                    with st.spinner("正在绘制关键帧..."):
                        try:
                            url = generate_scene_image(scene['image_prompt'])
                            st.session_state[img_key] = url
                        except Exception as e:
                            st.error(f"生图失败: {e}")
                
                if img_key in st.session_state:
                    st.image(st.session_state[img_key], caption="生成的底图", use_container_width=True)
            
            with col2:
                # 记录视频状态
                vid_key = f"vid_data_{i}"
                if st.button(f"将第 {i+1} 幕转为视频 (Video Model)", key=f"btn_vid_{i}"):
                    if img_key not in st.session_state:
                        st.warning("⚠️ 请先生成图像底图！")
                    else:
                        with st.spinner("正在提交视频生成任务..."):
                            try:
                                vid_result = animate_scene_video(st.session_state[img_key], scene['video_prompt'])
                                st.session_state[vid_key] = vid_result
                            except Exception as e:
                                st.error(str(e))
                
                if vid_key in st.session_state:
                    task_data = st.session_state[vid_key]
                    video_id = task_data.get("video_id") or task_data.get("id")
                    
                    if video_id:
                        st.success(f"✅ 任务下发成功! 视频ID: `{video_id}`")
                        
                        # 检查视频状态的逻辑
                        if st.button(f"🔄 检查视频是否生成完毕", key=f"btn_check_{i}"):
                            with st.spinner("查询中..."):
                                try:
                                    status_data = check_video_status(video_id)
                                    st.session_state[vid_key] = status_data # 更新状态数据
                                except Exception as e:
                                    st.error(str(e))
                                    
                        # 显示当前状态
                        current_status = st.session_state[vid_key].get("status", "unknown")
                        if current_status == "completed":
                            st.success("🎉 视频生成完成！")
                            video_url = st.session_state[vid_key].get("video_url") or st.session_state[vid_key].get("url")
                            if video_url:
                                st.video(video_url)
                                st.markdown(f"[点击下载视频]({video_url})")
                            else:
                                st.json(st.session_state[vid_key]) # 防御性显示，万一键名不叫video_url
                        elif current_status in ["queued", "processing", "running", "starting"]:
                            st.info(f"⏳ 视频正在生成中...当前状态: {current_status}")
                            st.json(st.session_state[vid_key])
                        else:
                            st.error(f"❌ 视频生成失败，状态: {current_status}")
                            st.json(st.session_state[vid_key])
                    else:
                        st.json(task_data)

