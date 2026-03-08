import gradio as gr
import numpy as np
import random
import torch
import spaces
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "4"

from PIL import Image
from diffusers import QwenImageEditPipeline


import base64
import json


os.environ["vl_base_url"] = "http://192.168.0.2:9116/v1"
os.environ["vl_model"] = "Qwen2.5-VL-7B-Instruct"

SYSTEM_PROMPT = '''
# Edit Instruction Rewriter
You are a professional edit instruction rewriter. Your task is to generate a precise, concise, and visually achievable professional-level edit instruction based on the user-provided instruction and the image to be edited.  

Please strictly follow the rewriting rules below:

## 1. General Principles
- Keep the rewritten prompt **concise**. Avoid overly long sentences and reduce unnecessary descriptive language.  
- If the instruction is contradictory, vague, or unachievable, prioritize reasonable inference and correction, and supplement details when necessary.  
- Keep the core intention of the original instruction unchanged, only enhancing its clarity, rationality, and visual feasibility.  
- All added objects or modifications must align with the logic and style of the edited input image’s overall scene.  

## 2. Task Type Handling Rules
### 1. Add, Delete, Replace Tasks
- If the instruction is clear (already includes task type, target entity, position, quantity, attributes), preserve the original intent and only refine the grammar.  
- If the description is vague, supplement with minimal but sufficient details (category, color, size, orientation, position, etc.). For example:  
    > Original: "Add an animal"  
    > Rewritten: "Add a light-gray cat in the bottom-right corner, sitting and facing the camera"  
- Remove meaningless instructions: e.g., "Add 0 objects" should be ignored or flagged as invalid.  
- For replacement tasks, specify "Replace Y with X" and briefly describe the key visual features of X.  

### 2. Text Editing Tasks
- All text content must be enclosed in English double quotes `" "`. Do not translate or alter the original language of the text, and do not change the capitalization.  
- **For text replacement tasks, always use the fixed template:**
    - `Replace "xx" to "yy"`.  
    - `Replace the xx bounding box to "yy"`.  
- If the user does not specify text content, infer and add concise text based on the instruction and the input image’s context. For example:  
    > Original: "Add a line of text" (poster)  
    > Rewritten: "Add text \"LIMITED EDITION\" at the top center with slight shadow"  
- Specify text position, color, and layout in a concise way.  

### 3. Human Editing Tasks
- Maintain the person’s core visual consistency (ethnicity, gender, age, hairstyle, expression, outfit, etc.).  
- If modifying appearance (e.g., clothes, hairstyle), ensure the new element is consistent with the original style.  
- **For expression changes, they must be natural and subtle, never exaggerated.**  
- If deletion is not specifically emphasized, the most important subject in the original image (e.g., a person, an animal) should be preserved.
    - For background change tasks, emphasize maintaining subject consistency at first.  
- Example:  
    > Original: "Change the person’s hat"  
    > Rewritten: "Replace the man’s hat with a dark brown beret; keep smile, short hair, and gray jacket unchanged"  

### 4. Style Transformation or Enhancement Tasks
- If a style is specified, describe it concisely with key visual traits. For example:  
    > Original: "Disco style"  
    > Rewritten: "1970s disco: flashing lights, disco ball, mirrored walls, colorful tones"  
- If the instruction says "use reference style" or "keep current style," analyze the input image, extract main features (color, composition, texture, lighting, art style), and integrate them concisely.  
- **For coloring tasks, including restoring old photos, always use the fixed template:** "Restore old photograph, remove scratches, reduce noise, enhance details, high resolution, realistic, natural skin tones, clear facial features, no distortion, vintage photo restoration"  
- If there are other changes, place the style description at the end.

## 3. Rationality and Logic Checks
- Resolve contradictory instructions: e.g., "Remove all trees but keep all trees" should be logically corrected.  
- Add missing key information: if position is unspecified, choose a reasonable area based on composition (near subject, empty space, center/edges).  

# Output Format Example
```json
{
   "Rewritten": "..."
}
'''

def polish_prompt(prompt, img):
    prompt = f"{SYSTEM_PROMPT}\n\nUser Input: {prompt}\n\nRewritten Prompt:"
    success=False
    while not success:
        try:
            result = custom_api(prompt, [img])
            # print(f"Result: {result}")
            # print(f"Polished Prompt: {polished_prompt}")
            if isinstance(result, str):
                result = result.replace('```json','')
                result = result.replace('```','')
                result = json.loads(result)
            else:
                result = json.loads(result)

            polished_prompt = result['Rewritten']
            polished_prompt = polished_prompt.strip()
            polished_prompt = polished_prompt.replace("\n", " ")
            success = True
        except Exception as e:
            print(f"[Warning] Error during API call: {e}")
    return polished_prompt


def encode_image(pil_image):
    import io
    buffered = io.BytesIO()
    pil_image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")




def api(prompt, img_list, model="qwen-vl-max-latest", kwargs={}):
    import dashscope
    api_key = os.environ.get('DASH_API_KEY')
    if not api_key:
        raise EnvironmentError("DASH_API_KEY is not set")
    assert model in ["qwen-vl-max-latest"], f"Not implemented model {model}"
    sys_promot = "you are a helpful assistant, you should provide useful answers to users."
    messages = [
        {"role": "system", "content": sys_promot},
        {"role": "user", "content": []}]
    for img in img_list:
        messages[1]["content"].append(
            {"image": f"data:image/png;base64,{encode_image(img)}"})
    messages[1]["content"].append({"text": f"{prompt}"})

    response_format = kwargs.get('response_format', None)

    response = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=model, # For example, use qwen-plus here. You can change the model name as needed. Model list: https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=messages,
        result_format='message',
        response_format=response_format,
        )

    if response.status_code == 200:
        return response.output.choices[0].message.content[0]['text']
    else:
        raise Exception(f'Failed to post: {response}')


def custom_api(prompt, img_list, model="gpt-4o-mini", kwargs={}):
    import os
    try:
        from openai import OpenAI
    except Exception as e:
        raise ImportError("请先安装 openai 包: pip install openai") from e

    api_key = kwargs.get('openai_api_key', os.environ.get('OPENAI_API_KEY'))
    base_url = kwargs.get('openai_api_base', os.environ.get('OPENAI_API_BASE') or os.environ.get('OPENAI_BASE_URL') or os.environ.get('vl_base_url'))
    model_name = kwargs.get('model_name', os.environ.get('vl_model'))
    client_init_kwargs = {
        'api_key': api_key or 'EMPTY'
    }
    if base_url:
        client_init_kwargs['base_url'] = base_url

    client = OpenAI(**client_init_kwargs)

    system_prompt = kwargs.get('system_prompt', 'you are a helpful assistant, you should provide useful answers to users.')

    user_content = [{"type": "text", "text": f"{prompt}"}]
    for pil_image in (img_list or []):
        try:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encode_image(pil_image)}"}
            })
        except Exception:
            continue

    temperature = float(kwargs.get('temperature', 0.2))
    max_tokens = int(kwargs.get('max_tokens', 2048))

    params = {
        'model': model_name,
        'messages': [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    response_format = kwargs.get('response_format')
    if response_format is not None:
        params['response_format'] = response_format

    resp = client.chat.completions.create(**params)
    try:
        return resp.choices[0].message.content
    except Exception:
        raise Exception(f"OpenAI 返回格式不兼容: {resp}")

# --- Model Loading ---
dtype = torch.bfloat16
use_multi_gpu = torch.cuda.is_available() and (torch.cuda.device_count() > 1 or (',' in os.environ.get('CUDA_VISIBLE_DEVICES', '')))
if use_multi_gpu:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    pipe = QwenImageEditPipeline.from_pretrained("/media/llm/Qwen-Image-Edit", torch_dtype=dtype, device_map='balanced')
else:
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    # Load the model pipeline
    pipe = QwenImageEditPipeline.from_pretrained("/media/llm/Qwen-Image-Edit", torch_dtype=dtype).to(device)

# --- UI Constants and Helpers ---
MAX_SEED = np.iinfo(np.int32).max

# --- Main Inference Function (with hardcoded negative prompt) ---
@spaces.GPU(duration=200)
def infer(
    image,
    prompt,
    seed=42,
    randomize_seed=False,
    true_guidance_scale=1.0,
    num_inference_steps=50,
    rewrite_prompt=True,
    progress=gr.Progress(track_tqdm=True),
):
    """
    Generates an image using the local Qwen-Image diffusers pipeline.
    """
    # Hardcode the negative prompt as requested
    negative_prompt = " "
    
    if randomize_seed:
        seed = random.randint(0, MAX_SEED)

    # Set up the generator for reproducibility
    generator = torch.Generator(device=device).manual_seed(seed)
    
    print(f"Calling pipeline with prompt: '{prompt}'")
    print(f"Negative Prompt: '{negative_prompt}'")
    print(f"Seed: {seed}, Steps: {num_inference_steps}, Guidance: {true_guidance_scale}")
    if rewrite_prompt:
        prompt = polish_prompt(prompt, image)
        print(f"Rewritten Prompt: {prompt}")

    # Generate the image
    images = pipe(
        image,
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=num_inference_steps,
        generator=generator,
        true_cfg_scale=true_guidance_scale,
        num_images_per_prompt=1
    ).images
    
    return images[0], seed

# --- Examples and UI Layout ---
examples = []

css = """
#col-container {
    margin: 0 auto;
    max-width: 1024px;
}
#edit_text{margin-top: -62px !important}
"""

with gr.Blocks(css=css) as demo:
    with gr.Column(elem_id="col-container"):
        gr.HTML('<img src="https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-Image/qwen_image_edit_logo.png" alt="Qwen-Image Logo" width="400" style="display: block; margin: 0 auto;">')
        gr.Markdown("[Learn more](https://github.com/QwenLM/Qwen-Image) about the Qwen-Image series. Try on [Qwen Chat](https://chat.qwen.ai/), or [download model](https://huggingface.co/Qwen/Qwen-Image-Edit) to run locally with ComfyUI or diffusers.")
        with gr.Row():
            with gr.Column():
                input_image = gr.Image(label="Input Image", show_label=False, type="pil")

            result = gr.Image(label="Result", show_label=False, type="pil")
        with gr.Row():
            prompt = gr.Text(
                    label="Prompt",
                    show_label=False,
                    placeholder="describe the edit instruction",
                    container=False,
            )
            run_button = gr.Button("Edit!", variant="primary")

        with gr.Accordion("Advanced Settings", open=False):
            # Negative prompt UI element is removed here

            seed = gr.Slider(
                label="Seed",
                minimum=0,
                maximum=MAX_SEED,
                step=1,
                value=0,
            )

            randomize_seed = gr.Checkbox(label="Randomize seed", value=True)

            with gr.Row():

                true_guidance_scale = gr.Slider(
                    label="True guidance scale",
                    minimum=1.0,
                    maximum=10.0,
                    step=0.1,
                    value=4.0
                )

                num_inference_steps = gr.Slider(
                    label="Number of inference steps",
                    minimum=1,
                    maximum=50,
                    step=1,
                    value=50,
                )
                
                rewrite_prompt = gr.Checkbox(label="Rewrite prompt", value=True)

        gr.Examples(examples=[
                ["neon_sign.png", "change the text to read 'Qwen Image Edit is here'"],
                ["cat_sitting.jpg", "make the cat floating in the air and holding a sign that reads 'this is fun' written with a blue crayon"],
                ["pie.png", "turn the style of the photo to vintage comic book"]],
                    inputs=[input_image, prompt], 
                    outputs=[result, seed], 
                    fn=infer, 
                    cache_examples=False)

    gr.on(
        triggers=[run_button.click, prompt.submit],
        fn=infer,
        inputs=[
            input_image,
            prompt,
            seed,
            randomize_seed,
            true_guidance_scale,
            num_inference_steps,
            rewrite_prompt,
        ],
        outputs=[result, seed],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7862)