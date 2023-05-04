from astro.sql.table import Table


def add_templates_to_context(parameters, context):
    for k, v in parameters.items():
        context[k] = v.qualified_name() if isinstance(v, Table) else f":{k}"
    return context
