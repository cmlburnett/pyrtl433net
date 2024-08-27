
import os
import socket
import time

import pyrtl433net

def main(args=None):
	args = pyrtl433net.parse_args(args)

	if args.server:
		fname = args.server[0]

		if not os.path.exists(fname):
			raise ValueError("Server config '%s' does not exist" % fname)

		s = pyrtl433net.server()
		s.load(fname)
		s.serve_forever()

	elif args.client:
		with pyrtl433net.client(args.client[0]) as cli:
			cnt = 1
			while True:
				try:
					cfg = cli.getconfig()
					print(cfg)
					# Config @cfg to rtl_433 arguments
					# Run rtl_433
					# Read packets from rtl_433
					# Send to server
					break
				except socket.timeout:
					print("Server not found %d" % cnt)
					time.sleep(1.0)
					cnt += 1
	
if __name__ == '__main__':
	main()

