"""
pyrtl433net -- network of rtl_433 devices

To run as the server, supply the --server switch and provide a configuration file:
	python3 -m pyrtl433net --server server.cfg --handler myhandler

==== server.cfg ====
[server]
interface = 0.0.0.0
port = 4333

[rtl433]
frequency = 915M
metadata = level
fsk = minimax

[rtl433.decoders]
WS85 = m=FSK_PCM,s=58,l=58,r=2048,preamble=aa2dd4
==== server.cfg ====

The --handler is a import'able python object with an rtl433_handler(server,client,packet) function to handle the incoming packets.


To run as the client, supply the --client switch with the server and port to connect to:
	python3 -m pyrtl433net --client SERVER:[HOST]

The only configuration the client takes is the interface and port of the server,
 no rtl_433 configuration is provided at invocation but pulled from the server.
"""

import argparse
import configparser
import importlib
import inspect
import json
import socket
import socketserver
import sys

DEFAULT_PORT = 4333
DEFAULT_BIN = 'rtl_433'

__all__ = ['parse_args', 'server', 'client']

def parse_args(args=None):
	"""
	Given a list of args @args, parse them and return the parser object.
	If @args is None, then it will pull from the sys.argv.
	"""

	p = argparse.ArgumentParser(
		prog="pyrtl433net",
		description="Run multiple instances to work a network of rtl_433 software defined radios and feed received data to a single server"
	)
	p.add_argument('--server', action="store", nargs=1, metavar="CONFIG_FILE", help="Run as the server using the specified config file")
	p.add_argument('--client', action="store", nargs=1, metavar="IP:[PORT]", help="Run as the clinet connecting to the specified server")
	p.add_argument('--rtl433', action="store", nargs=1, metavar="ARG", default=DEFAULT_BIN, help="Override the rtl_433 binary name, can specify the path too")
	p.add_argument('--dryrun', action="store_true", default=False, help="Dry run for the client, meaning this will formulate the rtl_433 command, print it out, and quit. This does require the server to be running to get the configuration. For the server, this will parse the configuration, print it out, and quit without binding the server socket.")
	p.add_argument('--handler', action="store", nargs=1, metavar="PY", help="Python handler for packets, this is fed to importlib.import_module and rtl433_handler(server, client, packet) is called for each packet received")

	args = p.parse_args(args)
	if not args.server and not args.client:
		p.print_help()
		sys.exit(-1)
	return args

class server:
	"""
	UDP server that listens for packets from the clients.
	Transport layer is JSON encoded at UTF-8.

	Requests from clients contain and 'cmd' key:
		getconfig returns the configuration parsed from the server.cfg
		packet is a radio packet received at the client end

	Returned is object of
		ret=ok if the packet was received
		ret=error if there was an error, and the error key is set with something meaningful
		ret=exception if there was an exception of some kind with exception key as a two tuple (exception type name, exception string value)
	"""

	class _MyUDPHandler(socketserver.BaseRequestHandler):
		"""
		Handler class for a UDP server.
		"""

		def handle(self):
			# request is a 2 tuple of (data,socket)
			data = self.request[0]
			sock = self.request[1]
			try:
				# Expect that the data is a JSON object, handle, and return a serialized JSON ojbect
				j = json.loads(data)
				ret = self._handle(j)
				ret = json.dumps(ret)
			except Exception as e:
				return {"ret": "exception", "exception": (str(type(e)), e.value)}

			# Convert return value back to JSON to ship over
			sock.sendto(ret.encode('utf-8'), self.client_address)

		def _handle(self, data):
			"""
			Actually handle the client data.
			Executing/handling commands is done here.
			"""

			if data['cmd'] == 'getconfig':
				return {"ret": "ok", 'config': self.server._config}

			elif data['cmd'] == 'packet':
				self.server._handler.rtl433_handler(self.server, self.client_address, data['packet'])
				return {"ret": "ok"}

			else:
				print("Unknown command")
				print(data)
				return {"ret": 'error', "error": 'Unrecognized command'}

	def load(self, fname):
		"""
		From @fname, load it in as a configuration file for the server.
		Expected sections:
			[server] contains interface and port to specify where to listen
			[rtl433] contains frequency, metadata, and fsk
				frequency is whatever is passed via -f to rtl_433 (eg, "915M" for 915 MHz)
				metadata is what you want to pass to -M, space-delimited list will result in multiple -M arguments
				fsk is what you want to pass to -Y for the FSK pulse detector mode, space-delimited list will result in multiple -Y arguments
			[rtl433.decoders] contains 3 possible options
				include is what decoders to include using -R, if "*" then all decoders are included
				exclude is what decoders to exclude, by default this is none
				key=value is custom generic decoders passed by -X where key is used as the decoder name and formed by "n=key,value"

		This is converted to a simple dictionary object tree and passed to the client when requested.
		"""

		c = configparser.ConfigParser()
		c.read(fname)
		if 'server' not in c.sections():
			raise ValueError("Server config missing a [server] section")

		self._iface = c.get('server', 'interface', fallback='0.0.0.0')
		self._port = c.getint('server', 'port', fallback=DEFAULT_PORT)

		self._frequency = c.get('rtl433', 'frequency')
		self._metadata = c.get('rtl433', 'metadata', fallback=None)
		self._fsk = c.get('rtl433', 'fsk', fallback=None)

		# Space-delimited list of options to pass
		if len(self._metadata):
			self._metadata = [_.strip() for _ in self._metadata.split(' ')]
			self._metadata = [_ for _ in self._metadata if len(_)]

		# Space-delimited list of options to pass
		if len(self._fsk):
			self._fsk = [_.strip() for _ in self._fsk.split(' ')]
			self._fsk = [_ for _ in self._fsk if len(_)]

		self._include = c.get('rtl433.decoders', 'include', fallback='*')
		self._exclude = c.get('rtl433.decoders', 'exclude', fallback=None)
		self._customs = []
		for key in c['rtl433.decoders']:
			if key in ('include', 'exclude'): continue

			val = c['rtl433.decoders'][key]
			self._customs.append( 'n=%s,%s' % (key,val) )

		self._config = {
			'frequency': self._frequency,
			'metadata': self._metadata,
			'fsk': self._fsk,
			'decoders': {
				'include': self._include,
				'exclude': self._exclude,
				'customs': self._customs,
			},
		}

	def serve_forever(self, args):
		"""
		Basic server function to handle incoming packets from clients.
		Bind to socket, listen, and invoke _MyUDPHandler to handle the packets.
		"""

		if args.handler is None:
			raise Exception("Expect a handler to be provided with --handler")

		# Ensure the handler function is good
		hand = importlib.import_module(args.handler[0])
		fname = 'rtl433_handler'
		if fname not in dir(hand):
			raise ValueError("Imported handler object does not have a function named %s()" % fname)

		# Get function as an object
		f = hand.rtl433_handler

		# Reflect and get arguments
		fargs = inspect.getfullargspec(f)
		if len(fargs.args) != 3:
			raise ValueError("Imported handler object has rtl433_handler() but does not take 3 positional arguments: %s" % str(fargs.args))

		# Enforce argument names so they're in the right order
		if fargs.args[0] != 'server': raise ValueError("Imported handler object has rtl433_handler(%s) but first argument is not 'server'" % ",".join(fargs.args))
		if fargs.args[1] != 'client': raise ValueError("Imported handler object has rtl433_handler(%s) but second argument is not 'client'" % ",".join(fargs.args))
		if fargs.args[2] != 'packet': raise ValueError("Imported handler object has rtl433_handler(%s) but third argument is not 'packet'" % ",".join(fargs.args))

		with socketserver.UDPServer((self._iface, self._port), __class__._MyUDPHandler) as s:
			print("Listening to UDP %s:%d" % (self._iface, self._port))

			# Copy over the config
			# Access self.server._config within _MyUDPHandler.handle
			s._config = self._config
			s._handler = hand

			s.serve_forever()

class client:
	"""
	UDP client that sends packets to the server.
	Transport layer is JSON encoded at UTF-8.

	rtl_433 configuration is pulled from the server over this protocol too.
	"""

	def __init__(self, hostport):
		if ':' in hostport:
			host,port = hostport.split(':',1)
			port = int(port)
		else:
			host = hostport
			port = DEFAULT_PORT

		self._host = host
		self._port = port

	def __enter__(self):
		# Not much a context since UDP is stateless, but in case it is switched to TCP then already using a context manager is easy
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		return False

	def write(self, data):
		"""
		Write a request and read the response.
		@data is a python object that is serialized as JSON and UTF-8 encoded.
		The response is likewise assumed to be UTF-8 encoded JSON and returned as a python object.
		"""
		print("Sending to %s:%d" % (self._host,self._port))

		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.settimeout(1.0)
		s.sendto(json.dumps(data).encode('utf-8'), (self._host,self._port))
		ret = s.recv(1024*10)
		ret = ret.decode('utf-8')
		ret = json.loads(ret)
		return ret

	def getconfig(self):
		"""
		Poll the server for configuration information.
		"""

		req = {
			'cmd': 'getconfig',
		}
		ret = self.write(req)
		if 'error' in ret:
			raise Exception("Response error: %s" % ret['error'])
		elif 'exception' in ret:
			raise Exception("Server exception: %s(%s)" % ret['exception'])

		return ret['config']

	def sendpacket(self, packet):
		"""
		Send a radio packet to the server.
		"""

		req = {
			'cmd': 'packet',
			'packet': packet,
		}
		ret = self.write(req)
		if 'error' in ret:
			raise Exception("Response error: %s" % ret['error'])
		elif 'exception' in ret:
			raise Exception("Server exception: %s(%s)" % ret['exception'])

		# Nothing back from the server
		return None

	@staticmethod
	def config_to_args(cfg):
		"""
		Convert a server.cfg INI style configuration file into python dictionary object tree.
		"""

		opts = []

		if 'frequency' in cfg:
			opts.append('-f')
			opts.append(cfg['frequency'])
		if 'metadata' in cfg:
			for m in cfg['metadata']:
				opts.append('-M')
				opts.append(m)
		if 'fsk' in cfg:
			for y in cfg['fsk']:
				opts.append('-Y')
				opts.append(y)

		# All decoders includeed by default
		# Otherwise "-R X" to include and "-R -X" to exclude
		if cfg['decoders']['include'] == '*':
			pass
		else:
			for part in cfg['decoders']['include'].split(' '):
				part = part.strip()
				if len(part):
					opts.append('-R')
					opts.append(part)

		if cfg['decoders']['exclude'] is None:
			pass
		else:
			for part in cfg['decoders']['exclude'].split(' '):
				part = part.strip()
				if len(part):
					opts.append('-R')
					opts.append('-' + part)

		# Custom decocers
		for k in cfg['decoders']['customs']:
			opts.append('-X')
			opts.append(k)

		return opts

