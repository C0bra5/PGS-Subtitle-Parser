import unittest
from pgs import ycbcr_to_rgb, rgb_to_ycbcr
import numpy as np

class TestImageUtils(unittest.TestCase):


	def test_rgba_to_ycbcra_valid_values_np_conv(self):
		for y in range(256):
			for cb in range(256):
				for cr in range(256):
					ycbcr_to_rgb(y, cb, cr)
	
	def test_ycbcra_to_rgba_valid_values_np_conv(self):
		for r in range(256):
			for g in range(256):
				for b in range(256):
					np.array([rgb_to_ycbcr(r, g, b)], dtype=np.uint8)