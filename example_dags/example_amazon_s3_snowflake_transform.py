import os
import time
from datetime import datetime, timedelta

import pandas as pd

# Uses data from https://www.kaggle.com/c/shelter-animal-outcomes
from airflow.decorators import dag

from astro import dataframe as df
from astro import sql as aql
from astro.sql.table import Table


@aql.transform()
def combine_data(center_1: Table, center_2: Table):
    return """SELECT * FROM {{center_1}}
    UNION SELECT * FROM {{center_2}}"""


@aql.transform()
def clean_data(input_table: Table):
    return """SELECT *
    FROM {{input_table}} WHERE TYPE NOT LIKE 'Guinea Pig'
    """


@df(identifiers_as_lower=False)
def aggregate_data(df: pd.DataFrame):
    return df.pivot_table(
        index="DATE", values="NAME", columns=["TYPE"], aggfunc="count"
    ).reset_index()


@dag(
    start_date=datetime(2021, 1, 1),
    max_active_runs=1,
    schedule_interval="@daily",
    default_args={
        "email_on_failure": False,
        "retries": 0,
        "retry_delay": timedelta(minutes=5),
    },
    catchup=False,
)
def example_amazon_s3_snowflake_transform():

    s3_bucket = os.getenv("S3_BUCKET", "s3://tmp9")

    input_table_1 = Table(
        "ADOPTION_CENTER_1",
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        conn_id="snowflake_conn",
    )
    input_table_2 = Table(
        "ADOPTION_CENTER_2",
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
        conn_id="snowflake_conn",
    )

    temp_table_1 = aql.load_file(
        path=f"{s3_bucket}/ADOPTION_CENTER_1.csv",
        file_conn_id="",
        output_table=input_table_1,
    )
    temp_table_2 = aql.load_file(
        path=f"{s3_bucket}/ADOPTION_CENTER_2.csv",
        file_conn_id="",
        output_table=input_table_2,
    )

    combined_data = combine_data(
        center_1=temp_table_1,
        center_2=temp_table_2,
    )

    cleaned_data = clean_data(combined_data)
    aggregate_data(
        cleaned_data,
        output_table=Table(
            f"aggregated_adoptions_{int(time.time())}",
            schema=os.environ["SNOWFLAKE_SCHEMA"],
            conn_id="snowflake_conn",
        ),
    )


dag = example_amazon_s3_snowflake_transform()
