# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-28 harness:openlumara
# Stable diffusion module: sdcpp, a1111, openai, thenoise.

import core
import aiohttp
import base64
import os
import time
import random
import asyncio

class StableDiffusionModule(core.module.Module):
    category = 'Media'

    settings = {
        'backend': {
            'description': "Engine: 'sdcpp', 'a1111', 'openai', or 'thenoise'",
            'default': 'sdcpp',
            "type": "select",
            "options": {
                "sdcpp": "stable-diffusion.cpp server or a compatible server such as koboldcpp's image server",
                "openai": "OpenAI API-compatible endpoint, such as lemonade",
                "a1111": "Automatic1111",
                "thenoise": "TheNoise - an image generation server specifically for AMD hardware"
            }
        },
        'URL': {
            'description': 'The address of the engine server',
            'default': '127.0.0.1:8080'
        },
        'model': {
            'description': "Model name (only used by the 'openai' backend; empty = server default)",
            'default': ''
        },
        'resolution': {
            'description': 'Default output resolution',
            'default': '1024x1024',
            'type': 'select',
            'options': {
                '512x512': '512\u00d7512 - SD1.5 native square',
                '512x768': '512\u00d7768 - SD1.5 portrait',
                '768x512': '768\u00d7512 - SD1.5 landscape',
                '768x768': '768\u00d7768 - SD2 native',
                '1024x1024': '1024\u00d71024 - SDXL-class square',
                '832x1216': '832\u00d71216 - SDXL-class portrait',
                '1216x832': '1216\u00d7832 - SDXL-class landscape',
                '1280x720': '1280\u00d7720 - 720p HD landscape',
                '1920x1080': '1920\u00d71080 - 1080p Full HD landscape',
            }
        },
        "cfg_scale": {
            "description": "CFG scale to use for the image generation model. This determines how closely the model should follow the prompt - the lower the cfg, the more creative it will be. Some models (such as z-image turbo) need a very low cfg (like below 1) for them to work properly.",
            "default": 6
        },
        "steps": {
            "description": "Amount of generation steps that should be used",
            "default": 20
        },
        "sampler": {
            "description": "Name of the sampler to use. Leave blank to default to the server's setting",
            "default": ""
        },
        'output_folder': {
            'description': 'Folder where generated images are saved and served from',
            'default': '~/gen_images'
        },
    }

    @property
    def asset_mounts(self):
        # expose the image folder to the webui under /ext-assets/stable_diffusion_module/gen/
        folder = self.config.get('output_folder')
        if folder:
            folder = os.path.expanduser(folder)
        return {'gen': folder} if folder else {}

    async def on_ready(self):
        self.output_dir = self.asset_mounts.get('gen') or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'webui', 'assets')
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        self.channel.log(self.name, 'Stable Diffusion Module ready. Backend: {} @ {} | images: {}'.format(
            self.config.get('backend'), self.config.get('URL'), self.output_dir))

    def _base_url(self):
        api_url = self.config.get('URL')
        if not api_url.startswith('http'):
            api_url = 'http://' + api_url
        return api_url.rstrip('/')

    def _parse_resolution(self, resolution_str):
        # Parse 'WxH' string. Returns (w, h) or None.
        if not resolution_str:
            return None
        res = resolution_str.lower().replace('\u00d7', 'x').strip()
        parts = res.split('x')
        if len(parts) != 2:
            return None
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            return None

    # ---- per-backend generators: each returns raw image bytes ----

    async def _gen_sdcpp(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'width': width,
            'height': height,
            'steps': steps,
            'cfg_scale': cfg,
            'seed': seed,
        }
        if sampler:
            payload['sampling_method'] = sampler
        async with session.post(base + '/sdcpp/v1/img_gen', json=payload) as resp:
            resp.raise_for_status()
            job = await resp.json()
        job_id = job.get('id')
        if not job_id:
            raise RuntimeError('sdcpp did not return a job id')
        deadline = time.time() + 300
        while time.time() < deadline:
            await asyncio.sleep(1)
            async with session.get('{}/sdcpp/v1/jobs/{}'.format(base, job_id),
                                   headers={'Cache-Control': 'no-store'}) as resp:
                resp.raise_for_status()
                job = await resp.json()
            status = job.get('status')
            if status in ('completed', 'succeeded'):
                images = (job.get('result') or {}).get('images') or []
                if not images:
                    raise RuntimeError('sdcpp job finished with no images')
                return base64.b64decode(images[0].get('b64_json', ''))
            if status in ('failed', 'cancelled', 'error'):
                raise RuntimeError('sdcpp job failed: {}'.format(
                    (job.get('error') or {}).get('message', status)))
        raise RuntimeError('sdcpp job timed out')

    async def _gen_a1111(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'steps': steps,
            'width': width,
            'height': height,
            'cfg_scale': cfg,
            'seed': seed,
        }
        if sampler:
            payload['sampler_name'] = sampler
        async with session.post(base + '/sdapi/v1/txt2img', json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        images = data.get('images', [])
        if not images:
            raise RuntimeError('No images returned by the A1111 API.')
        return base64.b64decode(images[0])

    async def _gen_openai(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed):
        payload = {
            'prompt': prompt,
            'n': 1,
            'size': '{}x{}'.format(width, height),
            'response_format': 'b64_json',
        }
        model = self.config.get('model')
        if model:
            payload['model'] = model
        # non-standard extras; servers that know them use them, others ignore
        for key, val in (('negative_prompt', negative), ('steps', steps),
                         ('cfg_scale', cfg), ('seed', seed)):
            if val not in ('', -1, None):
                payload[key] = val
        async with session.post(base + '/v1/images/generations', json=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
        items = data.get('data', [])
        if not items or not items[0].get('b64_json'):
            raise RuntimeError('OpenAI image API returned no image data.')
        return base64.b64decode(items[0]['b64_json'])

    async def _gen_thenoise(self, session, base, prompt, negative, steps, width, height, cfg, sampler, seed):
        payload = {
            'prompt': prompt,
            'negative_prompt': negative,
            'steps': steps,
            'width': width,
            'height': height,
            'guidance_scale': cfg,
            'seed': seed,
        }
        s = (sampler or '').lower().replace(' ', '_')
        if s in ('euler', 'er_sde'):
            payload['sampler'] = s
        async with session.post(base + '/text2image', json=payload) as resp:
            resp.raise_for_status()
            return await resp.read()  # raw PNG

    async def _generate_image_internal(self, prompt, negative_prompt='', steps=8, width=1024,
                                       height=1024, cfg_scale=1.0, sampler_name='', seed=-1):
        backend = (self.config.get('backend') or 'sdcpp').lower()
        base = self._base_url()
        gen = {
            'sdcpp': self._gen_sdcpp,
            'a1111': self._gen_a1111,
            'sdnext': self._gen_a1111,   # SD.Next speaks A1111
            'openai': self._gen_openai,
            'thenoise': self._gen_thenoise,
        }.get(backend)
        if gen is None:
            return None, "Unknown backend '{}'. Use sdcpp, a1111, openai, or thenoise.".format(backend)
        timeout = aiohttp.ClientTimeout(total=300)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                image_bytes = await gen(session, base, prompt, negative_prompt, steps,
                                        width, height, cfg_scale, sampler_name, seed)
            filename = 'sd_{}.png'.format(int(time.time()))
            with open(os.path.join(self.output_dir, filename), 'wb') as f:
                f.write(image_bytes)
            return filename, None
        except Exception as e:
            return None, str(e)

    @core.module.tool
    async def generate_image(self, prompt, negative_prompt='', seed=-1, steps=None, cfg_scale=None, sampler=None, resolution=None):
        """Generate an image and show it in the chat.

        Args:
            prompt: The image prompt.
            negative_prompt: What to exclude from the image.
            seed: Seed for generation. Pass -1 for random.
            steps: (Optional) Override default generation steps.
            cfg_scale: (Optional) Override default CFG scale.
            sampler: (Optional) Override default sampler name.
            resolution: (Optional) Override default resolution (e.g., '1280x720').

        Returns the seed that was used. Seed can be used to further refine previous image if desired.
        """
        seed = int(seed)
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)
        
        # Resolve parameters: Tool arg > Config > Default
        res_str = resolution if resolution is not None else self.config.get("resolution")
        parsed = self._parse_resolution(res_str)

        if parsed is None:
            return self.result("Invalid resolution '{}'. Use the format '1024x1024'.".format(res_str), success=False)

        width, height = parsed
        
        final_steps = steps if steps is not None else self.config.get("steps")
        final_cfg = cfg_scale if cfg_scale is not None else self.config.get("cfg_scale")
        final_sampler = sampler if sampler is not None else self.config.get("sampler")

        filename, err = await self._generate_image_internal(
            prompt, negative_prompt,
            steps=final_steps,
            width=width, height=height,
            cfg_scale=final_cfg,
            sampler_name=final_sampler,
            seed=seed
        )

        if err:
            return self.result(err, success=False)

        url = '/ext-assets/stable_diffusion_module/gen/{}'.format(filename)
        img_tag = '<img src=\"{}\" alt=\"{}\" style=\"max-width: 100%; height: auto; border-radius: 8px; margin-top: 10px;\">'.format(url, filename)
        await self.channel.push({'role': 'assistant', 'content': img_tag})
        return 'Image generated and pushed to chat. Seed used: {}. To refine this image, pass seed={} with an adjusted prompt or parameters. For a brand new image, omit seed for a random seed.'.format(seed, seed)

    @core.module.command('sd_status', help='Checks if the SD backend is reachable')
    async def sd_status_command(self, args):
        base = self._base_url()
        backend = (self.config.get('backend') or 'sdcpp').lower()
        probes = {
            'sdcpp': base + '/sdcpp/v1/capabilities',
            'a1111': base + '/sdapi/v1/options',
            'sdnext': base + '/sdapi/v1/options',
            'openai': base + '/v1/models',
            'thenoise': base + '/health',
        }
        probe = probes.get(backend)
        if probe is None:
            return "Unknown backend '{}'.".format(backend)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(probe) as resp:
                    resp.raise_for_status()
                    try:
                        info = await resp.json()
                    except Exception:
                        info = '(no json)'
            return 'SD backend ({}) is online: {}'.format(backend, info)
        except Exception as e:
            return 'SD backend is offline or unreachable: {}'.format(str(e))
