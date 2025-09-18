## Description
This is a package manager runner compatible with npm and yarn that scans all packages for version numbers including down stream dependencies and blocks recently updated packages.
The basic idea here is that npm packages are now frequently compromised, uploaded, and downloaded by a wide variety of tools and systems before being caught over the course of a day or so. 
As a result npm is still laregely a safe and secure tool, however recently updated packages are not and should be given time to be scanned and used by the broader npm community.

## Warning
Becareful using yarn as it does not yet support https for proxies, leaving you vulnerable to a MITM attack


## Installation
Install your package manager of choice
Install python-3.13.0
Run the build script for build and installation of executable dfu

## Usage

To run the project with Python:

```bash
python main.py --project test --min-package-age-days 9999999 npm i
python main.py --project test --min-package-age-days 80 npm i express@5.1.0
python main.py --unsafe-http  --project test --min-package-age-days 14 yarn install
dfu npm i
dfu --unsafe-http yarn install

```
example output
```bash
python main.py --project test --min-package-age-days 80 npm i express@5.1.0
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

