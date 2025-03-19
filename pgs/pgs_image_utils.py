import numpy as np
import pgs

def segment_to_pil(pds) -> np.array:
	# pre-populate from 0 to 255
	pil_palette = np.array([(0,0,0,0)] * 256, dtype=np.uint8)
	# set values at the right indexs in case they are mixed up or something
	for p in pds.palettes:
		pil_palette[p.id] = np.array((*ycbcr_to_rgb(p.lum,  p.cb, p.cr), p.alpha), dtype=np.uint8)
	return pil_palette

def pil_color_to_pds_palette(rgba, id) -> 'pgs.PDSPalette':
	return pgs.PDSPalette(id, *rgb_to_ycbcr(*rgba[0:3]), rgba[3])

def ycbcr_to_rgb(y,cb,cr):
	r = y                         + 1.402    * (cr - 128)
	g = y - 0.344136 * (cb - 128) - 0.714136 * (cr - 128)
	b = y + 1.772    * (cb - 128)
	r = int(max(0, min(0xff, r)))
	g = int(max(0, min(0xff, g)))
	b = int(max(0, min(0xff, b)))
	return (r,g,b)

def rgb_to_ycbcr(r,g,b) -> tuple[int,int,int]:
	y  = r *  0.299   + g *  0.587   + b *  0.11400
	cb = r * -0.16874 + g * -0.33126 + b *  0.5     + 128
	cr = r *  0.5     + g * -0.41869 + b * -0.08131 + 128
	y = int(max(0, min(0xff, y)))
	cb = int(max(0, min(0xff, cb)))
	cr = int(max(0, min(0xff, cr)))
	return (y, cb, cr)