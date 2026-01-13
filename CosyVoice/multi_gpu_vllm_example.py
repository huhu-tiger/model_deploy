import sys
sys.path.append('third_party/Matcha-TTS')
from vllm import ModelRegistry
from cosyvoice.vllm.cosyvoice2 import CosyVoice2ForCausalLM
ModelRegistry.register_model("CosyVoice2ForCausalLM", CosyVoice2ForCausalLM)

from cosyvoice.cli.cosyvoice import CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from cosyvoice.utils.common import set_all_random_seed
from tqdm import tqdm
import argparse
import torch
import os

def main():
    parser = argparse.ArgumentParser(description='CosyVoice2 多GPU推理示例')
    parser.add_argument('--tensor_parallel_size', type=int, default=2, help='张量并行大小')
    parser.add_argument('--gpu_memory_utilization', type=float, default=0.7, help='GPU内存利用率')
    args = parser.parse_args()
    
    print(f"使用张量并行大小: {args.tensor_parallel_size}")
    print(f"GPU内存利用率: {args.gpu_memory_utilization}")
    
    # 检查可用GPU数量
    gpu_count = torch.cuda.device_count()
    print(f"可用GPU数量: {gpu_count}")
    if args.tensor_parallel_size > gpu_count:
        print(f"警告: 请求的张量并行大小({args.tensor_parallel_size})大于可用GPU数量({gpu_count})")
        print(f"将张量并行大小调整为: {gpu_count}")
        args.tensor_parallel_size = gpu_count
    
    # 加载模型前修改vLLM的环境变量
    os.environ["VLLM_TP_SIZE"] = str(args.tensor_parallel_size)
    
    # 使用多GPU初始化CosyVoice2
    model_path = 'pretrained_models/CosyVoice2-0.5B'
    cosyvoice = CosyVoice2(model_path, 
                          load_jit=True, 
                          load_trt=False, 
                          load_vllm=True, 
                          fp16=True)
    
    # 修改vLLM引擎参数
    from vllm import EngineArgs, LLMEngine
    
    # 检查模型是否已经加载了vLLM
    if hasattr(cosyvoice.model.llm, 'vllm'):
        print("vLLM已加载，正在重新配置多GPU参数...")
        # 导出模型到vLLM格式
        from cosyvoice.vllm.cosyvoice2 import export_cosyvoice2_vllm
        export_cosyvoice2_vllm(cosyvoice.model.llm, f'{model_path}/vllm', cosyvoice.model.device)
        
        # 使用多GPU参数重新创建LLMEngine
        engine_args = EngineArgs(
            model=f'{model_path}/vllm',
            skip_tokenizer_init=True,
            enable_prompt_embeds=True,
            tensor_parallel_size=args.tensor_parallel_size,
            gpu_memory_utilization=args.gpu_memory_utilization
        )
        cosyvoice.model.llm.vllm = LLMEngine.from_engine_args(engine_args)
        print(f"vLLM引擎已重新配置，使用{args.tensor_parallel_size}个GPU")
    
    # 使用多GPU进行推理
    prompt_speech_16k = load_wav('./asset/zero_shot_prompt.wav', 16000)
    for i in tqdm(range(3)):  # 只运行3次示例
        set_all_random_seed(i)
        for i, j in enumerate(cosyvoice.inference_zero_shot(
            '收到好友从远方寄来的生日礼物，那份意外的惊喜与深深的祝福让我心中充满了甜蜜的快乐，笑容如花儿般绽放。', 
            '希望你以后能够做的比我还好呦。', 
            prompt_speech_16k, 
            stream=False)):
            print(f"生成音频长度: {j['tts_speech'].shape}")

if __name__=='__main__':
    main() 