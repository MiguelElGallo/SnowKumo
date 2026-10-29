# Fix a failed setup

## CUDA or torchvision fails after installing Kumo

In the recorded runtime, an unpinned install selected PyTorch 2.15.0+cu132.
Its CUDA 13.2 build was incompatible with the installed driver, and Kumo import
also failed against the runtime's torchvision package.

Install the supplied `requirements.txt` and restart the kernel. The successful
environment resolved PyTorch 2.9.1+cu128, CUDA 12.8, and Kumo Engine 1.0.0.
Then rerun the preflight and imports. Do not continue when CUDA is unavailable.
These pins record one tested environment; they are not a complete transitive lock.

## The trial rejects external access with 509009

The tested trial rejected creation of the tutorial's direct PyPI external-access
integration. Managed Artifact Repository package installation succeeded instead.
Select `snowflake.snowpark.pypi_shared_repository` and ensure your lab role has
`SNOWFLAKE.PYPI_REPOSITORY_USER`. See
[Snowflake package management](https://docs.snowflake.com/en/developer-guide/snowflake-ml/container-runtime-package-management).
If that route is unavailable too, ask your administrator about the account's
entitlements. Repeating integration creation does not enable a blocked feature.

## No GPU capacity is available

The recorded `GPU_NV_SM` allocation failed with capacity error 392507.
A temporary `GPU_NV_XS` pool configuration with one node worked in that account.
The actual device reported by PyTorch was an NVIDIA A10-24Q.
Choose an available supported GPU family for your account and region; the family
name alone does not establish the device you received. Do not modify a shared
pool while other workloads depend on it.

## The custom-label loader rejects SPLIT

Kumo 1.0.0 rejected the exported decimal128 split column. A float cast also arrived
as unsupported float32. `setup_2026.sql` creates `TRAINING_LABELS_KUMO`, which casts
only `SPLIT` to strings `0`, `1`, and `2`. Confirm the notebook reads that view,
not the original labels table. The original integer labels remain unchanged.

## A rerun reports a source-content mismatch

The loader compares every row, including existing tables. A mismatch means your
Snowflake data differs from the selected CSV snapshot. Use a separate lab database
or reconcile the source version before rerunning. An equal row count is not enough.
