-- The verified run used this pool temporarily configured as GPU_NV_XS, MAX_NODES=1.
-- Choose an available GPU pool if the restored default family has no capacity.
EXECUTE NOTEBOOK PROJECT HELSINKI_WEATHER_LAB.KUMO_2026.HELSINKI_TEMPERATURE_2026
 MAIN_FILE='helsinki_temperature_2026.ipynb'
 COMPUTE_POOL='SYSTEM_COMPUTE_POOL_GPU'
 QUERY_WAREHOUSE='COMPUTE_WH'
 RUNTIME='V2.9-GPU-PY3.12'
 REQUIREMENTS_FILE='requirements.txt'
 ARTIFACT_REPOSITORIES=(snowflake.snowpark.pypi_shared_repository);
