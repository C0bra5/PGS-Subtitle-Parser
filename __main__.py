import os
import argparse
import subprocess
from pgs import PGSParser
from ffprobe import FFProbe
from pathlib import Path

def uniquify_file_name(out_path: str) -> str:
	out_path
	if os.path.exists(out_path):
		(path_and_name, ext) = os.path.splitext(out_path)
		i = 0
		while i := i + 1:
			out_path = f'{path_and_name} ({i}){ext}'
			if not os.path.exists(out_path):
				break
	return out_path

def check_if_ffmpeg_exists(ffmpeg_path):
	global check_if_ffmpeg_exists
	try:
		subprocess.run([ffmpeg_path, "-h"], check=True, capture_output=True)
		# dirty but functional
		check_if_ffmpeg_exists = lambda a: True
	except subprocess.CalledProcessError:
		raise IOError("FFmpeg didn't have a 0 return code.")
	except FileNotFoundError:
		raise IOError('FFmpeg not found.')

def run_ffmpeg(ffmpeg_path: str, *commands, pipe_in: bytes | None = None) -> bytes:
	check_if_ffmpeg_exists(ffmpeg_path)
	# personal safety since ffmpeg is gonna need at least 3 arguments: "-i" "in_file" "output_file"
	if len(commands) < 3:
		raise ValueError('not enough args for ffmpeg')
	
	cmd = [ffmpeg_path, '-v', 'warning', '-hide_banner', *commands]
	kwargs = {'stdout': subprocess.PIPE}
	ffmpeg: subprocess.CompletedProcess = subprocess.run(cmd, input=pipe_in, **kwargs)
	if ffmpeg.returncode:
		raise IOError('ffmpeg didn''t return a 0 return code.')

	return ffmpeg.stdout

def dump_images_from_file(input_file_path, output_dir_path, ffprobe_path, ffmpeg_path):
	output_dir_path = os.path.join(output_dir_path, Path(input_file_path).stem)

	if Path(input_file_path).suffix == '.sup':
		# read the subtitle contents
		with open(input_file_path, 'rb') as f:
			data = f.read()
			# parse it
			parsed = PGSParser.read_from_bytes(data)

			# dumps all the images
			output_dir_path = uniquify_file_name(output_dir_path)
			os.mkdir(output_dir_path)
			print(f'dumping all images from "{input_file_path}" to "{output_dir_path}"')
			parsed.save_images(output_dir_path)
	else:
		# else ffprobe it for streams and dump subs when found
		for stream in FFProbe(ffprobe_path=ffprobe_path, file_name=input_file_path)['streams']:
			if stream['codec_name'] != 'hdmv_pgs_subtitle':
				continue
			# extract subs
			stream_index = stream['index']
			sub_data = run_ffmpeg(ffmpeg_path, '-i', input_file_path, '-map',f'0:{stream_index}','-c','copy', '-f', 'sup', '-')
			# dump the images
			
			output_dir_path_for_sub = uniquify_file_name(f'{output_dir_path} - {stream_index}')
			os.mkdir(output_dir_path_for_sub)
			print(f'dumping stream {stream_index} to "{output_dir_path_for_sub}"')
			PGSParser.read_from_bytes(sub_data).save_images(output_dir_path_for_sub)

def dump_sups_from_file(input_file_path, output_dir_path, ffprobe_path, ffmpeg_path):
	output_dir_path = os.path.join(output_dir_path, Path(input_file_path).stem)
	# scan the file with ffprobe
	for stream in FFProbe(ffprobe_path=ffprobe_path, file_name=input_file_path)['streams']:
		if stream['codec_name'] != 'hdmv_pgs_subtitle':
			continue
		# extract subs
		stream_index = stream['index']
		sub_data = run_ffmpeg(ffmpeg_path, '-i', input_file_path, '-map',f'0:{stream_index}','-c','copy', '-f', 'sup', '-')
		# dump the images
		
		output_file_path = uniquify_file_name(f'{output_dir_path} - {stream_index}.sup')
		print(f'dumping PGS stream {stream_index} to "{output_file_path}"')
		with open(output_file_path, 'wb') as f:
			f.write(sub_data)
		
if __name__ == '__main__':
	parser = argparse.ArgumentParser(
		formatter_class=argparse.RawDescriptionHelpFormatter,
		description= os.linesep.join((
			"images are dumped with file names that represent:",
			"{ds.id}.{ods.id} - {mm}.{ss}.{fff}.png",
			"",
			"usage Examples:",
			"",
			"\tdump all sup files out of a mkv:",
			"\tinput.mkv sup ./out",
			"",
			"\tdump all images out of a mkv:",
			"\tinput.mkv images ./out_images",
			"",
			"\tdump all images out of a mkv:",
			"\tinput.sup images ./out_images"
		))
	)

	parser.add_argument('input_file', help='The input file to use.')
	parser.add_argument('what_to_dump', choices=('sup','images'), help='What to dump from the input.')
	parser.add_argument('output_dir', nargs='?', default=None, help='Where to dump the output.')
	parser.add_argument('--ffmpeg', default=None, help='The path to ffmpeg', type=str)
	parser.add_argument('--ffprobe', default=None, help='The path to ffprobe', type=str)
	args = vars(parser.parse_args())
	
	# check if input file exists
	input_file = args['input_file']
	if not Path(input_file).is_file():
		raise IOError(f'file not found: {input_file}')
	
	what_to_dump = args['what_to_dump']

	# create output dir if needed
	output_dir = args['output_dir']
	if output_dir is None:
		match what_to_dump:
			case 'sup':
				output_dir = './out'
			case 'images':
				output_dir = './out_images'
			case _:
				raise ValueError('unknown dump_action')
	
	# create output dir if it doesn't exist
	if not Path(output_dir).is_dir():
		os.mkdir(output_dir)

	# check ffmpeg path
	ffmpeg_path = args['ffmpeg']
	if ffmpeg_path is None:
		ffmpeg_path = 'ffmpeg'
	elif not Path(ffmpeg_path).is_file():
		raise IOError('ffmpeg path was set but the fine in question could not be found.')
	
	# check ffprobe path
	ffprobe_path = args['ffprobe']
	if ffprobe_path is None:
		ffprobe_path = 'ffprobe'
	elif not Path(ffprobe_path).is_file():
		raise IOError('ffprobe path was set but the fine in question could not be found.')


	# get workin'
	match what_to_dump:
		case 'sup':
			dump_sups_from_file(input_file, output_dir, ffprobe_path, ffmpeg_path)
		case 'images':
			dump_images_from_file(input_file, output_dir, ffprobe_path, ffmpeg_path)
		case _:
			raise ValueError('unknown dump_action')