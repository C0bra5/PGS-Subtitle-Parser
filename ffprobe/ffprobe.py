import subprocess
import logging
import json
import typing
import sys
if typing.TYPE_CHECKING:
	from .ffprobe_typing import FFProbeResult

def check_if_ffprobe_exists():
	global check_if_ffprobe_exists
	try:
		subprocess.run(["ffprobe", "-h"], check=True, capture_output=True)
		# dirty but functional
		check_if_ffprobe_exists = lambda: True
	except subprocess.CalledProcessError:
		raise IOError("FFProbe didn't have a 0 return code.")
	except FileNotFoundError:
		raise IOError('FFProbe not found.')
	
def FFProbe(
		ffprobe_path:str = 'ffprobe',
		show_streams:bool = True,
		show_format:bool = True,
		show_data:bool = False,
		show_errors:bool = False,
		show_chapters:bool = False,
		show_packets:bool = False,
		show_programs:bool = False,
		show_frames:bool = False,
		show_stream_groups:bool = False,
		file_name: str | None = None,
		pipe: bytes | None = None,
		*args
	) -> 'FFProbeResult':
		check_if_ffprobe_exists()
		# prepare the base command
		cmd = [ffprobe_path, '-v', 'warning', '-hide_banner', '-of', 'json']
		# add flags
		if show_streams: cmd.append('-show_streams')
		if show_format: cmd.append('-show_format')
		if show_data: cmd.append('-show_data')
		if show_errors: cmd.append('-show_errors')
		if show_chapters: cmd.append('-show_chapters')
		if show_packets: cmd.append('-show_packets')
		if show_programs: cmd.append('-show_programs')
		if show_frames: cmd.append('-show_frames')
		if show_stream_groups: cmd.append('-show_stream_groups')
		# add inputs
		if file_name is not None: cmd.extend(('-i', file_name))
		if pipe is not None: cmd.extend(('-i', '-'))
		# add custom args
		cmd.extend(args)

		# run ffprobe
		ffprobe = subprocess.run(cmd, capture_output=True, input=pipe, check=False)
		# panic if it also panicked
		if ffprobe.returncode:
			logging.critical(msg = f"[ffprobe] {ffprobe.stderr.decode()}", exc_info=sys.exc_info())
			raise IOError(ffprobe.stderr.decode())
		elif ffprobe.stderr != b'':
			logging.warning(msg = f"[ffprobe] {ffprobe.stderr.decode()}")
		
		return json.loads(ffprobe.stdout.decode())