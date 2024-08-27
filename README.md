pyrtl433net -- Network layer on top of rtl_433

rtl_433 is a C-based app that interfaces with software defined radios (SDR) such as the Nooelec USB that was used for testing with this library
  https://www.nooelec.com/store/sdr/sdr-receivers/nesdr-smart-sdr.html

This comes as a server/client combo where the clients will run rtl_433 and pipe the output to the server.
On the server you must add functionality to pipe the data to your.

# Installation

Installation is easy
```
git clone https://github.com/cmlburnett/pyrtl433net
python3 -m build
pip3 install dist/pyrtl433net-1.0.tar.gz
```

On each client, you must install rtl_433, see (https://github.com/merbanan/rtl_433/blob/master/docs/BUILDING.md)[https://github.com/merbanan/rtl_433/blob/master/docs/BUILDING.md].
Of course you must also have an SDR of some kind too.

# Use

After installation on server and client, invoke in the following way.

The server:
```
python3 -m pyrtl433net --server server.cfg --handler myhandler
```

The client:
```
python3 -m pyrtl433net --client SERVER:[PORT]
```

The server requires a configuration file to properly configure rtl_433 on the clients.

server.cfg
```
[server]
interface = 0.0.0.0
port = 4333

[rtl433]
frequency = 915M
metadata = level
fsk = minimax

[rtl433.decoders]
WS85 = m=FSK_PCM,s=58,l=58,r=2048,preamble=aa2dd4
```

The server requires some sort of python handler of the packets.
This could be a singular python file or an installed module.

myhandler.py
```
def rtl433_handler(server, client, packet):
	print(server)
	print(client)
	print(['handler', packet])
```

