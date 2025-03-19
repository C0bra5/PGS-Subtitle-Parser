import pgs
from io import BytesIO
import io
import struct
import typing

class PGSIO:
	__readonly: bool
	__length: int
	__buffer: BytesIO

	def __init__(self, initial_bytes:bytes|None = None, is_readonly:bool = False):
		self.__length = len(initial_bytes) if initial_bytes else 0
		self.__readonly = is_readonly
		self.__buffer = BytesIO(initial_bytes= initial_bytes)
		self.__buffer.seek(0)

	def __enter__(self) -> 'PGSIO':
		if (self.__buffer.closed):
			raise BufferError('buffer was already closed')
		return self
	
	def __exit__(self, exec_type, exec_value, traceback):
		self.__buffer.__exit__(exec_type, exec_value, traceback)
		self.close()

	def __len__(self) -> int:
		return self.__length

	def tell(self) -> int:
		return self.__buffer.tell()

	def seek(self, offset, whence: int = io.SEEK_SET) -> int:
		return self.__buffer.seek(offset, whence)

	def close(self):
		if not self.__buffer.closed:
			self.__buffer.close()

	@staticmethod
	def calcsize(fmt):
		return struct.calcsize('>' + fmt)

	def unpack(self, fmt:str) -> tuple[typing.Any, ...]:
		fmt = '>' + fmt
		# calculate the expected size and read the data
		size = struct.calcsize(fmt)
		buf = self.read(size)
		
		# return parsed data
		return struct.unpack(fmt, buf)

	def read(self, size: int | None = None) -> bytes:
		# default arg to -1
		size = -1 if not isinstance(size, int) or size < 0 else size
		
		# since we always know what we are reading we should never do a 0 len read
		if size == 0:
			raise pgs.PGSIOException('We should never be doing a 0 len read.')
		
		# if we are reading while at the end of the buffer something went wrong
		if not self.can_read(size):
			raise pgs.PGSIOException('Tried to read past end of buffer.')
		
		data = self.__buffer.read(size)
		# we should never do a 0 len read so if we get nothing assume we reached an expected EOF
		if len(data) == 0:
			raise pgs.PGSIOException('Unnexpected EOF')
		
		# we should always know the length of the data we are reading
		if size != -1 and len(data) != size:
			raise pgs.PGSIOException("read data wasn't of expected length.")
		
		return data

	def can_read(self, size: int | None = None) -> bool:
		# default arg to 1 and set a min value of 1 since 0 len reads should never happen
		size = 1 if (not isinstance(size, int)) or size < 1 else size
		return (self.__buffer.tell() + size) <= self.__length

	
	@staticmethod
	def pack_data(fmt:str, *args) -> bytes:
		return struct.pack('>' + fmt, *args)

	def pack(self, fmt:str , *args) -> int:
		return self.write(PGSIO.pack_data(fmt, *args))
			
	def write(self, buffer: bytes) -> int:
		# check args
		if not isinstance(buffer, bytes):
			raise pgs.PGSIOException('attempted to write something other than bytes.')

		# check write lock
		if self.__readonly:
			raise pgs.PGSIOException('buffer is non writable.')

		#write
		written = self.__buffer.write(buffer)

		# check new pos to make sure something funky didn't happen
		new_pos = self.__buffer.tell()
		if new_pos < 0:
			raise pgs.PGSIOException('buffer pos should never be negative.')

		# update length
		if self.__length < new_pos:
			self.__length = new_pos

		return written



	
