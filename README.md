## Webrecorder Browserkube

This repository contains an experimental, Kubernetes-native Webrecorder remote browser orchestration system.

The system support several use cases:
- Running browsers as demanded by the user, with VNC, shutting down after fixed amount of time or when user closes connection.
- Running browsers controlled by a driver container, which shuts down the browser when done.
- Headless browser or 'headful', with or without VNC.
- Downloading a browser profile to use for all URLs or certain URLs.

This repository provides an extensible set of containers, and a helm chart installable from: [https://webrecorder.github.io/browserkube/charts](https://webrecorder.github.io/browserkube/charts)

Requirements:
- A kubernetes cluster, accessible via `kubectl`

- Helm 3 installed.


Optional:
- For Browser Profiles: S3-compatible block storage (eg. Minio) and credentials to read, write, delete to a block storage bucket path.


## Setup

The system uses Helm to deploy to a Kubernetes cluster. All of the cluster config settings are set it config.yaml

1. Copy `config.sample.yaml` -> `config.yaml`.

2. Fill in the details of credentials.

3. Before first run, create the `browsers` namespace by running `kubectl create namespace browsers`.

3. To start, run `helm install https://webrecorder.github.io/browserkube/charts -f ./config.yaml` to the currently configured Kubernetes cluster.

4. To stop the cluster, run `helm uninstall perma permafact`.


### Ingress Option

If the `ingress.host` and `ingress.cert_email` are set, the Helm chart will configure an Ingress controller,
on the specified host, and attempt to obtain an SSL cert (via Letsencrypt).

If the host is omitted, no ingress is created. This may be useful for only accessing the service via an internal network.

