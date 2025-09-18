Depends on yarn or npm as this is not a self sufficient package manager.

Built with python-3.13.0

## Installation

Run the build script for build and installation of executable dfu

## Usage

To run the project with Python:

```bash
python main.py --project test --min-package-age 9999999 npm i
python main.py --project test --min-package-age 80 npm i express@5.1.0
dfu npm i
dfu yarn install

```
example output
```bash
python main.py --project test --min-package-age 80 npm i express@5.1.0
Starting proxy setup in /tmp/mitm_orch_5f1vkkkn
Created confdir
Generated CA certificates
Wrote certificate files
Detected yarn version: None
Created Yarn 2+ config: /tmp/mitm_orch_5f1vkkkn/yarn_temp.yarnrc.yml
Setting up event loop
Creating mitmproxy options: host=localhost, port=8080
Creating DumpMaster
Waiting for proxy at localhost:8080
Adding request hook
Starting mitmproxy
Proxy is ready!
⠙Proxy error detected: Package blocked: Package path-to-regexp version 8.3.0 was modified less than 80 days ago.


Or use the DFU (Default) option.
```

