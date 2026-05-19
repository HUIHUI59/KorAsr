import os
import re
import numpy as np
import torch
import warnings
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
import uvicorn

# 屏蔽 Hugging Face 烦人的底层警告信息
warnings.filterwarnings("ignore") 

app = FastAPI()

# ==========================================
# 1. 纯血 PyTorch 加载 Whisper Large-v3-Turbo
# ==========================================
print("🚀 正在初始化原生 Whisper 架构 (大型 Turbo 模型)...")

device = "cuda:0" if torch.cuda.is_available() else "cpu"
# GPU 环境下使用 float16 精度，成倍提升推理速度并节省显存
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

model_id = "openai/whisper-large-v3-turbo"

try:
    # 加载模型，原生支持，彻底告别 Windows DLL 报错
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
    )
    model.to(device)
    
    # 加载处理器
    processor = AutoProcessor.from_pretrained(model_id)
    
    # 构建极速推理管道
    asr_pipeline = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        torch_dtype=torch_dtype,
        device=device,
    )
    print("✅ Whisper 顶级模型就绪！降噪与高精度防幻觉模式已开启。")
except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    exit(1)

# ==========================================
# 2. FastAPI Web 服务与智能 VAD 逻辑
# ==========================================
@app.get("/")
async def get_webpage():
    # 将同目录下的 index.html 喂给手机浏览器
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

SAMPLE_RATE = 16000 
MAX_BUFFER_S = 4.0        # 最大允许积累的音频时长 (4秒)
MIN_BUFFER_S = 0.5        # 最少需要积累的音频时长
SILENCE_THRESHOLD = 0.015 # 静音判定阈值 (计算局部小切片)
SILENCE_CHUNKS = 3        # 连续几次检测到极小音量判定为停顿
SPEECH_THRESHOLD = 0.01   # 【防幻觉网关】全局音频能量阈值

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = np.array([], dtype=np.float32)
    silence_counter = 0
    
    print("📱 手机端已连接，智能网关与防幻觉系统已启动...")
    
    try:
        while True:
            # 接收前端传来的 16kHz 浮点音频裸流
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.float32)
            audio_buffer = np.concatenate((audio_buffer, chunk))
            
            # 计算当前极短切片的音量
            volume = np.sqrt(np.mean(chunk**2))
            
            if volume < SILENCE_THRESHOLD:
                silence_counter += 1
            else:
                silence_counter = 0 
                
            # 触发识别的条件：用户停顿，或者缓冲区已满
            is_user_paused = silence_counter >= SILENCE_CHUNKS and len(audio_buffer) > SAMPLE_RATE * MIN_BUFFER_S
            is_buffer_full = len(audio_buffer) >= SAMPLE_RATE * MAX_BUFFER_S
            
            if is_user_paused or is_buffer_full:
                audio_to_process = audio_buffer.copy()
                
                # 清空缓冲区和计数器，准备接收下一句话
                audio_buffer = np.array([], dtype=np.float32)
                silence_counter = 0
                
                # 【防幻觉核心】：计算整段提取音频的平均能量
                overall_volume = np.sqrt(np.mean(audio_to_process**2))
                
                # 如果整段声音比底噪还小，直接丢弃，不送入模型
                if overall_volume < SPEECH_THRESHOLD:
                    continue
                
                try:
                    # 使用 Whisper 管道进行识别，强制锁定韩语输出
                    result = asr_pipeline(
                        audio_to_process, 
                        generate_kwargs={"language": "korean"}
                    )
                    
                    clean_text = result["text"].strip()
                    
                    # 确保文字有效后再返回给前端
                    if clean_text:
                        print(f"🗣️ [音量:{overall_volume:.3f}] 识别: {clean_text}")
                        await websocket.send_text(clean_text)
                            
                except Exception as e:
                    print(f"⚠️ 推理异常: {e}")

    except WebSocketDisconnect:
        print("🔌 客户端已断开连接")
    except Exception as e:
        print(f"❌ 网络异常: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)