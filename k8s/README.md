# Deploying to Rancher / Kubernetes

These manifests replace `render.yaml` for hosting the GUI (`webapp/`)
on a Kubernetes cluster managed by Rancher, using the same
`Dockerfile` at the repo root.

## 1. Build and push the image

Rancher pulls a prebuilt image from a container registry - it
doesn't build from source. From the repo root:

```
docker build -t your-registry.example.com/lead-validator:latest .
docker push your-registry.example.com/lead-validator:latest
```

Use whatever registry your cluster can already pull from (Docker
Hub, GHCR, a private registry Rancher's nodes are configured for,
etc.). If it's private, create an `imagePullSecrets` entry too -
Rancher: **Cluster Explorer → Storage → Secrets → Registry** does
this for you.

## 2. Set the real image name

Edit `k8s/deployment.yaml` and replace
`your-registry.example.com/lead-validator:latest` with the image you
just pushed.

## 3. Create the secret

Copy `k8s/secret.example.yaml` to `k8s/secret.yaml`, fill in a real
`APP_PASSWORD` and `SECRET_KEY`, and **don't commit `secret.yaml`**
(already covered by `.gitignore`). Or skip the file entirely and
create the secret directly in Rancher's UI: **Project → Secrets →
Create** (namespace `lead-validator`, name
`lead-validator-secrets`, keys `APP_PASSWORD` / `SECRET_KEY`).

## 4. Apply everything

Either via `kubectl` (Rancher exposes a working kubeconfig under
**Cluster → Kubeconfig File**):

```
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml   # optional - see below
```

...or through the Rancher UI: open your cluster, **Cluster
Explorer**, click the **Import YAML** button (top right, `+` icon),
and paste in each file's contents (or all of them at once - Rancher
accepts multi-document YAML).

## 5. Expose it

`k8s/ingress.yaml` assumes an nginx ingress controller (Rancher's
default RKE/RKE2 clusters ship with one) and needs its `host` edited
to your real domain before applying. No ingress controller, or want
something quicker to test with? Change `k8s/service.yaml`'s `type`
to `NodePort` instead, or use Rancher's UI: **Workload → lead-validator
→ ⋮ → Add Port** to publish it.

## 6. Check it's up

```
kubectl -n lead-validator get pods
kubectl -n lead-validator logs deploy/lead-validator
```

Rancher's UI shows the same under **Workloads**, including a
built-in shell/log viewer per pod.

Open the service URL (via Ingress host, NodePort, or `kubectl
port-forward svc/lead-validator -n lead-validator 8080:80` for a
quick local check), log in with `APP_PASSWORD`, and use it exactly
as described in the main README.

## Notes specific to this app

- **Single replica only.** `k8s/deployment.yaml` sets `replicas: 1`
  and `strategy: Recreate` on purpose - the app manages one
  browser-driven scraping job and one working Excel file at a time
  (see `webapp/app.py`), and its data volume is `ReadWriteOnce`.
  Don't scale this deployment up.
- **Persistent data.** `k8s/pvc.yaml` gives `webapp/data/` (uploaded
  cookies, in-progress Excel file, job progress) a 1Gi volume so it
  survives pod restarts, unlike the Render free-plan setup this
  replaces. Adjust the size or `storageClassName` for your cluster.
- **Resource sizing.** The container runs a real Chromium browser
  under Xvfb, which is heavier than a typical web app - the
  `resources` block in `k8s/deployment.yaml` (768Mi request / 2Gi
  limit) is a starting point; watch `kubectl top pod` under load and
  adjust.
- **Health checks.** `GET /healthz` (added in the FastAPI app) is
  what the readiness/liveness probes hit - it doesn't require login
  and doesn't touch the browser/job state.
