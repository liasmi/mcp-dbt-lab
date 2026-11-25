{% macro cents_to_dollars(column_name) %}
    cast({{ column_name }} as decimal(14, 2)) / 100
{% endmacro %}
