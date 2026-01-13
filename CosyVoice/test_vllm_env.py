import sys
sys.path.append('third_party/Matcha-TTS')
from vllm import ModelRegistry
from cosyvoice.vllm.cosyvoice2 import CosyVoice2ForCausalLM
ModelRegistry.register_model("CosyVoice2ForCausalLM", CosyVoice2ForCausalLM)

from vllm import EngineArgs, LLMEngine
import torch

def main():
    print("PyTorch版本:", torch.__version__)
    print("CUDA是否可用:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("可用GPU数量:", torch.cuda.device_count())
        for i in range(torch.cuda.device_count()):
            print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
    
    print("\nvLLM多GPU支持参数:")
    args = EngineArgs()
    print("tensor_parallel_size:", args.tensor_parallel_size)
    print("pipeline_parallel_size:", args.pipeline_parallel_size)
    print("data_parallel_size:", args.data_parallel_size)
    print("gpu_memory_utilization:", args.gpu_memory_utilization)
    
    print("\n环境设置完成，vLLM虚拟环境已准备就绪！")
    print("可以使用以下命令运行vllm_example.py:")
    print("python vllm_example.py")

if __name__ == "__main__":
    main() 