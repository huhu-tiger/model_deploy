from enum import Enum  # 导入 Enum
from pydantic import BaseModel, validator
# 请求参数模型
# 定义采样率枚举
class SampleRateEnum(Enum):
    RATE_32000 = 32000
    RATE_16000 = 16000

class ChatCompletionRequest(BaseModel):
    model: str = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"  # 默认模型
    input: str = ""  # 默认输入文本
    voice: str = "FunAudioLLM/CosyVoice2-0.5B:alex"  # 默认语音
    response_format: str = "mp3"  # 默认响应格式
    sample_rate: SampleRateEnum = SampleRateEnum.RATE_16000  # 默认采样率为 16000
    stream: bool = True  # 默认启用流式传输
    speed: float = 1  # 默认语速
    gain: int = 0  # 默认音量增益
    # 增加参数
    seed: int = 0 # 默认随机种子
    mode: str = "zero_shot"


class TTSCloneRequest(BaseModel):
    model: str = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"  # 默认模型
    input: str = ""  # 默认输入文本
    prompt_text: str = "You are a helpful assistant.<|endofprompt|>"  # CosyVoice3 需要的 prompt_text
    voice_id: str = ""  # 已保存的音色ID，如果提供则使用，否则需要 prompt_file
    prompt_file: str = ""  # prompt 音频文件URL，如果 voice_id 为空则需要提供
    response_format: str = "wav"  # 默认响应格式
    sample_rate: SampleRateEnum = SampleRateEnum.RATE_16000  # 默认采样率为 16000
    stream: bool = False  # 默认启用流式传输
    # 新增：输出类型，file 返回音频文件流，url 上传MinIO返回下载地址
    output: str = "file"


class TTSCloneDelRequest(BaseModel):
    voice_id: str = "alex"  # 默认语音

class TTSCloneSpkRequest(BaseModel):
    input: str = ""  # 音频中文本
    voice_name: str = ""  # voice名称
    voice_file: str = ".wav"  # 音频下载文件

class TTSInstructRequest(BaseModel):
    input: str = ""  # 输入文本
    instruct_text: str = "You are a helpful assistant.<|endofprompt|>"  # 指令文本
    prompt_file: str = ""  # prompt 音频文件URL
    response_format: str = "wav"
    output: str = "file"

class TTSCrossLingualRequest(BaseModel):
    input: str = ""  # 输入文本
    prompt_file: str = ""  # prompt 音频文件URL
    response_format: str = "wav"
    output: str = "file"
