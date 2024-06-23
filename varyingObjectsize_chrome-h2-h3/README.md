## Load website with n * 500 kbyte objects using Chromedriver and measure timings using ResourceTiming

### Setup

Client:

- Install Chrome
- `python3 -m pip install selenium webdriver_manager`

QUIC or TCP Webserver:

- `0k.html`, `500k.html`, ..., `10000k.html`
- `for i in echo {00..19}; do cp html/500k.png html/500k${i}.png; done`


### Run

- TCP:  `vosweb.py --tcp  myServer.com iterations`
- QUIC: `vosweb.py --quic myServer.com:4443 iterations`
