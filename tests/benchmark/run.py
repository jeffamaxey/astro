import argparse
import inspect
import json
import os
import sys
import time

import airflow
import psutil
from airflow.executors.debug_executor import DebugExecutor
from airflow.utils import timezone


def elapsed_since(start):
    return time.time() - start


def get_disk_usage():
    path = "/"
    disk_usage = psutil.disk_usage(path)
    return disk_usage.used


def subtract(after_dict, before_dict):
    return {key: after_dict[key] - before_dict.get(key, 0) for key in after_dict}


def profile(func, *args, **kwargs):
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        # metrics before
        memory_full_info_before = process.memory_full_info()._asdict()
        cpu_time_before = process.cpu_times()._asdict()
        disk_usage_before = get_disk_usage()
        if sys.platform == "linux":
            io_counters_before = process.io_counters()._asdict()
        start = time.time()

        # run decorated function
        result = func(*args, **kwargs)

        # metrics after
        elapsed_time = elapsed_since(start)
        memory_full_info_after = process.memory_full_info()._asdict()
        cpu_time_after = process.cpu_times()._asdict()
        disk_usage_after = get_disk_usage()
        if sys.platform == "linux":
            io_counters_after = process.io_counters()._asdict()

        profile = {
            "duration": elapsed_time,
            "memory_full_info": subtract(
                memory_full_info_after, memory_full_info_before
            ),
            "cpu_time": subtract(cpu_time_after, cpu_time_before),
            "disk_usage": disk_usage_after - disk_usage_before,
        }
        if sys.platform == "linux":
            profile["io_counters"] = (subtract(io_counters_after, io_counters_before),)

        profile = profile | kwargs
        print(json.dumps(profile, default=str))
        return result

    if inspect.isfunction(func):
        return wrapper
    elif inspect.ismethod(func):
        return wrapper(*args, **kwargs)


@profile
def run_dag(dag_id, execution_date, **kwargs):
    dagbag = airflow.models.DagBag()
    dag = dagbag.get_dag(dag_id)
    dag.clear(start_date=execution_date, end_date=execution_date, dag_run_state=False)

    dag.run(
        executor=DebugExecutor(),
        start_date=execution_date,
        end_date=execution_date,
        # Always run the DAG at least once even if no logical runs are
        # available. This does not make a lot of sense, but Airflow has
        # been doing this prior to 2.2 so we keep compatibility.
        run_at_least_once=True,
    )


def build_dag_id(dataset, database):
    return f"load_file_{dataset}_into_{database}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger benchmark DAG")
    parser.add_argument(
        "--database",
        type=str,
        help="Database {snowflake, bigquery, postgres}",
        required=True,
    )
    parser.add_argument(
        "--dataset",
        type=str,
        help="Dataset {few_kb, many_kb, few_mb, many_mb}",
        required=True,
    )
    parser.add_argument(
        "--revision",
        type=str,
        help="Git commit hash, to relate the results to a version",
    )
    parser.add_argument(
        "--chunk-size",
        "-c",
        type=int,
        help="Chunk size used for loading from file to database. Default: [1,000,000]",
    )
    args = parser.parse_args()
    dag_id = build_dag_id(args.dataset, args.database)
    run_dag(
        dag_id=dag_id,
        execution_date=timezone.utcnow(),
        revision=args.revision,
        chunk_size=args.chunk_size,
    )
