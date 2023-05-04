import math
import pathlib

import pandas as pd
import pytest
from airflow.decorators import task_group
from airflow.utils import timezone

from astro import sql as aql
from astro.constants import Database
from astro.dataframe import dataframe as adf
from astro.sql.table import Table, TempTable
from astro.utils.database import get_database_from_conn_id
from tests.operators import utils as test_utils

DEFAULT_DATE = timezone.datetime(2016, 1, 1)
CWD = pathlib.Path(__file__).parent

default_args = {
    "owner": "airflow",
    "retries": 1,
    "retry_delay": 0,
}


def merge_keys(sql_server, mode):
    """
    To match with their respective API's, we have a slightly different "merge_keys" value
    when a user is using snowflake.
    :param sql_server:
    :return:
    """
    sql_name, _ = sql_server
    keys = []
    if mode in ["multi", "update"]:
        keys = ["list", "sell"]
    elif mode == "single":
        keys = ["list"]
    return {k: k for k in keys} if sql_name == "snowflake" else keys


@pytest.fixture
def merge_parameters(request, sql_server):
    mode = request.param
    if mode == "single":
        return (
            {
                "merge_keys": merge_keys(sql_server, mode),
                "merge_columns": ["list"],
                "target_columns": ["list"],
                "conflict_strategy": "ignore",
            },
            mode,
        )
    elif mode == "multi":
        return (
            {
                "merge_keys": merge_keys(sql_server, mode),
                "merge_columns": ["list", "sell"],
                "target_columns": ["list", "sell"],
                "conflict_strategy": "ignore",
            },
            mode,
        )
    elif mode == "update":
        return (
            {
                "merge_keys": merge_keys(sql_server, mode),
                "target_columns": ["list", "sell", "taxes"],
                "merge_columns": ["list", "sell", "age"],
                "conflict_strategy": "update",
            },
            mode,
        )


@aql.transform
def do_a_thing(input_table: Table):
    return "SELECT * FROM {{input_table}}"


@aql.run_raw_sql
def add_constraint(table: Table, columns):
    database = get_database_from_conn_id(table.conn_id)
    if database == Database.SQLITE:
        return (
            "CREATE UNIQUE INDEX unique_index ON {{table}}" + f"({','.join(columns)})"
        )
    elif database == Database.BIGQUERY:
        return ""
    return (
        "ALTER TABLE {{table}} ADD CONSTRAINT airflow UNIQUE"
        + f" ({','.join(columns)})"
    )


@adf
def validate_results(df: pd.DataFrame, mode, sql_type):
    # make columns lower and reverse due to snowflake defaulting to uppercase
    # Also reverse because BQ and snowflake seem to reverse row order
    if sql_type in ["snowflake", "bigquery"]:
        df.columns = df.columns.str.lower()
        df = df.iloc[::-1]

    def set_compare(l1, l2):
        l1 = list(filter(lambda val: not math.isnan(val), l1))
        return set(l1) == set(l2)

    df = df.sort_values(by=["list"], ascending=True)

    if mode == "single":
        assert set_compare(df.age.to_list()[:-1], [60.0, 12.0, 41.0, 22.0])
        assert set_compare(df.taxes.to_list()[:-1], [3167.0, 4033.0, 1471.0, 3204.0])
        assert set_compare(df.taxes.to_list()[:-1], [3167.0, 4033.0, 1471.0, 3204.0])
        assert set_compare(df.list.to_list(), [160, 180, 132, 140, 240])
        assert set_compare(df.sell.to_list()[:-1], [142, 175, 129, 138])
    elif mode == "multi":
        assert set_compare(df.age.to_list()[:-1], [60.0, 12.0, 41.0, 22.0])
        assert set_compare(df.taxes.to_list()[:-1], [3167.0, 4033.0, 1471.0, 3204.0])
        assert set_compare(df.taxes.to_list()[:-1], [3167.0, 4033.0, 1471.0, 3204.0])
        assert set_compare(df.list.to_list(), [160, 180, 132, 140, 240])
        assert set_compare(df.sell.to_list()[:-1], [142, 175, 129, 138])
    elif mode == "update":
        assert df.taxes.to_list() == [1, 1, 1, 1, 1]
        assert set_compare(df.age.to_list()[:-1], [60.0, 12.0, 41.0, 22.0])


@task_group
def run_merge(output_specs: TempTable, merge_parameters, mode, sql_type):
    main_table = aql.load_file(
        path=f"{str(CWD)}/../data/homes_merge_1.csv", output_table=output_specs
    )
    merge_table = aql.load_file(
        path=f"{str(CWD)}/../data/homes_merge_2.csv", output_table=output_specs
    )

    con1 = add_constraint(main_table, merge_parameters["merge_keys"])

    merged_table = aql.merge(
        target_table=main_table,
        merge_table=merge_table,
        **merge_parameters,
    )
    con1 >> merged_table
    validate_results(df=merged_table, mode=mode, sql_type=sql_type)


@pytest.mark.parametrize(
    "sql_server",
    [
        "bigquery",
        "snowflake",
        "postgres",
        "sqlite",
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "merge_parameters",
    [
        # "None",
        "single",
        "multi",
        "update",
    ],
    indirect=True,
)
def test_merge(sql_server, sample_dag, test_table, merge_parameters):
    sql_type, _ = sql_server
    merge_params, mode = merge_parameters
    with sample_dag:
        output_table = test_table
        run_merge(output_table, merge_params, mode, sql_type)
    test_utils.run_dag(sample_dag)
