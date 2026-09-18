import os
import json
import time
import requests
from openai import OpenAI

# ================= 配置区 =================
API_KEY = "sk-1849NzbTlGk3StGVjlNju4EPefyp5DGRYmiCzXgIE1uladyT"
BASE_URL = "https://apihub.agnes-ai.com/v1"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ================= 1. 文本理解与分镜设计 =================
def analyze_article_to_vox_script(article_text):
    print("🎬 正在理解文章，设计 Vox 风格分镜...")
    
    system_prompt = """你是一位顶级的 Vox 风格 YouTube 纪录片导演和视觉设计专家。
你的任务是深度理解用户提供的文章，精准提炼核心逻辑，并严格按时间轴顺序，将其转化为高度定制化的视频分镜脚本。

【核心要求：分镜密度与顺序】
1. 严格按原文顺序：必须逐段落、逐句推进，绝不能跳跃、颠倒或省略文章的任何实质性内容。
2. 高频的分镜节奏：Vox 风格的信息密度极高。请预估文案朗读时间（按200字/分钟），大约每 10-15 秒（即每 30-50 个字）就必须切换或演进一个新分镜。例如，6分钟的内容必须生成 25 到 40 幕分镜。绝不能用少量分镜糊弄长文。

【核心要求：精准的视觉转译】
1. 深度内容映射：画面绝不能是宽泛的装饰！必须是对当前这句话的“视觉解释”。
   - 提到数据/趋势 -> 必须设计折线图、柱状图或数字动画。
   - 提到地理/路线 -> 必须设计复古地图、航线或发光锚点。
   - 提到历史/背景 -> 必须设计旧报纸剪报、老照片拼贴。
   - 提到抽象概念 -> 必须使用具体的物理隐喻（如多米诺骨牌代表连锁反应）。
2. Vox 视觉美学：充分运用复古剪纸拼贴 (paper collage)、半调网点 (halftone)、极简数据图表 (minimalist infographics)。配色应具有高级感（如芥末黄、藏青色、复古褪色感）。
3. 镜头连贯性：相邻两幕若描述同一事物的演变，上一幕的“尾帧”与下一幕的“首帧”必须在逻辑或构图上高度连贯。

【输出格式】
请严格返回如下 JSON 格式数组，确保可以直接被程序解析（只返回JSON，禁止其他文字）：
[
  {
    "scene": 1,
    "narration": "当前幕对应的旁白文案（严格摘自原文，约30-50字）",
    "image_prompt_first_frame": "Vox documentary style, paper collage, vintage aesthetic, [极其具体的起手画面，例如：A vintage map of South America with a glowing pin on Brazil] --ar 16:9",
    "image_prompt_last_frame": "Vox documentary style, paper collage, vintage aesthetic, [镜头运动结束后的画面，例如：Camera zooms into Brazil, showing a paper-cut illustration of dried, cracked earth] --ar 16:9",
    "video_prompt": "[具体且富有逻辑的镜头运动。例如：Camera slowly zooms in from the continent view to a close-up of the cracked earth.]"
  }
]"""

    response = client.chat.completions.create(
        model="agnes-2.5-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请处理以下文章：\n{article_text}"}
        ]
    )
    
    try:
        content = response.choices[0].message.content
        content = content.replace("```json", "").replace("```", "").strip()
        
        # 为了防止模型输出非纯JSON，我们可以用简单的手段提取方括号内的内容
        start_idx = content.find('[')
        end_idx = content.rfind(']') + 1
        if start_idx != -1 and end_idx != 0:
            content = content[start_idx:end_idx]
            
        script_data = json.loads(content)
        return script_data
    except Exception as e:
        print(f"❌ 解析分镜 JSON 失败: {e}")
        print(f"模型原始返回:\n{response.choices[0].message.content}")
        return []

# ================= 2. 图像生成 =================
def generate_scene_image(image_prompt, scene_num):
    print(f"🖼️ 正在生成第 {scene_num} 幕的关键帧图像...")
    response = client.images.generate(
        model="agnes-image-2.1-flash",
        prompt=image_prompt,
        n=1,
        size="1920x1080"
    )
    return response.data[0].url

# ================= 3. 视频生成 =================
def animate_scene_video(first_image_url, video_prompt, scene_num, last_image_url=None):
    print(f"🎥 正在将第 {scene_num} 幕图像转化为动态视频...")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "agnes-video-2.5-flash",
        "prompt": video_prompt,
        "mode": "keyframe",
        "size": "720P",
        "first_frame": first_image_url
    }
    if last_image_url:
        data["last_frame"] = last_image_url
        
    response = requests.post(f"{BASE_URL}/videos", headers=headers, json=data)
    if response.status_code == 200:
        return response.json() 
    else:
        print(f"❌ 第 {scene_num} 幕视频生成失败: {response.text}")
        return None

# ================= 主执行流程 =================
def main():
    # 这里我们输入一篇短文章作为测试
    article = "最近几年，全球咖啡豆价格飙升。主要原因有两个：一是巴西等主要产区遭遇极端干旱天气，导致阿拉比卡咖啡豆减产；二是全球海运物流成本上升。这使得你每天早上的那杯拿铁越来越贵。"
    
    print("========================================")
    print("🚀 开始 Vox 风格视频自动化生成流")
    print("========================================")
    
    # 1. 生成分镜
    scenes = analyze_article_to_vox_script(article)
    if not scenes:
        return
        
    print("\n✅ 分镜设计完成：")
    print(json.dumps(scenes, indent=2, ensure_ascii=False))
    
    results = []
    
    # 2 & 3. 遍历分镜，依次生图和生视频
    prev_last_url = None
    
    for scene in scenes:
        scene_num = scene.get("scene", 0)
        img_prompt_first = scene.get("image_prompt_first_frame", scene.get("image_prompt", ""))
        img_prompt_last = scene.get("image_prompt_last_frame", "")
        vid_prompt = scene.get("video_prompt", "")
        
        print(f"\n--- 处理第 {scene_num} 幕 ---")
        try:
            # 生图: 首帧 (如果上一幕有尾帧，则直接继承)
            if prev_last_url:
                print("🔗 继承上一幕的尾帧作为当前首帧...")
                img_url_first = prev_last_url
            else:
                print("生成首帧...")
                img_url_first = generate_scene_image(img_prompt_first, scene_num)
                print(f"✅ 首帧图像生成成功: {img_url_first}")
            
            # 生图: 尾帧
            img_url_last = None
            if img_prompt_last:
                print("生成尾帧...")
                img_url_last = generate_scene_image(img_prompt_last, scene_num)
                print(f"✅ 尾帧图像生成成功: {img_url_last}")
            
            # 保存当前尾帧，供下一幕使用
            prev_last_url = img_url_last
            
            # 生视频
            video_result = animate_scene_video(img_url_first, vid_prompt, scene_num, img_url_last)
            if video_result:
                print(f"✅ 视频生成任务下发成功: {video_result}")
            
            results.append({
                "scene": scene_num,
                "narration": scene.get("narration", ""),
                "image_url_first": img_url_first,
                "image_url_last": img_url_last,
                "video_info": video_result
            })
            
            time.sleep(2) # 缓冲时间
        except Exception as e:
            print(f"❌ 第 {scene_num} 幕处理发生错误: {e}")
            
    print("\n========================================")
    print("🎉 所有场景处理完毕！接下来请查看生成的素材。")
    print("========================================")

if __name__ == "__main__":
    main()
