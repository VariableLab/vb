import os
import subprocess
import json
import uuid

def get_duration(file_path):
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        file_path,
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    data = json.loads(result.stdout)
    # 优先取 format.duration
    dur = float(data.get("format", {}).get("duration", 0))
    if not dur:
        for stream in data.get("streams", []):
            if "duration" in stream:
                dur = float(stream["duration"])
                break
    return dur

def stitch_videos_crossfade(clips, output_path, transition_duration=0.5):
    """
    使用 ffmpeg 的 xfade 滤镜拼接多个视频并加上 crossfade 效果。
    要求所有输入视频分辨率、帧率相同。
    """
    if len(clips) < 2:
        if len(clips) == 1:
            os.system(f'cp "{clips[0]}" "{output_path}"')
        return output_path

    n = len(clips)
    durations = [get_duration(c) for c in clips]
    
    input_args = []
    for c in clips:
        input_args.extend(["-i", c])

    video_filters = []
    audio_filters = []
    cumulative_offset = 0.0

    for i in range(n - 1):
        clip_dur = durations[i]
        offset = round(cumulative_offset + clip_dur - transition_duration, 3)
        offset = max(0, offset)
        cumulative_offset = offset

        if i == 0:
            v_in1 = "[0:v]"
            a_in1 = "[0:a]"
        else:
            v_in1 = f"[vfade{i-1}]"
            a_in1 = f"[afade{i-1}]"

        v_in2 = f"[{i+1}:v]"
        a_in2 = f"[{i+1}:a]"

        if i < n - 2:
            v_out = f"[vfade{i}]"
            a_out = f"[afade{i}]"
        else:
            v_out = "[vout]"
            a_out = "[aout]"

        # xfade for video
        video_filters.append(
            f"{v_in1}{v_in2}xfade=transition=fade:duration={transition_duration}:offset={offset}{v_out}"
        )
        # acrossfade for audio
        audio_filters.append(
            f"{a_in1}{a_in2}acrossfade=d={transition_duration}:c1=tri:c2=tri{a_out}"
        )

    filter_complex = ";".join(video_filters + audio_filters)
    
    cmd = [
        "ffmpeg", "-y"
    ] + input_args + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        output_path
    ]
    
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return output_path

def stitch_videos_concat(clips, output_path):
    """
    不使用转场，直接硬切拼接（速度极快，不会重编码）
    """
    list_file = f"concat_list_{uuid.uuid4().hex}.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            f.write(f"file '{os.path.abspath(c)}'\n")
            
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    os.remove(list_file)
    return output_path

