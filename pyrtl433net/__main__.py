
import os
import socket
import subprocess
import time

import pyrtl433net

def main_server(args):
	fname = args.server[0]

	if not os.path.exists(fname):
		raise ValueError("Server config '%s' does not exist" % fname)

	s = pyrtl433net.server()
	s.load(fname)
	s.serve_forever()

def main_client(args):
	with pyrtl433net.client(args.client[0]) as cli:
		cnt = 1
		while True:
			_main_client_innerloop(cli, args, cnt)
			cnt += 1

def _main_client_innerloop(cli, args, cnt):
	try:
		cfg = cli.getconfig()
		opts = cli.config_to_args(cfg)
		opts.insert(0, args.rtl433[0])
		opts.append('-F')
		opts.append('json')
		print(opts)

		ret = subprocess.Popen(opts)
		while True:
			line = ret.stdout.readline()
			print([line])

		# Run rtl_433
		# Read packets from rtl_433
		# Send to server
		return
	except socket.timeout:
		print("Server not found %d" % cnt)
		time.sleep(1.0)

def main(args=None):
	args = pyrtl433net.parse_args(args)

	if args.server:
		main_server(args)

	elif args.client:
		main_client(args)
	
if __name__ == '__main__':
	main()

