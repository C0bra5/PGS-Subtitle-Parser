
from PIL import Image
from ffprobe import FFProbe
import numpy as np

from pgs import *
import os
from os import path
from io import BytesIO, StringIO
from glob import glob
from dataclasses import dataclass
import subprocess
import re
import math
import multiprocessing
import traceback
import sys

import typing
if typing.TYPE_CHECKING:
	import multiprocessing.pool

# Turn this on to make the pc work slightly faster since this is still a somewhat slow thing even though most of the work is multi-threaded
# import psutil
# psutil.Process(os.getpid()) 
# p.nice(psutil.HIGH_PRIORITY_CLASS)

FFMPEG_PATH = 'ffmpeg'
FFPROBE_PATH = 'ffprobe'
MAGICK_PATH = 'magick'
MKVPROPEDIT_PATH = 'mkvpropedit'
FIX_IMAGES_WITH_FFMPEG_AND_MAGIC = False


TEMP_DIR = path.join('.','temp')
OUT_DIR = path.join('.', 'out')

@dataclass
class SubToFix():
	input_index: int
	original_stream_index: int
	name: str
	start: str
	data: bytes
	temp_path: str

	def get_name(self):
		if self.name is not None and self.name != '':
			return self.name
		else:
			return f'#{self.original_stream_index}'

def print_err(*args, **kwargs):
	with StringIO() as buf: 
		print(*args, file=buf, **kwargs)
		contents = buf.getvalue()
		buf.close()
	contents = '\033[91m' + contents + '\033[0m'
	print(contents, file=sys.stderr)

def print_info(*args, **kwargs):
	with StringIO() as buf: 
		print(*args, file=buf, **kwargs)
		contents = buf.getvalue()
		buf.close()
	contents = '\033[92m' + contents.strip('\r\n\t ') + '\033[0m'
	print(contents, file=sys.stdout)

def run_ffmpeg(*commands, pipe_in: bytes | None = None) -> bytes:
	# personal safety since ffmpeg is gonna need at least 3 arguments: "-i" "in_file" "output_file"
	if len(commands) < 3:
		raise ValueError('not enough args for ffmpeg')
	
	cmd = [FFMPEG_PATH, '-v', 'warning', '-hide_banner', *commands]
	kwargs = {'stdout': subprocess.PIPE}
	ffmpeg: subprocess.CompletedProcess = subprocess.run(cmd, input=pipe_in, **kwargs)
	if ffmpeg.returncode:
		raise IOError('ffmpeg didn''t return a 0 return code.')

	return ffmpeg.stdout
	
def run_magick(img_data:np.ndarray, command:str):

	with BytesIO() as buf, Image.fromarray(img_data, mode='RGBA') as temp_img:
		temp_img.save(buf, format='png')
		buf.seek(0)
		to_magick = buf.read()
		
	cmd = [MAGICK_PATH,'-', *re.split(r'\s+', command) ,'png32:-']
	p = subprocess.run(cmd, capture_output=True, check=True, input=to_magick)
	
	with BytesIO(p.stdout) as img_buff, Image.open(img_buff, formats=['png']) as temp_img:
		return np.array(temp_img, dtype=np.uint8)

def run_mkvpropedit(*args):
	cmd = [MKVPROPEDIT_PATH, *args]
	p = subprocess.run(cmd, check=True)

def fix_images(ds: PGSDisplaySet, ds_palette: np.ndarray[any]) -> PGSDisplaySet:
	try:
		for ods in ds.ods.values():
			# get the image
			with ods.get_image(ds_palette) as temp_img:
				with temp_img.convert('RGBA') as temp_img2:
					img_data = np.array(temp_img2, dtype=np.uint8)

					with BytesIO() as buf:
						temp_img.save(buf, format='png')
						buf.seek(0)
						img_file_bytes = buf.read()

			if FIX_IMAGES_WITH_FFMPEG_AND_MAGIC:
				# get ymax
				ymax_cmd = ['-i',"-",'-vf','format=rgba,scale=out_range=full,signalstats,metadata=print:file=-','-f','null','-']
				ffmpeg_metadata = run_ffmpeg(*ymax_cmd, pipe_in=img_file_bytes)
				ymax = int(re.search(r'(?<=signalstats.YMAX=)[0-9]+(?=\s*(?:[\r\n]|\Z|$))',ffmpeg_metadata.decode())[0])

				# pad, fix the color range and map luminance to alpha
				# use -filter_complex because -vf shits the bed and makes the image red for some reason
				alpha_cutoff = f'if(lt(alpha(X,Y),{255//10}),0,p(X,Y))'
				filters = ','.join([
					"[0]scale=out_range=full,format=rgba[asd]",
					"[asd]pad=20+iw:20+ih:ow/2:oh/2:color=#00000000[asd]",
					f"[asd]geq=r='255':g='255':b='255':a='lerp(0,255,max(max(r(X,Y),g(X,Y)),b(X,Y))/{ymax})'[asd]",
					f"[asd]geq=r='p(X,Y)':g='p(X,Y)':b='p(X,Y)':a='{alpha_cutoff}'[asd]",
				])
				cmd = [FFMPEG_PATH,'-hide_banner','-v','quiet','-i','-','-filter_complex',filters,'-map','[asd]','-c','png','-f','rawvideo','-']
				p = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, input=img_file_bytes)

				
				# the next 3 operations could probably be done all in a single command of image magick
				# but right now i just spent an hour trying to look up how the fuck you multiply a channel by an other using image magick,
				# and apparently that's too eldritch for the wizzard 

				# create black border around image and quantize the image
				cmd = [MAGICK_PATH,'-','-write', 'mpr:in','-resize','200%','-channel','A','-morphology','dilate','disk:10','+channel','-fill','black','-colorize','100','-resize','50%','mpr:in','-composite','-colors','128', '-dither', 'None','png32:-']
				p = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, input=p.stdout)

				# make pixels that are below a certain alpha black and transparent
				filters = ','.join([
					"[0]scale=out_range=full,format=rgba[asd]",
					f"[asd]geq=r='{alpha_cutoff}':g='{alpha_cutoff}':b='{alpha_cutoff}':a='{alpha_cutoff}'[asd]",
				])
				cmd = [FFMPEG_PATH,'-hide_banner','-v','quiet','-i','-','-filter_complex',filters,'-map','[asd]','-c','png','-f','rawvideo','-']
				p = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, input=p.stdout)
				
				# trim the image
				cmd = [MAGICK_PATH, '-', '-channel', 'alpha', '-trim', 'png32:-']
				p = subprocess.run(cmd, stdout=subprocess.PIPE, check=True, input=p.stdout)
				
				# stonks
				with BytesIO(p.stdout) as img_buff, Image.open(img_buff, formats=['png']) as temp_img:
					img_data = np.array(temp_img, dtype=np.uint8)
			else:
				# update image to full white using luminance as alpha channel
				# make all transparent pixels full black
				img_data[img_data[:,:,3] == 0] = 0
				
				# set alpha to max of colors
				img_data[:,:,3] = img_data[:,:,:3].max(axis=2)

				# re-lerp alpha if it's not reaching max anymore
				if 200 < (ymax := int(img_data[:,:,:3].max())) < 0xff:
					img_data = img_data.astype(np.uint16)
					img_data[:,:,3] *= 255
					img_data[:,:,3] //= ymax
					img_data = img_data.astype(np.uint8)

				# make pixels everything white
				img_data[:,:,:3] = 0xff

				# make pixels that are below a certain alpha black and transparent
				img_data[img_data[:,:,3] < 20,:] = 0

				# pad image to make new stroke not overflow
				img_data = np.pad(img_data, [(5,5),(5,5),(0,0)], mode='constant', constant_values=0)

				# add the border, quantize the image
				img_data = run_magick(img_data, '-write mpr:in -resize 200% -channel A -morphology dilate disk:10 +channel -fill black -colorize 100 -resize 50% mpr:in -composite -colors 128 -dither None')
				
				# make pixels that are below a certain alpha black and transparent
				img_data[img_data[:,:,3] <= 255//10,:] = 0

				# trim the image
				img_data = np.trim_zeros(img_data, 'fb', axis=0)
				img_data = np.trim_zeros(img_data, 'fb', axis=1)
			
			
			ods.w_diff = img_data.shape[1] - ods.width
			ods.h_diff = img_data.shape[0] - ods.height
			ods.decoded_data = img_data

		#print(f'display set {ds.id} completed')

		return ds
	except Exception as e:
		print_err(f'[fix_images_error] {traceback.format_exc()}')
		raise
		
def fix_palette(ds: PGSDisplaySet):
	try:
		# full transparency should always be the first thing to appear in the palette
		final_palette_bytes = b'\x00'*4
		final_palette_lookup = {
			(0,0,0,0): 0
		}

		for ods in ds.ods.values():
			# create the pallete thing for PIL and make the lookup table for the conversion
			img_data = ods.decoded_data
			temp_palette = np.unique(img_data.reshape(-1,4), axis=0)
			for p in [(*p,) for p in temp_palette.tolist()]:
				if p not in final_palette_lookup:
					final_palette_lookup[p] = len(final_palette_lookup)
					final_palette_bytes += bytes(p)
			
			# turn the img data into an index list
			img_data = img_data.tolist()
			for line in img_data:
				for i,p in enumerate(line):
					line[i] = final_palette_lookup[(*p,)]
			img_data = np.array(img_data, dtype=np.uint8)

			img = Image.fromarray(img_data, 'P')
			img.putpalette(final_palette_bytes, rawmode='RGBA')
			if ods.id == 0:
				pass
		
			# encode the image
			img_bytes = img.tobytes()
			img_bytes_lines= [img_bytes[i * img.width: (i+1) * img.width] for i in range(img.height)]
			ods.rle_data = encode_pgs_rle(img_bytes_lines)
			ods.width = img.width
			ods.height = img.height

		# update the palette definition
		pds_palettes: list[PDSPalette] = []
		for p,i in final_palette_lookup.items():
			pds_palettes.append(pil_color_to_pds_palette(p, i))
		ds.pcs.palette_id = 0
		ds.pcs.is_palette_only_update = False
		ds.pds = {0: PDSSegment(ds.pcs.pts, ds.pcs.dts, ds.pcs.palette_id, 1, pds_palettes)}

		return ds
	except:
		print_err(f'[fix_images_error] {traceback.format_exc()}')
		raise

def fix_sub(sub_to_fix: SubToFix):
	pgs_file = PGSParser.read_from_bytes(sub_to_fix.data)
	
	with multiprocessing.Pool() as pool:
		results: list[multiprocessing.pool.ApplyResult] = []
		context = PGSContext()
		for ds in pgs_file.display_sets:
			context.update(ds)
			if ds.ods:
				palette = segment_to_pil(context.palettes[ds.pcs.palette_id])
				results.append(pool.apply_async(fix_images, args=[ds, palette]))
		for r in results:
			resp = r.get()
			pgs_file.display_sets[resp.id] = resp

		print_info(f'[fix_sub] {sub_to_fix.get_name()}: images updated')

		# replicate ODS where ever one is displayed (yes this is gonna replicate a fuck ton of data)
		# no idc, this will make subs load up faster ngl
		context = PGSContext()
		for ds in pgs_file.display_sets:
			context.update(ds)
			to_add = [obj.object_id for obj in ds.pcs.objects]
			ds.ods = {}
			for ods_id in to_add:
				new_ods = context.images[ods_id].__copy__()
				new_ods.pts = ds.pcs.pts
				new_ods.dts = ds.pcs.dts
				ds.ods[ods_id] = new_ods
				context.images[ods_id] = new_ods

			# fix the height and width of the windows
			for obj in ds.pcs.objects:
				ods = ds.ods[obj.object_id]
				w_diff = ods.w_diff
				h_diff = ods.h_diff

				obj.x = max(0, obj.x - (w_diff // 2))
				obj.y = max(0, obj.y - (h_diff // 2))
				if obj.crop != None:
					obj.crop.x = max(0, obj.crop.x - math.floor(w_diff / 2))
					obj.crop.y = max(0, obj.crop.y - math.floor(h_diff / 2))
					obj.crop.width = max(0, obj.crop.width + math.ceil(w_diff / 2))
					obj.crop.height = max(0, obj.crop.height + math.ceil(h_diff / 2))
			
				for wd in ds.wds.windows:
					if wd.id == obj.window_id:
						wd.x = max(0, wd.x - math.floor(w_diff / 2))
						wd.y = max(0, wd.y - math.floor(h_diff / 2))
						wd.width = max(0, wd.width + math.ceil(w_diff / 2))
						wd.height = max(0, wd.height + math.ceil(h_diff / 2))
			# since we are going to end up refreshing everything, make it a full update
			ds.pcs.state = PCSState.EPOCH_START

		print_info(f'[fix_sub] {sub_to_fix.get_name()}: window sizes updated')

		# fix them palettes
		results.clear()
		for ds in pgs_file.display_sets:
			if ds.ods:
				results.append(pool.apply_async(fix_palette, args=[ds]))
		for r in results:
			resp = r.get()
			pgs_file.display_sets[resp.id] = resp

		pool.close()
		pool.join()

	# update start and set the data on the response container
	sub_to_fix.start = str(pgs_file.display_sets[0].pcs.pts / 90_000)
	sub_to_fix.data = pgs_file.write()

	print_info(f'[fix_sub] {sub_to_fix.get_name()}: complete')

def uniquify_file_name(out_dir: str, name: str) -> str:
	out_path = path.join(out_dir, name)
	if path.exists(out_path):
		(path_and_name, ext) = path.splitext(out_path)
		i = 0
		while i := i + 1:
			out_path = f'{path_and_name} ({i}){ext}'
			if not path.exists(out_path):
				break
	return out_path

def fix_file(original_file_path):
	# gotta remux it first or else ffmpeg shits the bed for some reason
	# yes even if you tell ffmpeg it's an mkv video, ffmpeg is being the big dumb
	original_file_contents = run_ffmpeg('-i', original_file_path, '-map','0', '-c', 'copy', '-f', 'matroska', '-')
	ffprobe_streams = FFProbe(file_name=original_file_path, ffprobe_path=FFPROBE_PATH)['streams']
	subs_to_fix: list[SubToFix] = []
	for stream in ffprobe_streams:
		# we are only working with the pgs sub streams
		if stream['codec_name'] != 'hdmv_pgs_subtitle':
			continue

		stream_index = stream['index']
		# extract the sub file from the mkv
		sub_data = run_ffmpeg('-i', '-', '-map',f'0:{stream_index}','-c','copy', '-f', 'sup', '-', pipe_in=original_file_contents)
		
		# copy dispositions
		
		name = None
		if 'tags' in stream and 'title' in stream['tags']:
			name = stream['tags']['title']

		subs_to_fix.append(
			SubToFix(
				input_index = len(subs_to_fix) + 1,
				original_stream_index = stream_index,
				name = name,
				start = 0,
				data = sub_data,
				temp_path = path.join('.', 'temp', f'{stream_index}.sup'),
			)
		)
	
	# ensure temp dir exists
	if not path.exists(TEMP_DIR):
		os.makedirs(TEMP_DIR)
	
	# add sub inputs
	for sub in subs_to_fix:
		fix_sub(sub)
		PGSParser.read_from_bytes(sub.data)
		# save the file temporarely because windows can't pipe right or something
		with open(sub.temp_path, 'wb') as f:
			f.write(sub.data)
	

	# build the ffmpeg command to remux everything in the right way
	ffmpeg_args = ['-y','-i', original_file_path]
	for sub in subs_to_fix:
		ffmpeg_args.extend(('-itsoffset', sub.start, '-i', sub.temp_path))
	
	# map the streams
	for stream in ffprobe_streams:
		stream_index = stream['index']
		if stream['codec_name'] != 'hdmv_pgs_subtitle':
			ffmpeg_args.extend(('-map', f'0:{stream_index}'))
		else:
			sub = [sub for sub in subs_to_fix if sub.original_stream_index == stream_index][0]
			ffmpeg_args.extend(('-map', f'{sub.input_index}:s:0'))

	
	ffmpeg_args.extend(('-c', 'copy'))

	# copy over the old metadata and disposition
	for stream in ffprobe_streams:
		stream_index = stream['index']
		
		#copy over dispositions to prevent ffmpeg from setting defaults
		dispositions = [k for (k,v) in stream['disposition'].items() if v]
		dispositions = ''.join(dispositions) if dispositions else '0'
		# default gonna need to be redone because ffmpeg forces default even with disp 0 for some reason
		ffmpeg_args.extend((f'-disposition:{stream_index}', dispositions))
		
		# don't copy meta unless we are fixing a sub
		if stream['codec_name'] != 'hdmv_pgs_subtitle':
			continue

		# copy meta
		if 'tags' in stream:
			for k,v in stream['tags'].items():
				if k != 'DURATION':
					ffmpeg_args.extend((f'-metadata:s:{stream_index}',f"{k}={v}"))

	# save to a new file becasue safety + ffmpeg doesn't like writing to a file it's reading from 
	out_file_path = uniquify_file_name(path.join('.', 'out'), path.basename(original_file_path))
	ffmpeg_args.append(out_file_path)

	# ensure out dir exists	
	if not path.exists(OUT_DIR):
		os.makedirs(OUT_DIR)

	# merge everyting via ffmpeg
	run_ffmpeg(*ffmpeg_args)

	# use mkv edit to fix default dispositions
	mkv_propedit_args = [out_file_path]
	for stream in ffprobe_streams:
		if 'disposition' in stream and 'default' in stream['disposition']:
			is_default = stream['disposition']['default'] 
			stream_index = stream['index']
			mkv_propedit_args.extend(('--edit', f'track:{stream_index + 1}', '--set', f'flag-default={is_default}'))
	run_mkvpropedit(*mkv_propedit_args)

if __name__ == '__main__':
	fix_file(path.join('','sample','sample.mkv'))