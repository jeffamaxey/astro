#!/usr/bin/env python3

import argparse
import json
import sys

import pandas as pd

SUMMARY_FIELDS = [
    "database",
    "dataset",
    "total_time",
    "memory_rss",
    "cpu_time_user",
    "cpu_time_system",
]

if sys.platform == "linux":
    SUMMARY_FIELDS.extend(("memory_pss", "memory_shared"))


def format_bytes(bytes_):
    if abs(bytes_) < 1000:
        return f"{str(bytes_)}B"
    elif abs(bytes_) < 1e6:
        return f"{str(round(bytes_ / 1000.0, 2))}kB"
    elif abs(bytes_) < 1e9:
        return f"{str(round(bytes_ / 1000000.0, 2))}MB"
    else:
        return f"{str(round(bytes_ / 1000000000.0, 2))}GB"


def format_time(time):
    if time < 1:
        return f"{str(round(time * 1000, 2))}ms"
    if time < 60:
        return f"{str(round(time, 2))}s"
    if time < 3600:
        return f"{str(round(time / 60, 2))}min"
    else:
        return f"{str(round(time / 3600, 2))}hrs"


def analyse_results(results_filepath):
    data = []
    with open(results_filepath) as fp:
        data.extend(json.loads(line.strip()) for line in fp)
    df = pd.json_normalize(data, sep="_")

    # calculate total CPU from process & children
    mean_by_dag = df.groupby("dag_id", as_index=False).mean()

    # format data
    mean_by_dag["database"] = mean_by_dag.dag_id.apply(
        lambda text: text.split("into_")[-1]
    )
    mean_by_dag["dataset"] = mean_by_dag.dag_id.apply(
        lambda text: text.split("load_file_")[-1].split("_into")[0]
    )

    mean_by_dag["memory_rss"] = mean_by_dag.memory_full_info_rss.apply(
        lambda value: format_bytes(value)
    )
    if sys.platform == "linux":
        mean_by_dag["memory_pss"] = mean_by_dag.memory_full_info_pss.apply(
            lambda value: format_bytes(value)
        )
        mean_by_dag["memory_shared"] = mean_by_dag.memory_full_info_shared.apply(
            lambda value: format_bytes(value)
        )

    mean_by_dag["total_time"] = mean_by_dag["duration"].apply(
        lambda ms_time: format_time(ms_time)
    )

    mean_by_dag["cpu_time_system"] = (
        mean_by_dag["cpu_time_system"] + mean_by_dag["cpu_time_children_system"]
    ).apply(lambda ms_time: format_time(ms_time))
    mean_by_dag["cpu_time_user"] = (
        mean_by_dag["cpu_time_user"] + mean_by_dag["cpu_time_children_user"]
    ).apply(lambda ms_time: format_time(ms_time))

    summary = mean_by_dag[SUMMARY_FIELDS]

    # print Markdown tables per database
    for database_name in summary["database"].unique().tolist():
        print(f"\n### Database: {database_name}\n")
        print(summary[summary["database"] == database_name].to_markdown(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger benchmark DAG")
    parser.add_argument(
        "--results-filepath",
        "-r",
        type=str,
        help="NDJSON containing the results for a benchmark run",
    )
    args = parser.parse_args()
    print(f"Running the analysis on {args.results_filepath}...")
    analyse_results(args.results_filepath)
