pyrtl433net -- Network layer on top of rtl_433

rtl_433 is a C-based app that interfaces with software defined radios (SDR) such as the Nooelec USB that was used for testing with this library
  https://www.nooelec.com/store/sdr/sdr-receivers/nesdr-smart-sdr.html

This comes as a server/client combo where the clients will run rtl_433 and pipe the output to the server.
On the server you must add functionality to pipe the data to whatever you want to use to actually process the data.

Essentially, this is a IP/UDP transport and aggregator for SDR's.
Go a step further and run a client in a remote location and tunnel the IP stream over a VPN if you want.

# Motivation
The problem being solved is the need to have multiple SDR's around the house to receive sensors distributed around the house.
Due to walls, dirt, etc not all sensors can be within range of a single radio.
This, thus, poses a logistic problem of having a pool of sensors and need for multiple radios that WILL have overlap.
One way to solve this is to filter sensors on each radio, another way is to pool all packets to a single location and deal with duplicate packets.

A Raspberry Pi (either a 3/4/5/etc or a Pi Zero W or whatever) using a USB-based SDR is in the range of $50-75 so having a few of these to adequately cover all sensors is doable.

This would also permit large area coverage provided you have ethernet or wifi coverage (ie, a shed that is 300 yards away but has point-to-point wifi bridge) without having to have anything special with the ISM-banded sensors.

# Installation

Installation is easy
```
git clone https://github.com/cmlburnett/pyrtl433net
python3 -m build
pip3 install dist/pyrtl433net-1.0.tar.gz
```

On each client, you must install rtl_433, see [https://github.com/merbanan/rtl_433/blob/master/docs/BUILDING.md].
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

> [!NOTE]
> interface is 0.0.0.0 by default and standard port is 4333 (a play on 433 in rtl_433).
> The other parameters are also not required, if not provided then no options will be generated to rtl_433 so you will get its default behavior.

The server requires some sort of python handler of the packets.
This could be a singular python file or an installed module.

myhandler.py
```
def rtl433_handler(server, client, packet):
	print(server)
	print(client)
	print(['handler', packet])
```

> [!NOTE]
> The function must be exactly as shown with the function name, three positional parameters, and their names.
> Anything else is not accepted.
> Return values are ignored.

The server parameter is the server object instance itself.
The client parameter is the (IP,PORT) tuple.
The packet parameter is the JSON object given to pyrtl433net by rtl_433 output plus any metadata you have injected with rtl433.metadata config options.

For example, a packet from my Ecowitt WS85 wind/rain sensor and an Ecowitt WH51 soil moisture sensor:
```
{'time': '2024-08-27 10:17:45', 'model': 'ws85', 'count': 1, 'num_rows': 1, 'rows': [{'len': 258, 'data': '850029659382c00a590c3fff6000010001372e01ffdffd00006b3bde000000000'}], 'codes': ['{258}850029659382c00a590c3fff6000010001372e01ffdffd00006b3bde000000000'], 'mod': 'FSK', 'freq1': 914.953, 'freq2': 915.034, 'rssi': -9.266, 'snr': 14.127, 'noise': -23.394}
{'time': '2024-08-27 11:29:44', 'model': 'Fineoffset-WH51', 'id': '0e1f92', 'battery_ok': 1.0, 'battery_mV': 1600, 'moisture': 42, 'boost': 0, 'ad_raw': 229, 'mic': 'CRC', 'mod': 'FSK', 'freq1': 914.957, 'freq2': 915.029, 'rssi': -0.114, 'snr': 23.835, 'noise': -23.949}
```
Note that the WS85 is not currently recognized by the rtl_433 decoders and is raw data as described by the custom decoder in the server.cfg.

# Module use comments
The purpose of this python module is to be able to deploy multiple SDR's in an area and push all received radio packets to a central location for processing.
This means the server should be able to handle receiving duplicate packets from multiple radios and do so gracefully.
This also means the server is the point of filtration.
This filtering could be done through include/exclude decoders, or on the server by discarding based on packet model.

The configuration is stored on the server, so that all clients are configured the same way.
There is no mechanism to set up clients with different configurations (mostly because I don't see the use case for this capability).

At this time, if the configuration is changed, the server needs to be shut down and restarted.
Additionally, the clients need to time out (1 second) so that they reconnect and pull the configuration from the server again.
Future modification will be updating the clients that the config changed so they re-getconfig without restarting.

# Handler implementation
The packet handler is defined above.
What the function does with the packet is entirely up to you.
- Log it to a database
- Filter out sensors and send as MQTT messages
- Send Push or SMS notifications based on data received
- Throttle packets so sensors that update too often are restricted
- Tag each packet with a location, and push multiple locations into a single center

Please note that this server model does not use threads or anything fancy, so the time spent in the handler WILL make other clients wait.
So if your handler is not deterministic and not speedy, you may experience dropped packets.
Highly recommend an intermediary log of some sort if the ultimate data sink is sporadic, buggy, or can take time.

