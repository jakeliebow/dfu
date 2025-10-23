## Description
This is a package manager runner compatible with npm and yarn that scans all packages for version numbers including down stream dependencies and blocks recently updated packages.
The basic idea here is that npm packages are now frequently compromised, uploaded, and downloaded by a wide variety of tools and systems before being caught over the course of a day or so. 
As a result npm is still laregely a safe and secure tool, however recently updated packages are not and should be given time to be scanned and used by the broader npm community.

## Warning
Becareful using yarn as it does not yet support https for proxies, leaving you vulnerable to a MITM attack


## Installation
Install your package manager of choice
Install python 3.12
Run the build script for build and installation of executable dfu

## Usage

1) Start the standalone proxy server (writes configs into `./proxy_files`):

```bash
python main.py --host localhost --port 8080 --min-package-age-days 80
```

2) In your project (e.g., `test/`), run npm through the generated config:

```bash
cd test
npm --userconfig ../proxy_files/dfu.npmrc install express@latest
```

3) Yarn (pick the file that exists):

```bash
# Yarn 2+
yarn --rc-file ../proxy_files/dfu.yarnrc.yml install

# Yarn 1.x
yarn --use-yarnrc ../proxy_files/dfu.yarnrc install
```

Example output:
```bash
Starting proxy setup in /path/to/your/repo/proxy_files
Created confdir
Generated CA certificates
Wrote certificate files
Detected yarn version: 3
Created Yarn 2+ config: /path/to/your/repo/proxy_files/dfu.yarnrc.yml
Setting up event loop
Creating mitmproxy options: host=localhost, port=8080
Creating DumpMaster
Adding request hook
Starting mitmproxy
```

