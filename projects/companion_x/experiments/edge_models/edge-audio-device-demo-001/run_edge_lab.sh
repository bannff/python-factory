#!/usr/bin/env bash
# Execute the anonymous cohort in a disposable, offline ARM64 edge-lab workload.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 PAYLOAD_DIR ARM64_NUMPY_WHEEL OUTPUT_JSON" >&2
  exit 2
fi

payload_dir=$1
wheel=$2
output=$3
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
container="edge-audio-demo-001-$$"
wheel_digest=f9e75681b59ddaa5e659898085ae0eaea229d054f2ac0c7e563a62205a700121

[[ $(basename -- "$payload_dir") == payload ]] || { echo "payload directory must be named payload" >&2; exit 2; }
[[ -f "$payload_dir/model.npz" && -f "$payload_dir/cohort.json" ]] || { echo "payload incomplete" >&2; exit 2; }
python3 "$script_dir/payload_layout.py" "$payload_dir"
[[ -f "$wheel" ]] || { echo "wheel missing" >&2; exit 2; }
[[ $(shasum -a 256 "$wheel" | cut -d ' ' -f 1) == "$wheel_digest" ]] || { echo "wheel digest mismatch" >&2; exit 2; }

cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$container" --platform linux/arm64 --network none \
  --cpus 1 --memory 512m --memory-swap 512m --read-only \
  --tmpfs /work:rw,exec,size=160m --tmpfs /tmp:rw,size=160m \
  python-factory/edge-lab:local >/dev/null

# Docker cp refuses a read-only root even for a tmpfs target; stream into /work.
docker exec -i "$container" sh -c 'cat > /work/runtime.py' < "$script_dir/runtime.py"
tar -C "$(dirname -- "$payload_dir")" -cf - payload | docker exec -i "$container" tar -C /work -xf -
docker exec -i "$container" sh -c 'cat > /work/numpy.whl' < "$wheel"
docker exec "$container" python -m zipfile -e /work/numpy.whl /work/vendor
docker exec -e PYTHONPATH=/work/vendor "$container" python /work/runtime.py \
  --model /work/payload/model.npz --cohort /work/payload/cohort.json \
  --output /work/predictions.json --repeats 30

mkdir -p -- "$(dirname -- "$output")"
docker exec "$container" cat /work/predictions.json > "$output"
docker inspect "$container" --format \
  'image={{.Image}} network={{.HostConfig.NetworkMode}} nano_cpus={{.HostConfig.NanoCpus}} memory_bytes={{.HostConfig.Memory}} memory_swap_bytes={{.HostConfig.MemorySwap}} read_only={{.HostConfig.ReadonlyRootfs}}' \
  > "$output.container.txt"
