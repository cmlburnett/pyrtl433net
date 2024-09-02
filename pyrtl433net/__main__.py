
import json
import os
import socket
import subprocess
import sys
import time

import pyrtl433net

def main_server(args):
	"""
	Invoke the server
	"""
	fname = args.server[0]

	if not os.path.exists(fname):
		raise ValueError("Server config '%s' does not exist" % fname)

	s = pyrtl433net.server()
	s.load(fname)
	if args.dryrun:
		print(s._config)
		sys.exit(0)

	s.serve_forever(args)

def main_client(args):
	"""
	Invoke the client and loop indefinitely
	"""
	with pyrtl433net.client(args.client[0]) as cli:
		cnt = 1
		while True:
			print("Connecting...")
			try:
				_main_client_innerloop(cli, args)
			except socket.timeout:
				print("Server not found %d" % cnt)
				time.sleep(1.0)

			# Iteration counter
			cnt += 1
			time.sleep(2.0)

def _main_client_innerloop(cli, args):
	"""
	Inner loop that invokes rtl_433 as a process, read the stdout from it, and send each radio packet to the server.
	"""

	cfg = cli.getconfig()
	opts = cli.config_to_args(cfg)

	# Binary goes first
	opts.insert(0, args.rtl433[0])

	# Lastly, spit out the radio packets as a JSON object
	opts.append('-F')
	opts.append('json')

	print(" ".join(opts))
	if args.dryrun:
		sys.exit(0)

	# TODO: look at stderr and use return code to interpret why rtl_433 quit
	with subprocess.Popen(opts, stdout=subprocess.PIPE) as p:
		try:
			while True:
				if p.poll() is not None:
					# Process quit, so return
					return

				line = p.stdout.readline()
				line = line.decode('utf-8')
				line = line.strip()
				if len(line):
					j = json.loads(line)

					ret = send_repeat(cli, j)
					if ret is None:
						print("Failed to received, quit reading data until new config received...")
						# Server stopped responding, fall out and reconnect to get fresh config
						return
		finally:
			# Can't return without killing the process first
			p.kill()

	return

def send_repeat(cli, dat, repeat=5):
	cnt = 0
	while cnt < repeat:
		ret = cli.sendpacket(dat)
		if ret is not None:
			return ret

		print("\tRepeat %d of %d" % (cnt, repeat))
		cnt += 1

	# Tried @repeat times
	return None

def main(args=None):
	args = pyrtl433net.parse_args(args)

	if args.server:
		main_server(args)

	elif args.client:
		main_client(args)
	
if __name__ == '__main__':
	main()

