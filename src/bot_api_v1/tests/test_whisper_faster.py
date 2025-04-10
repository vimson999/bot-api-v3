import time
import os
import gc
import platform
import numpy as np # 确保导入 numpy
import torch # 用于设备检查和可能的 CUDA 操作

# --- 全局配置 ---
MODEL_SIZE = "base" # 模型大小 ("tiny", "base", "small", ...)
DEVICE_TYPE = "cpu"  # 设备 ("cpu" 或 "cuda")
# CPU 使用 float32 保证稳定性 (基于之前测试)
COMPUTE_TYPE_CONFIG = "float32"
AUDIO_FILE = "audio.mp3" # <--- 替换成你的音频文件路径

# 检查音频文件是否存在
if not os.path.exists(AUDIO_FILE):
    print(f"错误：音频文件 '{AUDIO_FILE}' 不存在。请修改脚本中的 AUDIO_FILE 变量。")
    exit()

# --- faster-whisper 测试函数 (修正打印错误) ---
def run_faster_whisper_test():
    print("\n" + "="*30)
    print("  Running faster-whisper Test")
    print("="*30)
    model = None # 初始化，便于清理
    segments = None
    info = None
    full_transcript_list = None
    full_text = "[未开始处理]" # 默认值
    language = ""
    duration = 0.0
    language_probability = None # 初始化概率

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("错误：'faster_whisper' 未安装。请运行 'pip install faster-whisper'")
        return

    print(f"配置: model='{MODEL_SIZE}', device='{DEVICE_TYPE}', compute_type='{COMPUTE_TYPE_CONFIG}'")
    print(f"音频文件: {AUDIO_FILE}")

    # --- 模型加载 ---
    load_start_time = time.time()
    try:
        cpu_threads_to_pass = 1 # 保守设置
        model_kwargs = {
            "device": DEVICE_TYPE,
            "compute_type": COMPUTE_TYPE_CONFIG,
        }
        if DEVICE_TYPE == "cpu":
            model_kwargs["cpu_threads"] = cpu_threads_to_pass
            print(f"       (使用 cpu_threads: {cpu_threads_to_pass})")
        model = WhisperModel(MODEL_SIZE, **model_kwargs)
    except Exception as e:
        print(f"加载 faster-whisper 模型时出错: {e}")
        return
    load_end_time = time.time()
    print(f"模型加载时间: {load_end_time - load_start_time:.2f} 秒")

    # --- 核心测试：获取完整文案的总时间 ---
    print("开始转录并获取完整文案...")
    overall_start_time = time.time()
    full_transcript_list = []
    try:
        # 1. 执行转录
        segments, info = model.transcribe(AUDIO_FILE, beam_size=5, language="zh", task="transcribe", word_timestamps=False)

        # 2. 迭代生成器一次，构建文本列表
        for segment in segments:
            print("[%.2fs -> %.2fs] %s" % (segment.start, segment.end, segment.text))
            full_transcript_list.append(segment.text.strip())

        # 3. 拼接成最终文本
        full_text = " ".join(full_transcript_list)

        # 记录语言和时长信息 (确保 info 存在)
        if info:
            language = info.language
            duration = info.duration
            if hasattr(info, 'language_probability'):
                 language_probability = info.language_probability

    except Exception as e:
        print(f"使用 faster-whisper 转录或处理时出错: {e}")
        full_text = "[转录或处理出错]"
        # 尝试获取 info (如果 transcribe 成功但迭代失败)
        if info is None and 'info' in locals(): info = locals()['info']
        if info:
            language = info.language; duration = info.duration
            if hasattr(info, 'language_probability'): language_probability = info.language_probability

    finally:
        overall_end_time = time.time()
        overall_time = overall_end_time - overall_start_time
        print(f"获取完整文案总耗时: {overall_time:.2f} 秒")

    # --- 在计时结束后打印信息 (修正格式化) ---
    prob_output = 'N/A' # 默认概率显示
    if language_probability is not None:
        if isinstance(language_probability, (float, int)): # 检查是否是数字
             try:
                 prob_output = f"{float(language_probability):.2f}" # 尝试格式化为浮点数
             except (ValueError, TypeError):
                 prob_output = str(language_probability) # 格式化失败则转为字符串
        else:
             prob_output = str(language_probability) # 不是数字直接转字符串

    if language:
        print(f"检测到语言: '{language}' (faster-whisper 报告概率: {prob_output})") # 使用修正后的概率字符串
    if duration > 0:
        print(f"转录音频时长 (由 faster-whisper 报告): {duration:.2f} 秒")
    if not language and not duration > 0:
         print("未能获取语言和时长信息。")

    print("\n--- 完整文案 (faster-whisper) ---")
    print(full_text)
    print("--- faster-whisper 测试结束 ---")

    # 清理
    del model, segments, info, full_transcript_list, full_text, language, language_probability
    if 'torch' in locals() and torch.cuda.is_available(): torch.cuda.empty_cache()
    gc.collect()


# --- openai-whisper 测试函数 (保持不变) ---
def run_openai_whisper_test():
    print("\n" + "="*30)
    print("  Running openai-whisper Test")
    print("="*30)
    model = None
    result = None
    full_text = "[未开始处理]"
    language = ""
    try:
        import whisper
        # import torch # 如果上面已经导入，这里不需要重复导入
    except ImportError:
        print("错误：'openai-whisper' 未安装。")
        return

    print(f"配置: model='{MODEL_SIZE}', device='{DEVICE_TYPE}'")
    print(f"音频文件: {AUDIO_FILE}")

    load_start_time = time.time()
    try:
        model = whisper.load_model(MODEL_SIZE, device=DEVICE_TYPE)
    except Exception as e:
        print(f"加载 openai-whisper 模型时出错: {e}")
        return
    load_end_time = time.time()
    print(f"模型加载时间: {load_end_time - load_start_time:.2f} 秒")

    print("开始转录并获取完整文案...")
    overall_start_time = time.time()
    try:
        result = model.transcribe(AUDIO_FILE, language="zh")
        full_text = result.get("text", "").strip()
        language = result.get("language", "")
    except Exception as e:
        print(f"使用 openai-whisper 转录时出错: {e}")
        full_text = "[转录出错]"
    finally:
        overall_end_time = time.time()
        overall_time = overall_end_time - overall_start_time
        print(f"获取完整文案总耗时: {overall_time:.2f} 秒")

    if language:
        print(f"检测到语言: {language}")
    else:
         if result and 'language' in result: print(f"检测到语言: {result['language']}")
         else: print("未能检测到语言。")

    print("\n--- 完整文案 (openai-whisper) ---")
    print(full_text)
    print("--- openai-whisper 测试结束 ---")

    del model, result, full_text, language
    if 'torch' in locals() and torch.cuda.is_available(): torch.cuda.empty_cache()
    gc.collect()


# --- 主程序入口 (保持不变) ---
if __name__ == "__main__":
    print("开始 Whisper 库比较测试 (目标：最快获取完整文案 - faster-whisper vs openai-whisper)...")
    print(f"当前 JST 时间: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"测试机器平台: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"CPU 核心数 (逻辑): {os.cpu_count()}")
    print(f"音频文件: {AUDIO_FILE}")

    print("\n提示：为获得稳定结果（尤其在 macOS），建议在运行此脚本前设置 OMP 环境变量，例如:")
    print("export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 CT2_NUM_THREADS=1\n")

    start_all = time.time()

    run_faster_whisper_test()
    gc.collect()

    run_openai_whisper_test()
    gc.collect()

    end_all = time.time()
    print("\n所有测试完成。")
    print(f"总测试耗时: {end_all - start_all:.2f} 秒")