"""
Agnes AI 三大模型封装库使用示例示例 (example.py)
"""
from agnes_client import AgnesAIClient

def main():
    # 自动从 'agnes ai.md' 读取 API Key 初始化客户端
    client = AgnesAIClient()

    print("==========================================")
    print("1. 测试文本模型 (agnes-2.5-flash) - 生成 Vox 风格分镜脚本")
    print("==========================================")
    script_prompt = "请为短视频【AI技术如何改变电影特效】生成一段 Vox 风格的开头台词及画面指示。"
    system_prompt = "你是一名专业 Vox 解说类视频导演，语言精炼，注重动效指导。"
    
    script_result = client.generate_text(
        prompt=script_prompt,
        system_prompt=system_prompt,
        temperature=0.7
    )
    print("生成结果：\n", script_result)

    print("\n==========================================")
    print("2. 测试图像模型 (agnes-image-2.1-flash) - 生成 Vox 拼贴图素材")
    print("==========================================")
    image_prompt = "Paper cutout illustration of a robot holding a vintage camera, retro grid graph paper texture background, Vox video aesthetic"
    
    try:
        images = client.generate_image(
            prompt=image_prompt,
            size="2K",
            ratio="16:9"
        )
        print("图片生成 URL：", images)
    except Exception as e:
        print("图片生成失败：", e)

    print("\n==========================================")
    print("3. 测试视频模型 (agnes-video-2.5-flash) - 文生视频/图生视频")
    print("==========================================")
    video_prompt = "未来科技城市在雨中闪烁霓虹灯，镜头缓慢向前推近，720P 电影质感"
    
    try:
        # wait_for_completion=True 会自动提交任务并轮询直到视频生成完成返回 URL
        video_result = client.generate_video(
            prompt=video_prompt,
            mode="text",
            seconds="5",
            aspect_ratio="16:9",
            wait_for_completion=True
        )
        print("视频生成结果：", video_result)
    except Exception as e:
        print("视频生成失败：", e)

if __name__ == "__main__":
    main()
