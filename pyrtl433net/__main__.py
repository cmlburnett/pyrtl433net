
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

	s.serve_forever()

def main_client(args):
	"""
	Invoke the client and loop indefinitely
	"""
	with pyrtl433net.client(args.client[0]) as cli:
		cnt = 1
		while True:
			try:
				_main_client_innerloop(cli, args)
			except socket.timeout:
				print("Server not found %d" % cnt)
				time.sleep(1.0)

			# Iteration counter
			cnt += 1
			time.sleep(1.0)

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


	if args.dryrun:
		print(" ".join(opts))
		sys.exit(0)

	# TODO: look at stderr and use return code to interpret why rtl_433 quit
	with subprocess.Popen(opts, stdout=subprocess.PIPE) as p:
		while True:
			if p.poll() is not None:
				print(p.returncode)
				return

			line = p.stdout.readline()
			line = line.decode('utf-8')
			line = line.strip()
			if len(line):
				j = json.loads(line)
				print(j)
				cli.sendpacket(j)

	return

def main(args=None):
	args = pyrtl433net.parse_args(args)

	if args.server:
		main_server(args)

	elif args.client:
		main_client(args)
	
if __name__ == '__main__':
	main()

