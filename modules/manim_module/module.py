import core
import os
import subprocess
import tempfile
import time
import shutil
import glob
from typing import Optional, Any

class ManimModule(core.module.Module):
    """
    Manim Animation Module
    
    Provides programmatic rendering of mathematical and scientific animations 
    using the Manim Community engine. This module handles the generation of 
    MP4 videos from Python code and integrates them into the WebUI assets.
    """

    category = 'Media'

    settings = {
        'output_folder': {
            'type': 'string',
            'description': 'Folder where rendered videos will be saved (relative to module directory)',
            'default': 'webui/assets'
        },
        'quality': {
            'type': 'select',
            'description': 'Render quality preset for Manim output',
            'default': 'high',
            'options': {
                'low': '480p (fast preview)',
                'medium': '720p (balanced)',
                'high': '1080p (high quality)',
                'fourk': '4K (ultra high quality)'
            }
        },
        'fps': {
            'type': 'number',
            'description': 'Frames per second for the output video',
            'default': 30
        }
    }

    dependencies = ['manim']

    async def on_install(self):
        """
        Handles the installation of system-level dependencies required by Manim.
        """
        self.channel.log(self.name, "Installing system dependencies for Manim...")
        
        # Essential system libraries for Manim rendering
        sys_deps = ['ffmpeg', 'libcairo2-dev', 'libpango1.0-dev']
        
        try:
            # Update package lists
            subprocess.run(['apt-get', 'update'], capture_output=True, check=True)
            
            for dep in sys_deps:
                self.channel.log(self.name, f"Installing {dep}...")
                subprocess.run(['apt-get', 'install', '-y', dep], capture_output=True, check=True)
                
            self.channel.log(self.name, "System dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            self.channel.log(self.name, f"Warning: System dependency installation failed: {e.stderr.decode()}")
        except Exception as e:
            self.channel.log(self.name, f"Unexpected error during installation: {str(e)}")

    async def on_ready(self):
        """
        Initializes the module and verifies the environment.
        """
        module_path = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(module_path, 'webui', 'assets')

        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        # Use 'python3 -m manim' for maximum compatibility across different Venv setups
        self.manim_exe = "python3 -m manim"
        self.ffmpeg_exe = shutil.which('ffmpeg')

        # Health Check
        if not self.ffmpeg_exe:
            self.channel.log(self.name, "CRITICAL: FFmpeg not found. Videos cannot be rendered.")
        else:
            self.channel.log(self.name, "Manim environment verified. Ready for rendering.")

    def _get_quality_flags(self) -> list:
        """
        Maps internal quality settings to Manim CLI flags.
        """
        quality_map = {
            'low': ['-ql'],
            'medium': ['-qm'],
            'high': ['-qh'],
            'fourk': ['-qk']
        }
        quality = self.config.get('quality', 'high')
        return quality_map.get(quality, ['-qh'])

    async def _render_scene_internal(
        self,
        scene_code: str,
        scene_name: str,
        quality: str = None,
        fps: int = None
    ):
        """
        Internal logic to render a scene and move the output to the WebUI assets folder.
        """
        if not self.manim_exe:
            return None, "Manim executable not configured."

        if quality:
            self.config.set('quality', quality)
        if fps:
            self.config.set('fps', fps)

        quality_flags = self._get_quality_flags()

        # Create a temporary file for the scene code
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            prefix='manim_scene_',
            delete=False,
            dir='/tmp'
        ) as temp_file:
            temp_file.write(scene_code)
            temp_file_path = temp_file.name

        try:
            # Construct command: python3 -m manim <file> <scene> <flags>
            cmd = self.manim_exe.split() + [temp_file_path, scene_name] + quality_flags

            self.channel.log(self.name, f"Rendering Manim scene: {scene_name}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600, # Increased timeout for high-res renders
                cwd='/tmp',
                env={**os.environ, 'PATH': os.environ.get('PATH', '') + ':/home/lumara/.local/bin'}
            )

            if result.returncode != 0:
                error_msg = result.stderr if result.stderr else result.stdout
                return None, f"Manim rendering failed:\n{error_msg}"

            # Manim stores videos in a nested structure based on quality
            # We search recursively in /tmp/media/videos for the specific scene file
            search_pattern = os.path.join('/tmp/media/videos', '**', f'{scene_name}.mp4')
            found_files = glob.glob(search_pattern, recursive=True)

            if not found_files:
                return None, "Render succeeded but output file was not found in the media directory."

            source_path = found_files[0]
            dest_filename = f'{scene_name}.mp4'
            dest_path = os.path.join(self.output_dir, dest_filename)

            # Move the rendered video to the WebUI assets folder for display
            shutil.copy(source_path, dest_path)
            
            return dest_filename, None

        except Exception as e:
            return None, f"An unexpected error occurred during rendering: {str(e)}"
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    async def render_and_show_video(
        self,
        scene_code: str,
        scene_name: str = 'MainScene',
        quality: str = None,
        fps: int = None
    ):
        """
        Renders a Manim scene and pushes the resulting video to the chat.
        """
        filename, err = await self._render_scene_internal(scene_code, scene_name, quality, fps)
        if err:
            return self.result(err, success=False)

        url = f"/ext-assets/manim_module/{filename}"
        video_tag = f'<video controls src="{url}" style="max-width: 100%; height: auto; border-radius: 8px; margin-top: 10px;" poster="{url}"></video>'

        await self.channel.push({
            "role": "assistant",
            "content": video_tag
        })

        return f"Manim scene '{scene_name}' rendered and displayed! Video saved as: {filename}"

    async def render_scene_to_file(
        self,
        scene_code: str,
        scene_name: str = 'MainScene',
        quality: str = None,
        fps: int = None
    ):
        """
        Renders a Manim scene to the assets folder without pushing to chat.
        """
        filename, err = await self._render_scene_internal(scene_code, scene_name, quality, fps)
        if err:
            return self.result(err, success=False)
        return f"Manim scene '{scene_name}' rendered successfully. Saved as: {filename}"

    @core.module.command('manim_status', help='Checks if Manim and FFmpeg are available')
    async def manim_status_command(self, args: list):
        """
        Command to verify the health of the Manim installation.
        """
        checks = []
        # Check FFmpeg
        if self.ffmpeg_exe:
            try:
                res = subprocess.run([self.ffmpeg_exe, '-version'], capture_output=True, text=True, timeout=5)
                checks.append(f"✓ FFmpeg: {res.stdout.splitlines()[0]}")
            except Exception as e:
                checks.append(f"✗ FFmpeg: Error - {str(e)}")
        else:
            checks.append("✗ FFmpeg: Not found in system PATH")

        # Check Manim
        try:
            res = subprocess.run(self.manim_exe.split() + ['--version'], capture_output=True, text=True, timeout=10)
            checks.append(f"✓ Manim: {res.stdout.strip()}")
        except Exception as e:
            checks.append(f"✗ Manim: Error - {str(e)}")

        return "\n".join(checks)
