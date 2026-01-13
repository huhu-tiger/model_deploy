import sys
sys.path.append('third_party/Matcha-TTS')
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
from cosyvoice.utils.file_utils import load_wav
import torchaudio

cosyvoice = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=False, load_trt=False, load_vllm=False, fp16=False)

# NOTE if you want to reproduce the results on https://funaudiollm.github.io/cosyvoice2, please add text_frontend=False during inference
# zero_shot usage

def load_voice_data(speaker):
    """加载语音数据"""
    voice_path = f"'/media/source/CosyVoice2-Ex/voices/太乙真人.pt'"
    try:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if not os.path.exists(voice_path):
            return None
        voice_data = torch.load(voice_path, map_location=device)
        return voice_data.get('audio_ref')
    except Exception as e:
        raise ValueError(f"加载音色文件失败: {e}")

# 根据样本克隆声音
prompt_speech_16k = load_voice_data()


for i, j in enumerate(cosyvoice.inference_sft('你好，老婆大人还有乎乎', '', '', zero_shot_spk_id='my_zero_shot_spk', stream=False)):
    torchaudio.save('zero_shot_1.wav', j['tts_speech'], cosyvoice.sample_rate)
