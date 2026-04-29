import os
import re
import numpy as np
import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from funasr import AutoModel
import uvicorn

app = FastAPI()

# ==========================================
# 1. 极速加载 SenseVoice 与 VAD 模型 (PyTorch 生态)
# ==========================================
print("🚀 正在初始化 FunASR + SenseVoiceSmall 模型...")
print(f"🖥️ 当前 PyTorch 检测到的 GPU 状态: {torch.cuda.is_available()}")

print("🚀 正在从 Hugging Face 初始化 SenseVoiceSmall 模型...")

try:
    # 核心修改点：使用 iic/SenseVoiceSmall，这是阿里的官方 HF 仓库 ID
    model = AutoModel(
        model="iic/SenseVoiceSmall", 
        hub="hf",                   # 强制指定从 Hugging Face 下载
        vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch", # VAD 也改用 HF 路径
        vad_kwargs={"hub": "hf"},
        trust_remote_code=True,
        device="cuda:0"             # 既然 GPU 已经 OK，强制使用显卡加速
    )
    print("✅ 模型加载完成！显存已就位。")
except Exception as e:
    print(f"❌ 模型加载失败，正在尝试备选路径: {e}")
    # 如果 HF 依然有问题（网络波动），会自动回退到 modelscope（虽然慢点但稳）
    model = AutoModel(
        model="iic/SenseVoiceSmall",
        vad_model="fsmn-vad",
        trust_remote_code=True,
        device="cuda:0"
    )

# ==========================================
# 2. FastAPI Web 服务与 WebSocket 逻辑
# ==========================================
@app.get("/")
async def get_webpage():
    # 直接将同目录下的 index.html 喂给手机浏览器
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# ==========================================
# 3. 智能动态切片与 WebSocket 逻辑
# ==========================================
SAMPLE_RATE = 16000 
MAX_BUFFER_S = 4.0      # 最大允许积累的音频时长 (4秒，保证长句语境)
MIN_BUFFER_S = 0.5      # 最少需要积累的音频时长 (防误触)
SILENCE_THRESHOLD = 0.015 # 静音判定阈值 (根据手机麦克风底噪可微调)
SILENCE_CHUNKS = 3      # 连续几次检测到极小音量就认为是一句话结束

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = np.array([], dtype=np.float32)
    silence_counter = 0
    
    print("📱 手机端已连接，智能动态 VAD 算法已启动...")
    
    try:
        while True:
            # 1. 接收实时音频裸流
            data = await websocket.receive_bytes()
            chunk = np.frombuffer(data, dtype=np.float32)
            audio_buffer = np.concatenate((audio_buffer, chunk))
            
            # 2. 计算当前极短切片(约0.25秒)的音量能量 (RMS)
            volume = np.sqrt(np.mean(chunk**2))
            
            # 3. 静音判定逻辑
            if volume < SILENCE_THRESHOLD:
                silence_counter += 1
            else:
                silence_counter = 0 # 一旦有声音，重置静音计数器
                
            # 4. 触发识别的两大条件：
            # 条件 A: 用户停顿了（连续几次静音），且缓冲池里有足够长度的声音
            is_user_paused = silence_counter >= SILENCE_CHUNKS and len(audio_buffer) > SAMPLE_RATE * MIN_BUFFER_S
            # 条件 B: 用户说话太快太长，达到了最大缓冲区限制（强行截断防内存溢出）
            is_buffer_full = len(audio_buffer) >= SAMPLE_RATE * MAX_BUFFER_S
            
            if is_user_paused or is_buffer_full:
                # 提取完整音频，并施加 1.5 倍的数字增益，放大手机麦克风音量
                audio_to_process = audio_buffer.copy() * 1.5 
                
                # 清空缓冲区和计数器，迎接下一句话
                audio_buffer = np.array([], dtype=np.float32)
                silence_counter = 0
                
                try:
                    # 送入 GPU 极速推理
                    res = model.generate(
                        input=audio_to_process,
                        language="ko", 
                        use_itn=True  # 开启逆文本正则化 (优化数字、日期的韩语显示格式)
                    )
                    
                    if res and len(res) > 0:
                        raw_text = res[0].get("text", "")
                        
                        # 清洗富文本标签
                        clean_text = re.sub(r'<[^>]+>', '', raw_text).strip()
                        
                        # 过滤掉标点符号和空字符串
                        if clean_text and clean_text not in ["。", "，", ".", ","]:
                            print(f"🗣️ [音量:{volume:.3f}] 识别: {clean_text}")
                            await websocket.send_text(clean_text)
                            
                except Exception as e:
                    print(f"⚠️ 瞬间推理异常 (已忽略): {e}")

    except WebSocketDisconnect:
        print("🔌 客户端已断开连接")
    except Exception as e:
        print(f"❌ 网络传输异常: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)