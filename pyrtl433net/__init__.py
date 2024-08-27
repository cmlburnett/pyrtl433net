"""
pyrtl433net -- network of rtl_433 devices

To run as the server, supply the --server switch and provide a configuration file:
	python3 -m pyrtl433net --server server.cfg

==== server.cfg ====
[server]
port = 4333
interface = 0.0.0.0

[rtl433]
frequency = 915M
metadata = level
fsk = minimax

[rtl433.decoders]
include = *
WS85 = m=FSK_PCM,s=58,l=58,r=2048,preamble=aa2dd4
==== server.cfg ====


To run as the client, supply the --client switch with the server and port to connect to:
	python3 -m pyrtl433net --client SERVER:[HOST]

The only configuration the client takes is the interface and port of the server,
 no rtl_433 configuration is provided at invocation but pulled from the server.
"""

import argparse
import configparser
import json
import socket
import socketserver
import sys

DEFAULT_PORT = 4333
DEFAULT_BIN = 'rtl_433'

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

	args = p.parse_args(args)
	if not args.server and not args.client:
		p.print_help()
		sys.exit(-1)
	return args

class server:
	class _MyUDPHandler(socketserver.BaseRequestHandler):
		def handle(self):
			data = self.request[0].strip()
			sock = self.request[1]
			try:
				j = json.loads(data)
				ret = self._handle(j)
				ret = json.dumps(ret)
			except Exception as e:
				return {"exception": (str(type(e)), e.value)}

			# Convert return value back to JSON to ship over
			sock.sendto(ret.encode('utf-8'), self.client_address)

		def _handle(self, data):
			print(['request', self.client_address, data])
			if data['cmd'] == 'getconfig':
				return self.server._config
			elif data['cmd'] == 'packet':
				print(['packet', data['packet']])
				return {"ret": "ok"}
			else:
				print("Unknown command")
				print(data)
				return {"error": 'Unrecognized command'}

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

	def serve_forever(self):
		with socketserver.UDPServer((self._iface, self._port), __class__._MyUDPHandler) as s:
			print("Listening to UDP %s:%d" % (self._iface, self._port))

			# Copy over the config
			s._config = self._config

			s.serve_forever()

class client:
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
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		return False

	def write(self, data):
		print("Sending to %s:%d" % (self._host,self._port))

		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.settimeout(1.0)
		s.sendto(json.dumps(data).encode('utf-8'), (self._host,self._port))
		ret = s.recv(1024)
		ret = ret.decode('utf-8')
		ret = json.loads(ret)
		return ret

	def getconfig(self):
		req = {
			'cmd': 'getconfig',
		}
		ret = self.write(req)
		if 'error' in ret:
			raise Exception("Response error: %s" % ret['error'])
		elif 'exception' in ret:
			raise Exception("Server exception: %s(%s)" % ret['exception'])

		return ret

	def sendpacket(self, packet):
		req = {
			'cmd': 'packet',
			'packet': packet,
		}
		ret = self.write(req)
		if 'error' in ret:
			raise Exception("Response error: %s" % ret['error'])
		elif 'exception' in ret:
			raise Exception("Server exception: %s(%s)" % ret['exception'])

		return ret


	@staticmethod
	def config_to_args(cfg):
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

