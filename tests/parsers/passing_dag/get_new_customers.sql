SELECT * FROM {{customers_table}} WHERE member_since > DATEADD(day, -7, '{{ execution_date }}')
