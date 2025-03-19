from PIL import Image
import numpy as np
import pgs
import logging
from os import path
from enum import IntFlag
import math

# PGS format information:
# Scorpius's blog
# https://blog.thescorpius.com/index.php/2017/07/15/presentation-graphic-stream-sup-files-bluray-subtitle-format/
# https://web.archive.org/web/20250121122806/https://blog.thescorpius.com/index.php/2017/07/15/presentation-graphic-stream-sup-files-bluray-subtitle-format/
# FFmpeg's source code
# https://git.ffmpeg.org/gitweb/ffmpeg.git/blob/1eafbf820312d45b31907e16877ae780022598c4:/libavcodec/pgssubdec.c


PGS_MAGIC_VALUE = b'PG'
"""Denotes the start of any PGS Segment"""
PGS_HEADER_LAYOUT = '2sIIBH'
PGS_HEADER_LENGTH = pgs.PGSIO.calcsize(PGS_HEADER_LAYOUT)
"""MAGIC - PTS - DTS - TYPE - SEG_LEN"""
MAX_PGS_SEGMENT_LENGTH = 0xffff



PCS_HEADER_LAYOUT = 'HHBHBBBB'
"""W - H - FPS - NUM - STATE - PALETTE-UPDATE-FLAGE - PALETTE_ID - PCS_OBJ_COUNT"""
PCS_OBJECT_LAYOUT = 'HBBHH'
"""OBJ_ID - WINDOW_ID - CROP_FLAG - X - Y"""
PCS_CROP_LAYOUT = 'HHHH'
"""X - Y - W - H"""



WDS_HEADER_LAYOUT = 'B'
"""WDS_ID"""
WDS_WINDOW_LAYOUT = 'BHHHH'
"""WINDOW_ID - X - Y - W - H"""



PDS_HEADER_LAYOUT = 'BB'
"""PDS_ID - PDS_VER"""
PDS_PALETTE_LAYOUT = 'BBBBB'
"""PALETTE_ID - Y - CR - CB - ALPHA"""



ODS_HEADER_LAYOUT = 'HBB'
"""ODS_ID - ODS_VER - SEQ_POS_FLAG"""
ODS_HEADER_LENGTH = pgs.PGSIO.calcsize(ODS_HEADER_LAYOUT)

ODS_PAYLOAD_HEADER_LAYOUT = '3sHH'
"""DATA_LEN - W - H"""
ODS_PAYLOAD_HEADER_LENGTH = pgs.PGSIO.calcsize(ODS_PAYLOAD_HEADER_LAYOUT)

MAX_ODS_DATA_FRAGMENT_LEN = MAX_PGS_SEGMENT_LENGTH - pgs.PGSIO.calcsize(ODS_HEADER_LAYOUT)
"""The maximum length that of an ODS data fragment can have."""

# END SEGMENT HAS NO DATA

class PGSSegment:
	
	pts: int
	"""4 bytes: Presentation Timestamp"""
	dts: int
	"""4 bytes: Decoding Timestamp"""

	def __init__(self, pts: int, dts: int):
		self.pts = pts
		self.dts = dts

	@staticmethod
	def read(reader: pgs.PGSIO, context: 'PGSContext') -> 'PGSSegment':
		packet_start = reader.tell()

		# parse default components
		(magic, pts, dts, segType, size) = reader.unpack(PGS_HEADER_LAYOUT)
		# check magic value
		if magic != PGS_MAGIC_VALUE:
			raise pgs.PGSParserException(f'invalid packet header @ 0x{reader.tell() - 11:x}')
		
		# check for unknown segment types
		if segType not in PGS_SEGMENT_TYPE_RESOLVER:
			raise pgs.PGSParserException(f'invalid packet header @ 0x{reader.tell() - 2:x}')
		
		expected_end = reader.tell() + size
		# parse the releavent segment type
		ret = PGS_SEGMENT_TYPE_RESOLVER[segType].read(pts, dts, size, reader, context)
		if reader.tell() != expected_end:
			raise pgs.PGSParserException(f'read too much data for packet starting @ 0x{packet_start:x}. expected to read {size} but read {reader.tell() - packet_start}')
		return ret

	def write_segment_header(self, writer: pgs.PGSIO):
		writer.write(PGS_MAGIC_VALUE)
		writer.pack('IIB', self.pts, self.dts, self.get_segment_id())
		
	def serialize(self, writer: pgs.PGSIO):
		self.write_segment_header(writer)
		if isinstance(self, ENDSegment):
			writer.pack('H', 0)
		else:
			with pgs.PGSIO() as segment_writer:
				self.write(segment_writer)
				writer.pack('H', segment_writer.tell())
				segment_writer.seek(0)
				writer.write(segment_writer.read())

	@staticmethod
	def get_segment_id() -> int:
		raise pgs.PGSParserException('failed to encode because of missing segment id')

	
	def write(self, _):
		raise pgs.PGSParserException('segment has no write function')
	
	def write(self, _):
		raise pgs.PGSParserException('segment has no read function')



# from https://git.ffmpeg.org/gitweb/ffmpeg.git/blob/1eafbf820312d45b31907e16877ae780022598c4:/libavcodec/pgssubdec.c
# state is a 2 bit field that defines pgs epoch boundaries
# 00 - Normal, previously defined objects and palettes are still valid
# 01 - Acquisition point, previous objects and palettes can be released
# 10 - Epoch start,       previous objects and palettes can be released
# 11 - Epoch continue,    previous objects and palettes can be released
# next 6 bits are reserved and therefore ignored
class PCSState(IntFlag):
    NORMAL =            0b00
    ACQUISITION_POINT = 0b01
    EPOCH_START =       0b10
    EPOCH_CONTINUE =    0b11

class PCSObjectCrop:

	x:int
	"""2 bytes: X offset from the top left pixel of the cropped object in the screen."""
	y:int
	"""2 bytes: Y offset from the top left pixel of the cropped object in the screen."""
	width: int
	"""2 bytes: Width of the cropped object in the screen."""
	height: int
	"""2 bytes: Height of the cropped object in the screen."""

	def __init__(self, x: int, y: int, width: int, height: int):
		self.x = x
		self.y = y
		self.width = width
		self.height = height

	@staticmethod
	def read(reader: pgs.PGSIO):
		return PCSObjectCrop(*reader.unpack(PCS_CROP_LAYOUT))

	def write(self, writer: pgs.PGSIO):
		writer.pack(PCS_CROP_LAYOUT, self.x, self.y, self.width, self.height)
	
class PCSObject:
	object_id: int
	"""2 bytes: ID of the ODS segment that defines the image to be shown"""
	window_id: int
	"""1 byte: Id of the WDS segment to which the image is allocated in the PCS. Up to two images may be assigned to one window."""
	# is_copped
	# """1 byte: Force display of the cropped image object. false = 0x00, true = 0x40"""
	x: int
	"""2 bytes: X offset from the top left pixel of the image on the screen."""
	y: int
	"""2 bytes: Y offset from the top left pixel of the image on the screen."""
	crop: PCSObjectCrop | None

	def __init__(self, window_id: int, object_id: int, x: int, y: int, crop: PCSObjectCrop | None = None):
		self.window_id = window_id
		self.object_id = object_id
		self.x = x
		self.y = y
		self.crop = crop

	@staticmethod
	def read(reader: pgs.PGSIO) -> 'PCSObject':
		# read data
		(object_id, window_id, is_cropped, x, y) = reader.unpack(PCS_OBJECT_LAYOUT)
		# read crop info if crop requested
		crop: PCSObjectCrop | None = None
		if is_cropped == 0x40:
			crop = PCSObjectCrop.read(reader)
		# return data
		return PCSObject(window_id, object_id, x, y, crop)
	
	def write(self, writer: pgs.PGSIO):
		crop_flag = self.crop is not None and 0x40 or 0x00
		writer.pack(PCS_OBJECT_LAYOUT, self.object_id, self.window_id, crop_flag, self.x, self.y)
		if self.crop is not None:
			self.crop.write(writer)

class PCSSegment(PGSSegment):
	
	width: int
	"""2 bytes: Video width in pixels (ex. 0x780 = 1920)"""
	height: int
	"""2 bytes: Video height in pixels (ex. 0x438 = 1080)"""
	framerate: int
	"""1 byte: Always 0x10. Can be ignored."""
	number: int
	"""2 bytes: Number of this specific composition. It is incremented by one every time a graphics update occurs."""
	state: PCSState
	"""1 byte: Type of this composition. 0x00: Normal | 0x40: Acquisition Point | 0x80: Epoch Start"""
	is_palette_only_update: bool
	"""1 byte: Indicates if this PCS describes a Palette only Display Update. 0x00: False | 0x80: True"""
	palette_id: PCSState
	"""1 byte: ID of the palette to be used in the Palette only Display Update."""
	# count: int
	#"""1 byte: Number of composition objects defined in this segment"""
	objects: list[PCSObject]

	def __init__(self, pts: int, dts: int, width: int, height: int, framerate: int, number: int, state: PCSState, is_update: int, palette_id: int, objects: list[PCSObject] | None = []):
		super().__init__(pts, dts)
		self.width = width
		self.height = height
		self.framerate = framerate
		self.number = number
		self.state = state
		self.is_palette_only_update = is_update
		self.palette_id = palette_id
		self.objects = objects

	@staticmethod
	def read(pts: int, dts: int, size: int, reader: pgs.PGSIO, context: 'PGSContext') -> 'PCSSegment':
		# read basic info
		(width, height, framerate, number, state_flag, palette_update_flag, palette_id, object_count) = reader.unpack(PCS_HEADER_LAYOUT)

		# validate obj count
		if object_count > 2:
			raise pgs.PGSParserException('PCS are limited to 2 presentation objects at once.')
		
		# parse state and update flags
		try:
			state = PCSState(state_flag)
		except ValueError:
			raise pgs.PGSParserException('unknown composition flag 0x{state_flag:02x}')

		is_update = palette_update_flag == 0x40

		# read objects
		objects: list[PCSObject] = []
		for _ in range (object_count):
			objects.append(PCSObject.read(reader))
		
		# return parsed object
		return PCSSegment(pts, dts, width, height, framerate, number, state, is_update, palette_id, objects)

	def write(self, writer: pgs.PGSIO):
		state_flag = int(self.state)
		palette_update_flag = 0x00
		if (self.is_palette_only_update):
			palette_update_flag = 0x40

		writer.pack(PCS_HEADER_LAYOUT, self.width, self.height, self.framerate, self.number, state_flag, palette_update_flag, self.palette_id, len(self.objects))
		
		for object in self.objects:
			object.write(writer)
	
	@staticmethod
	def get_segment_id() -> int:
		return 0x16



class WDSWindow:
	id: int
	"""1 byte: ID of this window"""
	x: int
	"""2 bytes: X offset from the top left pixel of the window in the screen."""
	y: int
	"""2 bytes: Y offset from the top left pixel of the window in the screen."""
	width: int
	"""2 bytes: Width of the window."""
	height: int
	"""2 bytes: Height of the window."""

	def __init__(self, id: int, x: int, y: int, width: int, height: int):
		self.id = id
		self.x = x
		self.y = y
		self.width = width
		self.height = height

	def write(self, writer: pgs.PGSIO) -> None:
		writer.pack(WDS_WINDOW_LAYOUT, self.id, self.x, self.y, self.width, self.height)

	@staticmethod
	def read(reader: pgs.PGSIO) -> 'WDSWindow':
		return WDSWindow(*reader.unpack(WDS_WINDOW_LAYOUT))

class WDSSegment(PGSSegment):
	
	#count: int
	#"""1 byte: Number of windows defined in this segment"""
	windows: list[WDSWindow]

	def __init__(self, pts:int, dts: int, windows: list[WDSWindow] | None = []):
		super().__init__(pts, dts)
		self.windows = windows or []

	@staticmethod
	def read(pts: int, dts: int, size: int, reader: pgs.PGSIO, context: 'PGSContext') -> 'WDSSegment':
		# check size
		if (size - 1) % 9 != 0:
			raise pgs.PGSParserException(f'invalid WDS segment length {size} @ 0x{reader.tell() - 2:x}')
	
		# parse windows
		(window_count,) = reader.unpack(WDS_HEADER_LAYOUT)
		windows: list[WDSWindow] = []
		for _ in range(window_count):
			windows.append(WDSWindow.read(reader))

		# return parsed segment
		return WDSSegment(pts,dts, windows)
	

	def write(self, writer: pgs.PGSIO):
		writer.pack(WDS_HEADER_LAYOUT, len(self.windows))
		for window in self.windows:
			window.write(writer)
	
	@staticmethod
	def get_segment_id() -> int:
		return 0x17



class PDSPalette:
	
	id: int
	"""1 byte: Entry number of the palette."""
	lum: int
	"""1 byte: Luminance."""
	cr: int
	"""1 byte: Color Difference Red."""
	cb: int
	"""1 byte: Color Difference Blue."""
	alpha: int
	"""1 byte: Transparency."""
	
	def __init__(self, id: int, lum: int, cr: int, cb: int, alpha: int):
		self.id = id
		self.lum = lum
		self.cr = cr
		self.cb = cb
		self.alpha = alpha

	@staticmethod
	def read(reader: pgs.PGSIO) -> 'PDSPalette':
		(id, lum, cr, cb, alpha) = reader.unpack(PDS_PALETTE_LAYOUT)
		return PDSPalette(id, lum, cr, cb, alpha)

	def write(self, writer: pgs.PGSIO):
		writer.pack(PDS_PALETTE_LAYOUT, self.id, self.lum, self.cr, self.cb, self.alpha)

class PDSSegment(PGSSegment):
	
	id: int
	"""1 byte: ID of the palette."""
	version: int
	"""1 byte: Version of this palette within the Epoch."""
	palettes: list[PDSPalette]

	def __init__(self, pts: int, dts: int, id: int, version: int, palettes: list[PDSPalette] = []):
		super().__init__(pts, dts)
		self.id = id
		self.version = version
		self.palettes = palettes

	@staticmethod
	def read(pts: int, dts: int, size: int, reader: pgs.PGSIO, context: 'PGSContext') -> 'PDSSegment':
		# check if length is valid
		palette_count = size // 5
		if palette_count * 5 + 2 != size:
			raise pgs.PGSParserException(f'unvalid PCS segment length {size} at 0x{reader.tell() - PGS_HEADER_LENGTH}')
		# parse the headers
		(id, version) = reader.unpack(PDS_HEADER_LAYOUT)
		# parse the palettes
		palettes: list[PDSPalette] = []
		for _ in range(size // 5):
			palettes.append(PDSPalette.read(reader))
		
		return PDSSegment(pts, dts, id, version, palettes)

	def write(self, writer: pgs.PGSIO):
		writer.pack(PDS_HEADER_LAYOUT, self.id, self.version)
		for palette in self.palettes:
			palette.write(writer)

	@staticmethod
	def get_segment_id() -> int:
		return 0x14



class ODSPositionFlag(IntFlag):
	
	MIDDLE         = 0x00_000000
	LAST           = 0b01_000000
	FIRST          = 0b10_000000
	FIRST_AND_LAST = 0b11_000000

class ODSSegment(PGSSegment):
	id: int
	"""2 bytes: ID of this object."""
	version: int
	"""1 byte: Version of this object."""
	position_flag: ODSPositionFlag
	"""1 byte: If the image is split into a series of consecutive fragments, the last fragment has this flag set.
	possible values:
	0x40: Last in sequence
	0x80: First in sequence
	0xC0: First and last in sequence (0x40 | 0x80)
	"""
	# length: int
	# """3 bytes: The length of the Run-length Encoding (RLE) data buffer with the compressed image data. does not include width or length"""
	width: int
	"""2 bytes: Width of the image."""
	height: int
	"""2 bytes:	Height of the image."""
	rle_data: bytes | list[bytes]
	"""variable length:	This is the image data compressed using Run-length Encoding (RLE). The size of the data is defined in the DataLength field."""

	remaining_rle_length: int
	"""The amoutn of data that remains to be added"""
	expected_fragment_length: int
	"""The max amount of data that can be stored in a subsequent ODS segment that appends to this one. should be 0xffff - 11 after passing is complete"""

	# only used if you are planning on doing modifications to the ODS and therefore need to update palettes for new display segments and
	decoded_data: np.ndarray
	w_diff: int
	h_diff: int

	def __init__(self, pts: int, dts: int, id: int, version: int, position_flag: ODSPositionFlag, width: int, height: int, data: bytes, remaining_rle_length: int = 0):
		super().__init__(pts, dts)
		self.id = id
		self.version = version
		self.position_flag = position_flag
		self.remaining_rle_length = remaining_rle_length
		self.expected_fragment_length = len(data)
		self.width = width
		self.height = height
		self.rle_data = data
		self.decoded_data = None
		self.w_diff = None
		self.h_diff = None

	@staticmethod
	def read(pts: int, dts: int, size: int, reader: pgs.PGSIO, context: 'PGSContext') -> 'PCSSegment':
		segment_start_pos = reader.tell()
		# read the header
		(id, version, position_flag) = reader.unpack(ODS_HEADER_LAYOUT)
		position_flag = ODSPositionFlag(position_flag)
		
		# append to existing if it's not a first
		if ODSPositionFlag.FIRST not in position_flag:
			# check if the ODS we are extending exists
			previous_object = context.images.get(id)
			if previous_object is None:
				raise pgs.PGSParserException(f'ODS segment at 0x{segment_start_pos:x} tried to append to an unknown ODS segment: {id}')
			
			# check if it's already done reading
			if ODSPositionFlag.LAST in previous_object.position_flag:
				raise pgs.PGSParserException(f"ODS segment at 0x{segment_start_pos:x} tried to ppend to a segment that has already been read to completion ({id})")
			
			# the fragment data length should be what ever remains of our segment buffer
			fragment_length = size - ODS_HEADER_LENGTH
			if previous_object.remaining_rle_length < fragment_length:
				raise pgs.PGSParserException(f"ODS segment at 0x{segment_start_pos:x} has a fragment that is longer ({fragment_length}) than the remaining amount of data expected to arrive for the fragment it's extending ({previous_object.remaining_rle_length})")

			# determine the amount of data we can read
			amount_to_read = previous_object.expected_fragment_length
			if fragment_length != amount_to_read:
				# no fragment should have a longer fragment size than the expected fragment size
				if fragment_length > amount_to_read:
					raise pgs.PGSParserException(f'ODS segment at 0x{segment_start_pos:x} has a longer fragment length ({fragment_length}) than expected ({amount_to_read})')
			
				# the final fragment may be equal or smaller than the expected size
				if ODSPositionFlag.LAST not in position_flag:
					raise pgs.PGSParserException(f"ODS segment at 0x{segment_start_pos:x} has a fragment length ({fragment_length}) that differs from the expected fragment length ({amount_to_read}).")
				
				amount_to_read = fragment_length
			
			# check to make sure we read the right amount of data
			data_read = reader.read(amount_to_read)
			if len(data_read) != amount_to_read:
				raise pgs.PGSParserException(f'Failed to read expected amount of bytes ({amount_to_read}) from payload of ODS segment at 0x{segment_start_pos:x}') 

			# append to previous object
			previous_object.rle_data += data_read
			previous_object.remaining_rle_length -= len(data_read)

			# if we've reached the end check if we actually have done so and mark the ODS as finished
			if ODSPositionFlag.LAST in position_flag:
				# double safety
				if previous_object.remaining_rle_length != 0:
					raise pgs.PGSParserException(f"ODS fragment at 0x{segment_start_pos:x} should have completed the ODS #{id} but not all data has been read. {previous_object.remaining_rle_length} remaining to read.")
				# mark the segment as completed
				previous_object.position_flag = ODSPositionFlag.FIRST_AND_LAST
			
			return None
		else:
			# parse the payload length
			remaining_payload_length = int.from_bytes(reader.read(3), byteorder='big', signed=False)

			# validate values
			if remaining_payload_length < 7:
				raise pgs.PGSParserException(f'ODS segment @ 0x{segment_start_pos:x} has a payload length that is too small, min should be 7 (w + h + 1 + eol) for an empty image with no pixels.')
			
			# parse width and height
			(width, height) = reader.unpack('HH')
			if width == 0 or height == 0:
				raise pgs.PGSParserException(f"ODS segment @ 0x{segment_start_pos:x} has a size of 0 pixels ({width} x {height}).") 

			# check the rle length
			remaining_payload_length -= 4
			amount_to_read = size - (ODS_HEADER_LENGTH + ODS_PAYLOAD_HEADER_LENGTH)
			if remaining_payload_length < amount_to_read:
				raise pgs.PGSParserException(f"ODS segment @ 0x{segment_start_pos:x} has a rle length ({remaining_payload_length}) smaller than it should ({amount_to_read}).")
			
			# if this is the first and last, the rle_length should be the same as the max read 
			if ODSPositionFlag.LAST in position_flag and remaining_payload_length != amount_to_read:
				raise pgs.PGSParserException(f"ODS segment @ 0x{segment_start_pos:x} is first and last but it's rle length ({remaining_payload_length}) is greater than the maximum the segment cound contain ({amount_to_read})")

			# read the data
			data_fragment = reader.read(amount_to_read)
			remaining_payload_length -= len(data_fragment)
								   
			# if it's the last ensure we got everything
			if ODSPositionFlag.LAST in position_flag and remaining_payload_length != 0:
				logging.debug(f"failed to read all data from first and last ODS segment @ 0x{segment_start_pos}")

			# return the parsed object
			return ODSSegment(pts, dts, id, version, position_flag, width, height, data_fragment, remaining_rle_length=remaining_payload_length)

	def get_payload_bytes(self) -> bytes:
		# complete data is read as length,width,height,rle_encoded_data
		payload = pgs.PGSIO.pack_data('HH', self.width, self.height) + self.rle_data
		payload = len(payload).to_bytes(3, 'big') + payload
		return payload

	def serialize(self, writer: pgs.PGSIO):
		payload = self.get_payload_bytes()
		fragments = [payload[i:i+MAX_ODS_DATA_FRAGMENT_LEN] for i in range(0, len(payload), MAX_ODS_DATA_FRAGMENT_LEN)]
		last_index = len(fragments) - 1
		base_seg_len = writer.calcsize(ODS_HEADER_LAYOUT)
		for fragment_index, fragment_data in enumerate(fragments):
			# write basic header
			self.write_segment_header(writer)
			# write length of current segment
			seg_len = base_seg_len + len(fragment_data)
			if seg_len > MAX_PGS_SEGMENT_LENGTH:
				raise pgs.PGSParserException('tried to write an ODS segment that is too long.')
			writer.pack('H', seg_len)

			# get the position flag
			posFlag = ODSPositionFlag.MIDDLE
			if fragment_index == 0:
				posFlag |= ODSPositionFlag.FIRST 
			if fragment_index == last_index:
				posFlag |= ODSPositionFlag.LAST
				
			# write the ODS header
			writer.pack(ODS_HEADER_LAYOUT, self.id, self.version, int(posFlag))
			# write the fragment data
			writer.write(fragment_data)

	@staticmethod
	def get_segment_id() -> int:
		return 0x15

	def get_image(self, palette) -> Image.Image:
		data = pgs.decode_pgs_rle(self.rle_data)
		img = Image.frombytes('P', size=(self.width,self.height), data=b''.join(data), decoder_name='raw')
		img.putpalette(palette, rawmode='RGBA')
		return img
	
	def __copy__(self) -> 'ODSSegment':
		seg = ODSSegment(
			self.pts,
			self.dts,
			self.id,
			self.version,
			self.position_flag,
			self.width,
			self.height,
			self.rle_data,
			remaining_rle_length=0
		)
		seg.w_diff = self.w_diff
		seg.h_diff = self.h_diff
		seg.decoded_data = self.decoded_data
		return seg



class ENDSegment(PGSSegment):
	
	def __init__(self, pts, dts):
		super().__init__(pts, dts)
		
	def read(pts: int, dts: int, size: int, reader: pgs.PGSIO, context: 'PGSContext') -> 'ENDSegment':
		# the end segment should always have a length of 0
		if (size != 0):
			raise pgs.PGSParserException(f"END segment at 0x{reader.tell() - PGS_HEADER_LENGTH:x}")
		
		# return the parsed segment
		return ENDSegment(pts, dts)
	
	def write(self, _):
		pass
		
	@staticmethod
	def get_segment_id() -> int:
		return 0x80



PGS_SEGMENT_TYPE_RESOLVER: dict[int, PDSSegment|ODSSegment|PCSSegment|WDSSegment|ENDSegment] = {
	PDSSegment.get_segment_id(): PDSSegment,
	ODSSegment.get_segment_id(): ODSSegment,
	PCSSegment.get_segment_id(): PCSSegment,
	WDSSegment.get_segment_id(): WDSSegment,
	ENDSegment.get_segment_id(): ENDSegment
}

class PGSDisplaySet:
	id: int
	pcs: PCSSegment
	wds: WDSSegment
	pds: dict[int,PDSSegment]
	ods: dict[int,ODSSegment]
	end: ENDSegment

	def __init__(self, segments: list[PGSSegment], id: int):
		pcs = [s for s in segments if isinstance(s, PCSSegment)]
		wds = [s for s in segments if isinstance(s, WDSSegment)]
		end = [s for s in segments if isinstance(s, ENDSegment)]
		if len(pcs) != 1:
			raise pgs.PGSParserException(f'bad number of PCS segments in display set #{id}')
		if len(wds) != 1:
			raise pgs.PGSParserException(f'bad number of WDS segments in display set #{id}')
		if len(end) != 1:
			raise pgs.PGSParserException(f'bad number of END segments in display set #{id}')
		self.id = id
		self.pcs = pcs[0]
		self.wds = wds[0]
		self.end = end[0]
		self.pds = {}
		for s in segments:
			if isinstance(s, PDSSegment):
				self.pds[s.id] = s
		self.ods = {}
		for s in segments:
			if isinstance(s, ODSSegment):
				self.ods[s.id] = s
	
	def write(self, writer: pgs.PGSIO):
		self.pcs.serialize(writer)
		self.wds.serialize(writer)
		for s in self.pds.values():
			s.serialize(writer)
		for s in self.ods.values():
			s.serialize(writer)
		self.end.serialize(writer)


class PGSFile:
	display_sets: list[PGSDisplaySet]

	def __init__(self, segments: list[PGSSegment]):
		self.segments = []
		
		self.display_sets = []
		curr_display_set = []
		for segment in segments:
			curr_display_set.append(segment)
			if isinstance(segment, ENDSegment):
				self.display_sets.append(PGSDisplaySet(curr_display_set, len(self.display_sets)))
				curr_display_set = []

	
	def save_images(self, out_dir):
		"""
		images are dumped with file names that represent
		{ds.id}.{ods.id} - {mm}.{ss}.{fff}.png
		"""
		context = PGSContext()
		for ds in self.display_sets:
			context.update(ds)
			if len(ds.ods) > 0:
				if ds.pcs.palette_id not in context.palettes:
					raise pgs.PGSParserException(f'bad palette id found: {ds.pcs.palette_id}')
				for ods in ds.ods.values():
					mins = math.floor((ods.pts / 90000) / 60)
					secs = math.floor((ods.pts / 90000) % 60)
					ms = math.floor((ods.pts / 90) % 1000)
					save_path = path.join(out_dir, f'{ds.id}-{ods.id} - {mins:02d}.{secs:02d}.{ms:03d}.png')
					ods.get_image(pgs.segment_to_pil(context.palettes[ds.pcs.palette_id])).save(save_path)

	def write(self) -> bytes:

		with pgs.PGSIO() as writer:
			# write the segments
			for ds in self.display_sets:
				ds.write(writer)

			# output the data
			writer.seek(0)
			return writer.read()
		
class PGSContext:
	pcs: PCSSegment
	images: dict[int, ODSSegment]
	palettes: dict[int, PDSSegment]
	windows: dict[int, WDSWindow]

	def __init__(self):
		self.pcs = None
		self.images = {}
		self.palettes = {}
		self.windows = {}
	
	def begin_new_epoch(self):
		self.pcs = None
		self.images.clear()
		self.palettes.clear()
		self.windows.clear()

	def update(self, segment):
		if isinstance(segment, PGSDisplaySet):
			self.update(segment.pcs)
			self.update(segment.wds)
			for pds in segment.pds.values():
				self.update(pds)
			for ods in segment.ods.values():
				self.update(ods)
		if isinstance(segment, PCSSegment):
			if PCSState.EPOCH_START in segment.state:
				self.begin_new_epoch()
			self.pcs = segment
		elif isinstance(segment, PDSSegment):
			self.palettes[segment.id] = segment
			if len(self.palettes) > 8:
				raise pgs.PGSParserException('PGS epochs have a limit of 8 palettes.')
		elif isinstance(segment, ODSSegment):
			self.images[segment.id] = segment
			if len(self.images) > 64:
				raise pgs.PGSParserException('PGS epochs have a limit of 64 items for some reason... why is the object id a 2 byte thing then...')

class PGSParser:
		

	@staticmethod
	def read_from_bytes(bytes) -> PGSFile:
		with pgs.PGSIO(bytes, True) as reader:
			# read segments
			segments = []
			context = PGSContext()
			while reader.can_read():
				# read the segment
				ret = PGSSegment.read(reader, context)
				# append the segment if we got one (we don't get any when it's a subsequent ODS segment)
				if isinstance(ret, PGSSegment):
					context.update(ret)
					segments.append(ret)
				elif not (ret is None):
					raise pgs.PGSParserException(f'got an unexpected object type while parsing PGS segments: {str(type(ret))}')
					
			
		# the last segment should always be an end segment
		if len(segments) > 0 and not isinstance(segments[-1], ENDSegment):
			raise pgs.PGSParserException('final segment should always be an end segment')
		
		return PGSFile(segments)
	
	
		
	