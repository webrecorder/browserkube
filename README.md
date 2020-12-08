## Webrecorder Browserkube

This repository contains an experimental, Kubernetes-native Webrecorder remote browser orchestration system.

The system supports several use cases:
- Running browsers as demanded by the user, with VNC, shutting down after fixed amount of time or when user closes connection.
- Running browsers controlled by a driver container, which shuts down the browser when done.
- Headless browser or 'headful', with or without VNC.
- Running browsers with custom, pre-prepared [browser profiles](https://blog.mozilla.org/firefox/profiles-shmofiles-whats-browser-profile-anyway/) to supply cookies, site-specific preferences or other config; specify a default profile to use for all URLs or provide a list of URL-specific profiles.

This repository provides an extensible set of containers and a Helm chart installable from [https://webrecorder.github.io/browserkube/charts](https://webrecorder.github.io/browserkube/charts).

Requirements:

- A Kubernetes cluster
- A local copy of [`kubectl`](https://kubernetes.io/docs/tasks/tools/install-kubectl/), configured to run commands against the cluster
- A local copy of [Helm 3](https://v3.helm.sh/)


Optional:

Browserkube ships with a minimally-configured deployment of [Minio](https://min.io/) for storage.

You may prefer to use an external S3-compatible storage service like [Amazon Simple Storage Service](https://aws.amazon.com/s3/) or [Digital Oceans Spaces Object Storage](https://www.digitalocean.com/products/spaces/).


## Setup

The system uses Helm to deploy to a Kubernetes cluster.

1. Add the Browserkube chart repository to Helm: `helm repo add browserkube https://webrecorder.github.io/browserkube/charts`

2. Configure the chart:
   1. `touch config.yaml`.
   2. As desired, override any of the default config in `helm show values browserkube/browserkube` (see `chart/values.yaml`) by adding keys to `config.yaml`. (For example, to use custom storage, set `enable_minio: False` and copy over the complete "storage" mapping, swapping in your credentials and details in place of the default minio config values.)

3. Run `helm install bk browserkube/browserkube -f ./config.yaml` to install a release (here, arbitrarily named "bk") of the chart on the currently configured Kubernetes cluster. If successful, `helm list` will list the `bk` release, and `kubectl get services` will list the `browserkube` service, and you should be able to see the service and its pods in the Kubernetes dashboard. `kubectl get namespaces` should list the (newly-created) namespace specified by the `browser_namespace` config value.

4. To uninstall the release, run `helm uninstall bk`.


### Ingress Option / Exposing the Service

If the `ingress.host` and `ingress.cert_email` are set, the Helm chart will configure an Ingress controller on the specified host and attempt to obtain an SSL cert via Letsencrypt. This is the recommended approach for basic cloud installations.

If the host is omitted, no ingress is created, and you will need to expose the service using other strategies. This may be useful if you wish to deploy the service to an internal network, or when using an [external load balancer](https://kubernetes.io/docs/tasks/access-application-cluster/create-external-load-balancer/). It is presently the only option locally.

For example, if developing locally using [minikube](https://minikube.sigs.k8s.io/docs/start/), `minikube service --url browserkube` will expose the browserkube service to your localhost on a random port; `minikube service --url minio` will do the same with minio.

Or, you can arrange for port-forwarding using kubectl: `kubectl port-forward service/browserkube 8080:80` will map localhost:8080 to a single browserkube pod (all traffic will be directed to one pod, selected when the command is run, even if multiple pods are running on the cluster) and `kubectl port-forward service/minio 9000` will expose minio on port 9000. However, as of 12/8/20, this strategy is known to be [relatively flaky](https://github.com/kubernetes/kubernetes/issues/74551).
